from flask import Blueprint, jsonify, request

from scripts.model_adapter import analyze_work
from scripts.quality_scorer import score_note
from scripts.deconstruct_daily import build_xhs_note
from scripts.generation_context import build_generation_context, context_counts
from scripts.account_strategy import get_account_strategy

bp = Blueprint("web_note_api", __name__, url_prefix="/api/note")


@bp.get("/<rid>")
def get_note(rid):
    try:
        from scripts.queue_manager import get_queue
        result = get_queue(per_page=9999)
        for item in result.get("items", []):
            if item.get("record_id") == rid:
                return jsonify({"ok": True, "data": {
                    "record_id": rid,
                    "note_content": item.get("note_content", ""),
                    "quality_score": item.get("quality_score"),
                    "status": item.get("status"),
                }})
        # Fallback: check feishu
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config
        client = FeishuClient()
        cfg = get_feishu_config()
        xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if xhs_table_id and client.is_configured():
            records = client.list_records(xhs_table_id, page_size=10)
            for r in records:
                if r.get("record_id") == rid:
                    f = r.get("fields", {}) or {}
                    return jsonify({"ok": True, "data": {
                        "record_id": rid,
                        "title": str(f.get("小红书标题模板", "")),
                        "note_content": str(f.get("正文开头模板", "")),
                        "tags": str(f.get("热门标签推荐", "")),
                        "cta": str(f.get("互动话术模板", "")),
                    }})
        return jsonify({"ok": False, "error": "笔记未找到"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/regenerate")
def regenerate_note(rid):
    try:
        data = request.get_json(force=True) or {}
        # Build work dict from queue
        from scripts.queue_manager import get_queue, update_task_fields
        result = get_queue(per_page=9999)
        work = {}
        task = None
        for item in result.get("items", []):
            if item.get("record_id") == rid:
                task = item
                work = {
                    "作品名称": item.get("work_name", ""),
                    "作者": item.get("author", ""),
                    "平台": item.get("platform", ""),
                    "分类": item.get("category", ""),
                }
                break
        if not work:
            return jsonify({"ok": False, "error": "任务未找到"}), 404

        generation_context = build_generation_context(task)
        account_strategy = get_account_strategy(task.get("account_strategy_id") if task else None)
        analysis = analyze_work(work, account_strategy=account_strategy, **generation_context)
        note_text = build_xhs_note(work, analysis, account_strategy=account_strategy)
        score_result = score_note(note_text, account_strategy=account_strategy)
        update_task_fields(
            rid,
            deconstruct_result=analysis,
            note_content=note_text,
            quality_score=score_result,
        )
        return jsonify({"ok": True, "data": {
            "note_content": note_text,
            "quality_score": score_result,
            "title": analysis.get("小红书包装", {}).get("小红书标题模板", ""),
            "body": analysis.get("小红书包装", {}).get("正文开头模板", ""),
            "tags": analysis.get("小红书包装", {}).get("热门标签推荐", []),
            "cta": analysis.get("小红书包装", {}).get("互动话术模板", ""),
            "generation_context": context_counts(generation_context),
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/save")
def save_note(rid):
    try:
        data = request.get_json(force=True) or {}
        diff_log = data.get("diff_log", "")
        quality_score = data.get("quality_score") or {}
        title = data.get("title", "")
        body = data.get("body", "")
        tags = data.get("tags") or []
        cta = data.get("cta", "")
        note_content = data.get("note_content") or _compose_note(title, body, tags, cta)

        from scripts.queue_manager import get_queue, update_task_fields
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config
        task = None
        result = get_queue(per_page=9999)
        for item in result.get("items", []):
            if item.get("record_id") == rid:
                task = item
                break
        if not task:
            return jsonify({"ok": False, "error": "任务未找到"}), 404

        log_line = diff_log or _build_diff_log(quality_score)
        local_log = _append_local_log(task, log_line)
        update_task_fields(rid, note_content=note_content, modification_log=local_log)

        feishu_result = {"attempted": False, "ok": False, "error": "missing xhs_record_id"}
        xhs_record_id = task.get("xhs_record_id")
        if xhs_record_id:
            client = FeishuClient()
            cfg = get_feishu_config()
            xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
            if xhs_table_id and client.is_configured():
                patch = {}
                if title:
                    patch["小红书标题模板"] = title
                if body:
                    patch["正文开头模板"] = body
                if tags:
                    patch["热门标签推荐"] = tags
                if cta:
                    patch["互动话术模板"] = cta

                try:
                    if patch:
                        client.update_record_in_table(xhs_table_id, xhs_record_id, patch)
                    log_ok = client.save_modification_log(
                        xhs_table_id,
                        xhs_record_id,
                        _diff_log_for_feishu(log_line),
                        _score_total(quality_score),
                    )
                    feishu_result = {"attempted": True, "ok": bool(log_ok), "error": None if log_ok else "log write failed"}
                except Exception as e:
                    feishu_result = {"attempted": True, "ok": False, "error": str(e)}
            else:
                feishu_result = {"attempted": False, "ok": False, "error": "feishu not configured"}

        return jsonify({"ok": True, "data": {"saved": True, "feishu": feishu_result}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-generate")
def batch_generate():
    try:
        data = request.get_json(force=True) or {}
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "record_ids 为空"}), 400

        from scripts.queue_manager import get_queue
        result = get_queue(per_page=9999)
        generated = []
        for item in result.get("items", []):
            if item.get("record_id") in record_ids and item.get("note_content"):
                generated.append({
                    "record_id": item["record_id"],
                    "work_name": item.get("work_name", ""),
                    "note_content": item["note_content"],
                })

        return jsonify({"ok": True, "data": {"generated": len(generated), "notes": generated}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/score")
def rescore_note(rid):
    try:
        from scripts.queue_manager import get_queue, update_task_fields
        result = get_queue(per_page=9999)
        note_text = ""
        target_task = None
        for item in result.get("items", []):
            if item.get("record_id") == rid and item.get("note_content"):
                note_text = item["note_content"]
                target_task = item
                break

        if not note_text:
            return jsonify({"ok": False, "error": "笔记内容为空"}), 400

        account_strategy = get_account_strategy(target_task.get("account_strategy_id") if target_task else None)
        score_result = score_note(note_text, account_strategy=account_strategy)
        update_task_fields(rid, quality_score=score_result)
        return jsonify({"ok": True, "data": score_result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _compose_note(title, body, tags, cta):
    clean_tags = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]
    parts = []
    if title:
        parts.append(f"# {title}")
    if body:
        parts.append(str(body).strip())
    if cta:
        parts.append(f"互动话术：{cta}")
    if clean_tags:
        parts.append("标签：" + " ".join(f"#{tag}" for tag in clean_tags))
    return "\n\n".join(parts).strip()


def _build_diff_log(quality_score):
    from datetime import datetime

    return (
        f"{datetime.now().strftime('%Y%m%d %H:%M')} | "
        "字段: 标题/正文/标签 | 说明: 人工修改 | "
        f"评分:{_score_total(quality_score)}"
    )


def _append_local_log(task, log_line):
    current = str(task.get("modification_log") or "").strip()
    return log_line if not current else f"{current}\n{log_line}"


def _diff_log_for_feishu(log_line):
    parts = [p.strip() for p in str(log_line or "").split("|")]
    if len(parts) >= 3:
        return " | ".join(parts[1:-1])
    return str(log_line or "").strip()


def _score_total(score):
    if isinstance(score, dict):
        return score.get("total", 0)
    try:
        return int(score)
    except (TypeError, ValueError):
        return 0
