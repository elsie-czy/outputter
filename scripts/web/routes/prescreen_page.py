import json
import os
import subprocess
import threading
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from scripts.config import BASE_DIR, PATHS, ensure_dirs
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, now_ts
from scripts.web.services.prescreen_status import (
    humanize_prescreen_summary,
    load_prescreen_jobs_tail,
    load_prescreen_recent,
)

bp = Blueprint("web_prescreen", __name__)


def _int_arg(name, default, min_value=1, max_value=500):
    try:
        value = int(request.args.get(name, default) if request.method == "GET" else (request.json or {}).get(name, default))
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _normalize_ts(value):
    ts = _safe_float(value, 0)
    if not ts:
        return 0
    # Feishu date fields and prescreen_fetch_insert.py use milliseconds.
    if ts > 100000000000:
        ts = ts / 1000
    return ts


def _safe_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _fmt_ts(value):
    ts = _normalize_ts(value)
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _normalize_list_text(value):
    if isinstance(value, list):
        return "、".join([str(x).strip() for x in value if str(x).strip()])
    s = str(value or "").strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = json.loads(s.replace("'", '"'))
            if isinstance(parsed, list):
                return "、".join([str(x).strip() for x in parsed if str(x).strip()])
        except Exception:
            pass
    return s


def _build_command_display(mode, sources, limit, batch, query="", dry_run=False):
    parts = [
        "prescreen_fetch_insert.py",
        "--mode",
        mode,
        "--sources",
        sources,
        "--limit",
        str(limit),
        "--batch",
        batch,
    ]
    if mode == "search" and query:
        parts.extend(["--query", query])
    if dry_run:
        parts.append("--dry-run")
    return " ".join(parts)


def _extract_summary_counts(result):
    summary = result.get("summary") or ""
    data = {}
    try:
        data = json.loads(summary)
    except Exception:
        data = {}
    return {
        "fetched": _safe_int(data.get("fetched")),
        "created": _safe_int(data.get("created")),
        "updated": _safe_int(data.get("updated")),
        "skipped": _safe_int(data.get("skipped")),
        "errors": _safe_int(data.get("errors")),
    }


def _load_prescreen_records(limit=500):
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
    if not table_id:
        raise RuntimeError("未配置 选题库-初筛 table_id")

    items = []
    for idx, rec in enumerate(client.iter_records(table_id, page_size=100)):
        if idx >= limit:
            break
        f = rec.get("fields") or {}
        title = str(f.get("作品名称", "")).strip()
        author = str(f.get("作者", "")).strip()
        platform = str(f.get("平台", "")).strip()
        in_library = str(f.get("是否入库", "") or "否").strip()
        score = _safe_float(f.get("综合得分") or f.get("推荐热度_数值") or f.get("平台评分_数值"))
        item = {
            "record_id": rec.get("record_id", ""),
            "title": title,
            "author": author,
            "platform": platform,
            "type": str(f.get("类型", "")).strip(),
            "link": str(f.get("作品链接", "")).strip(),
            "in_library": in_library,
            "finished": str(f.get("是否完结", "")).strip(),
            "dimension": str(f.get("入选维度", "")).strip(),
            "rank_source": str(f.get("榜单来源", "")).strip(),
            "rank_pos": _safe_int(f.get("榜单排名"), 0),
            "collect_num": _safe_int(f.get("收藏量_数值"), 0),
            "review_num": _safe_int(f.get("书评量_数值"), 0),
            "platform_score": _safe_float(f.get("平台评分_数值"), 0),
            "score": score,
            "batch": str(f.get("抓取批次", "")).strip(),
            "updated_ts": _normalize_ts(f.get("最近更新") or f.get("添加时间")),
            "updated_at": _fmt_ts(f.get("最近更新") or f.get("添加时间")),
            "desc": str(f.get("简介", "")).strip(),
        }
        if title or author or platform:
            items.append(item)

    items.sort(key=lambda x: (x.get("updated_ts") or 0, x.get("score") or 0), reverse=True)
    return items


def _get_prescreen_record(client, table_id, record_id):
    rid = str(record_id or "").strip()
    if not rid:
        return None
    for rec in client.iter_records(table_id, page_size=100):
        if str(rec.get("record_id") or "").strip() == rid:
            return rec
    return None


def _build_topic_fields_from_prescreen(prescreen_fields, topic_available):
    title = str(prescreen_fields.get("作品名称") or "").strip()
    author = str(prescreen_fields.get("作者") or "").strip()
    platform = str(prescreen_fields.get("平台") or "").strip()
    type_name = str(prescreen_fields.get("类型") or "").strip()
    desc = str(prescreen_fields.get("简介") or "").strip()
    link = str(prescreen_fields.get("作品链接") or "").strip()
    dimension = _normalize_list_text(prescreen_fields.get("入选维度"))
    reason = str(prescreen_fields.get("推荐理由") or "").strip()
    rank_source = str(prescreen_fields.get("榜单来源") or "").strip()
    rank_pos = _safe_int(prescreen_fields.get("榜单排名"), 0)
    batch = str(prescreen_fields.get("抓取批次") or "").strip()
    platform_score = _safe_float(prescreen_fields.get("平台评分_数值"), 0)

    fields = {}
    if "作品名称" in topic_available:
        fields["作品名称"] = title
    if "作者" in topic_available:
        fields["作者"] = author
    if "平台" in topic_available:
        fields["平台"] = platform
    if "分类" in topic_available:
        fields["分类"] = type_name
    elif "类型" in topic_available:
        fields["类型"] = type_name
    if "简介" in topic_available:
        fields["简介"] = desc[:1000]
    if "作品链接" in topic_available:
        fields["作品链接"] = link
    if "搜索要素" in topic_available:
        parts = [x for x in [title, author, platform, type_name] if x]
        fields["搜索要素"] = " ".join(parts)
    if "评分" in topic_available and platform_score:
        fields["评分"] = platform_score
    if "排名" in topic_available and rank_pos:
        fields["排名"] = float(rank_pos)
    if "推荐理由" in topic_available:
        fields["推荐理由"] = reason or dimension
    if "备注" in topic_available:
        note_parts = ["来源：选题库初筛"]
        if dimension:
            note_parts.append(f"入选维度：{dimension}")
        if rank_source:
            note_parts.append(f"榜单来源：{rank_source}")
        if batch:
            note_parts.append(f"抓取批次：{batch}")
        if link and "作品链接" not in topic_available:
            note_parts.append(f"作品链接：{link}")
        fields["备注"] = "\n".join(note_parts)
    if "是否拆解" in topic_available:
        fields["是否拆解"] = "否"
    if "是否入库" in topic_available:
        fields["是否入库"] = "是"
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _status_payload():
    recent = load_prescreen_recent()
    jobs = load_prescreen_jobs_tail()
    latest_result = (recent.get("latest") or [{}])[0] if recent.get("latest") else {}
    latest_job = (jobs.get("latest") or [{}])[0] if jobs.get("latest") else {}
    counts = _extract_summary_counts(latest_result)
    mode = latest_result.get("mode") or latest_job.get("mode") or "rank"
    sources = latest_result.get("sources") or latest_job.get("sources") or "fanqie,jjwxc"
    limit = latest_result.get("limit") or latest_job.get("limit") or 60
    batch = latest_result.get("batch") or latest_job.get("batch") or datetime.now().strftime("%Y-%m-%d")
    query = latest_result.get("query") or latest_job.get("query") or ""
    return {
        "recent": recent,
        "jobs": jobs,
        "latest_result": latest_result,
        "latest_job": latest_job,
        "counts": counts,
        "command": _build_command_display(mode, sources, limit, batch, query, bool(latest_result.get("dry_run"))),
    }


@bp.get("/prescreen")
def prescreen_page():
    return render_template("prescreen.html", active_page="prescreen", page_title="选题库初筛")


@bp.get("/api/prescreen/overview")
def prescreen_overview():
    payload = _status_payload()
    stats = {"total": 0, "yes": 0, "no": 0, "unscored": 0, "batch_options": []}
    err = None
    try:
        rows = _load_prescreen_records(limit=1200)
        batches = []
        for item in rows:
            stats["total"] += 1
            if str(item.get("in_library") or "").strip() in ("是", "已入库", "yes", "true", "1"):
                stats["yes"] += 1
            else:
                stats["no"] += 1
            if not item.get("score"):
                stats["unscored"] += 1
            batch = item.get("batch") or ""
            if batch and batch not in batches:
                batches.append(batch)
        stats["batch_options"] = batches[:20]
    except Exception as e:
        err = str(e)
    return jsonify({"ok": err is None, "error": err, "status": payload, "stats": stats})


@bp.get("/api/prescreen/list")
def prescreen_list():
    try:
        limit = _int_arg("limit", 500, 1, 1200)
        items = _load_prescreen_records(limit=limit)
        return jsonify({"ok": True, "data": {"items": items}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "data": {"items": []}}), 500


@bp.post("/api/prescreen/fetch")
def prescreen_fetch():
    ensure_dirs()
    data = request.get_json() or {}
    mode = str(data.get("mode") or "rank").strip()
    query = str(data.get("query") or "").strip()
    raw_sources = data.get("sources") or ["fanqie", "jjwxc"]
    if isinstance(raw_sources, list):
        sources = ",".join([str(x).strip() for x in raw_sources if str(x).strip()])
    else:
        sources = str(raw_sources or "").strip()
    if not sources:
        sources = "fanqie,jjwxc"
    limit = max(1, min(200, _safe_int(data.get("limit"), 60)))
    batch = str(data.get("batch") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    dry_run = bool(data.get("dry_run"))

    if mode not in ("rank", "search"):
        return jsonify({"ok": False, "error": "mode 仅支持 rank/search"}), 400
    if mode == "search" and not query:
        return jsonify({"ok": False, "error": "关键词抓取需要填写关键词"}), 400

    job_id = f"ps_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"),
        {
            "ts": now_ts(),
            "job_id": job_id,
            "mode": mode,
            "query": query,
            "sources": sources,
            "limit": limit,
            "batch": batch,
            "dry_run": dry_run,
            "status": "queued",
        },
    )

    def run_job():
        append_jsonl(os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"), {"ts": now_ts(), "job_id": job_id, "status": "running"})
        python_bin = os.path.join(BASE_DIR, ".venv", "bin", "python")
        if not os.path.exists(python_bin):
            python_bin = "python"
        cmd = [
            python_bin,
            os.path.join(BASE_DIR, "scripts", "prescreen_fetch_insert.py"),
            "--sources",
            sources,
            "--limit",
            str(limit),
            "--batch",
            batch,
            "--mode",
            mode,
        ]
        if mode == "search":
            cmd.extend(["--query", query])
        if dry_run:
            cmd.append("--dry-run")

        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 15)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            summary = out.splitlines()[-1].strip() if out else f"returncode={p.returncode}"
            ok_flag = p.returncode == 0
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "ok": ok_flag,
                    "mode": mode,
                    "query": query,
                    "sources": sources,
                    "limit": limit,
                    "batch": batch,
                    "dry_run": dry_run,
                    "summary": summary,
                    "summary_cn": humanize_prescreen_summary(summary),
                    "stderr_tail": err[-800:] if err else "",
                },
            )
        except Exception as e:
            summary = f"exception: {e}"
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "ok": False,
                    "mode": mode,
                    "query": query,
                    "sources": sources,
                    "limit": limit,
                    "batch": batch,
                    "dry_run": dry_run,
                    "summary": summary,
                },
            )
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "status": "done",
                    "ok": ok_flag,
                    "summary": summary,
                    "summary_cn": humanize_prescreen_summary(summary),
                },
            )

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id, "command": _build_command_display(mode, sources, limit, batch, query, dry_run)})


@bp.post("/api/prescreen/maintain")
def prescreen_maintain():
    ensure_dirs()
    data = request.get_json() or {}
    limit = max(1, min(500, _safe_int(data.get("limit"), 128)))
    dry_run = bool(data.get("dry_run"))
    job_id = f"pm_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "prescreen_maintain_web_jobs.jsonl"),
        {"ts": now_ts(), "job_id": job_id, "limit": limit, "dry_run": dry_run, "status": "queued"},
    )

    def run_job():
        append_jsonl(os.path.join(PATHS["logs"], "prescreen_maintain_web_jobs.jsonl"), {"ts": now_ts(), "job_id": job_id, "status": "running"})
        python_bin = os.path.join(BASE_DIR, ".venv", "bin", "python")
        if not os.path.exists(python_bin):
            python_bin = "python"
        cmd = [python_bin, os.path.join(BASE_DIR, "scripts", "topic_prescreen_maintain.py"), "enrich", "--limit", str(limit)]
        if dry_run:
            cmd.append("--dry-run")
        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 10)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            summary = out.splitlines()[-1].strip() if out else f"returncode={p.returncode}"
            ok_flag = p.returncode == 0
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_maintain_web_results.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "ok": ok_flag, "limit": limit, "dry_run": dry_run, "summary": summary, "stderr_tail": err[-800:] if err else ""},
            )
        except Exception as e:
            summary = f"exception: {e}"
            append_jsonl(os.path.join(PATHS["logs"], "prescreen_maintain_web_results.jsonl"), {"ts": now_ts(), "job_id": job_id, "ok": False, "summary": summary})
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_maintain_web_jobs.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "status": "done", "ok": ok_flag, "summary": summary},
            )

    threading.Thread(target=run_job, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@bp.post("/api/prescreen/promote")
def prescreen_promote():
    data = request.get_json() or {}
    record_id = str(data.get("record_id") or "").strip()
    if not record_id:
        return jsonify({"ok": False, "error": "缺少初筛记录 ID"}), 400

    try:
        client = FeishuClient()
        if not client.is_configured():
            return jsonify({"ok": False, "error": "飞书未配置"}), 400

        cfg = get_feishu_config()
        prescreen_table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
        topic_table_id = (cfg.get("related_table_ids") or {}).get("选题库")
        if not prescreen_table_id:
            return jsonify({"ok": False, "error": "未配置 选题库-初筛 table_id"}), 500
        if not topic_table_id:
            return jsonify({"ok": False, "error": "未配置 选题库 table_id"}), 500

        prescreen_rec = _get_prescreen_record(client, prescreen_table_id, record_id)
        if not prescreen_rec:
            return jsonify({"ok": False, "error": "未找到初筛记录"}), 404
        source_fields = prescreen_rec.get("fields") or {}
        title = str(source_fields.get("作品名称") or "").strip()
        author = str(source_fields.get("作者") or "").strip()
        platform = str(source_fields.get("平台") or "").strip()
        if not title:
            return jsonify({"ok": False, "error": "初筛记录缺少作品名称"}), 400

        topic_available = client.get_table_fields(topic_table_id)
        topic_fields = _build_topic_fields_from_prescreen(source_fields, topic_available)
        topic_fields = client.filter_fields(topic_table_id, topic_fields)
        if not topic_fields:
            return jsonify({"ok": False, "error": "正式选题库没有可写入字段"}), 400

        match_fields = {}
        if "作品名称" in topic_available:
            match_fields["作品名称"] = title
        if author and "作者" in topic_available:
            match_fields["作者"] = author
        if platform and "平台" in topic_available:
            match_fields["平台"] = platform

        existing_topic_id = client.find_record_id_by_fields(topic_table_id, match_fields) if match_fields else None
        action = "created"
        if existing_topic_id:
            client.update_record_in_table(topic_table_id, existing_topic_id, topic_fields)
            topic_record_id = existing_topic_id
            action = "updated"
        else:
            topic_record_id = client.create_record_in_table(topic_table_id, topic_fields)

        prescreen_patch = {}
        prescreen_available = client.get_table_fields(prescreen_table_id)
        if "是否入库" in prescreen_available:
            prescreen_patch["是否入库"] = "是"
        if "入库时间" in prescreen_available:
            prescreen_patch["入库时间"] = int(datetime.now().timestamp() * 1000)
        if "正式选题记录ID" in prescreen_available and topic_record_id:
            prescreen_patch["正式选题记录ID"] = topic_record_id
        if prescreen_patch:
            client.update_record_in_table(prescreen_table_id, record_id, client.filter_fields(prescreen_table_id, prescreen_patch))

        append_jsonl(
            os.path.join(PATHS["logs"], "prescreen_promote.jsonl"),
            {
                "ts": now_ts(),
                "prescreen_record_id": record_id,
                "topic_record_id": topic_record_id,
                "action": action,
                "title": title,
                "author": author,
                "platform": platform,
            },
        )
        return jsonify({"ok": True, "action": action, "topic_record_id": topic_record_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
