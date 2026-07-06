from datetime import datetime
import re

from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import (
    QUEUE_FILE,
    get_queue,
    get_task_progress,
    is_task_truly_done,
    read_jsonl,
    update_status,
    update_task_fields,
    write_jsonl,
)
from scripts.data_normalizer import normalize_feishu_record, normalize_for_frontend
from scripts.deconstruct_daily import build_xhs_note
from scripts.generation_context import build_generation_context, context_counts
from scripts.model_adapter import analyze_work
from scripts.quality_scorer import score_note

bp = Blueprint("web_task_detail", __name__)


@bp.get("/task/<task_id>")
def task_detail_page(task_id):
    """任务详情页面"""
    return render_template(
        "task_detail.html",
        task_id=task_id,
        page_title="任务详情",
        header_back_href="/production-center",
        header_back_text="返回生产中心",
        header_badge="ID: " + task_id,
    )


@bp.get("/api/task/<task_id>")
def task_detail_api(task_id):
    """获取任务详情"""
    try:
        items = get_queue(per_page=9999).get("items", [])
        task = None
        for i in items:
            if i.get("record_id") == task_id:
                task = i
                break
        
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        
        # 添加阶段信息
        from scripts.queue_manager import STAGE_PROGRESS, STAGE_LABELS
        status = task.get("status", "")
        if status == "pending":
            status = "waiting"
        
        task["stage_label"] = STAGE_LABELS.get(status, status or "未知")
        task["stage_progress"] = get_task_progress(task)
        task["progress_percent"] = round(get_task_progress(task) / 6 * 100)
        task["display_status"] = status
        task["truly_done"] = is_task_truly_done(task)
        task["has_images"] = bool(task.get("images", {}).get("cover"))
        
        # 步骤时间
        task["step_times"] = task.get("step_times", {})
        
        # 处理拆文结果
        deconstruct_result = task.get("deconstruct_result")
        if not deconstruct_result:
            task["deconstruct_result"] = None
        elif deconstruct_result.get("缓存") and not deconstruct_result.get("开篇套路"):
            task["deconstruct_result"] = None
        else:
            task["deconstruct_result"] = normalize_for_frontend(
                normalize_feishu_record(deconstruct_result, source="main")
            )
        
        # 处理笔记内容
        note_content = task.get("note_content", "")
        title_options = task.get("title_options", [])  # 新增：独立的备选标题字段
        if not note_content or note_content.startswith("（缓存") or len(str(note_content).strip()) < 10:
            # 从拆文结果中提取笔记内容
            dr = task.get("deconstruct_result") or {}
            xhs = dr.get("小红书包装") or {}
            title = xhs.get("小红书标题模板", "") or ""
            body = xhs.get("正文开头模板", "") or ""
            if not title and not body:
                title = task.get('work_name', '') + ' 拆解笔记'
                body = "请运行拆文任务获取笔记内容"
            task["note_content"] = {
                "title": title,
                "content": body,
                "tags": [],
                "score": _format_score(task.get("quality_score")),
                "title_options": title_options if title_options else [],
            }
        else:
            # 笔记内容是 markdown 字符串
            note_text = str(note_content)
            task["note_content"] = {
                "title": _extract_title(note_text),
                "content": _extract_body(note_text),
                "tags": _extract_tags(note_text),
                "score": _format_score(task.get("quality_score")),
                "title_options": title_options if title_options else _extract_title_options(note_text),
            }
        task["modification_log"] = task.get("modification_log", "")
        
        return jsonify({"ok": True, "data": task})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _extract_title(note_content):
    """从笔记内容提取标题"""
    if not note_content:
        return ""
    lines = note_content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("【标题】"):
            return line.replace("【标题】", "", 1).strip()
        if line.startswith("标题："):
            return line.replace("标题：", "", 1).strip()
        if line.startswith("标题:"):
            return line.replace("标题:", "", 1).strip()
        if line and not line.startswith("#"):
            return line[:50]
    return ""


def _extract_body(note_content):
    """去掉【标题】行和【备选标题】区块，避免正文编辑框重复出现。"""
    if not note_content:
        return ""
    lines = str(note_content).splitlines()
    result = []
    skip_titles = False
    for line in lines:
        stripped = line.strip()
        # 跳过【标题】行
        if not result and (stripped.startswith("# ") or stripped.startswith("【标题】") or stripped.startswith("标题：") or stripped.startswith("标题:")):
            continue
        # 跳过【备选标题】区块
        if stripped.startswith("【备选标题】"):
            skip_titles = True
            continue
        if skip_titles and (stripped.startswith("  ") or re.match(r'^\d+\.\s', stripped)):
            continue
        skip_titles = False
        result.append(line)
    return "\n".join(result).lstrip()


def _extract_title_options(note_content):
    """从笔记内容提取备选标题列表（向后兼容旧数据）"""
    if not note_content:
        return []
    lines = str(note_content).splitlines()
    titles = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("【备选标题】"):
            in_section = True
            continue
        if in_section:
            if not stripped or stripped.startswith("【") or (not re.match(r'^\d+\.\s', stripped) and not stripped.startswith("  ")):
                break
            # 去除编号前缀
            title = re.sub(r'^\d+\.\s*', '', stripped.lstrip())
            if title:
                titles.append(title)
    return titles


def _extract_tags(note_content):
    """从笔记内容提取标签"""
    if not note_content:
        return []
    tags = []
    # 查找 # 标签
    matches = re.findall(r'#(\w+)', note_content)
    tags.extend(matches[:5])
    return tags


def _find_task(task_id):
    items = read_jsonl(QUEUE_FILE)
    for item in items:
        if item.get("record_id") == task_id:
            return item
    return None


def _format_score(score):
    if not isinstance(score, dict):
        return None
    suggestion = score.get("suggestion", "")
    return {
        "total": score.get("total", 0),
        "title_attract": score.get("title_appeal", 0),
        "emotion": score.get("emotion_density", 0),
        "collect_value": score.get("collection_value", 0),
        "interaction": score.get("interaction_guide", 0),
        "style_match": score.get("xhs_style_match", 0),
        "ai_trace": score.get("ai_trace", 0),
        "grade": score.get("grade", ""),
        "suggestions": [suggestion] if suggestion else [],
    }


def _compose_note(title, content, tags):
    title = str(title or "").strip()
    content = str(content or "").strip()
    clean_tags = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]
    parts = []
    if title:
        parts.append(f"# {title}")
    if content:
        parts.append(content)
    if clean_tags:
        parts.append("标签：" + " ".join(f"#{tag}" for tag in clean_tags))
    return "\n\n".join(parts).strip()


def _build_modification_log(task, new_note, quality_score):
    old_note = str(task.get("note_content") or "")
    changed = []
    if _extract_title(old_note) != _extract_title(new_note):
        changed.append("标题")
    if old_note.strip() != new_note.strip():
        changed.append("正文")
    if _extract_tags(old_note) != _extract_tags(new_note):
        changed.append("标签")
    if not changed:
        changed.append("草稿")
    total = 0
    if isinstance(quality_score, dict):
        total = quality_score.get("total", 0)
    return (
        f"{datetime.now().strftime('%Y%m%d %H:%M')} | "
        f"字段: {'/'.join(changed)} | 说明: 人工修改 | 评分:{total}"
    )


def _append_local_modification_log(task, log_line):
    current = str(task.get("modification_log") or "").strip()
    return log_line if not current else f"{current}\n{log_line}"


def _save_to_feishu_note(task, title, content, tags, log_line, score):
    xhs_record_id = task.get("xhs_record_id")
    if not xhs_record_id:
        return {"attempted": False, "ok": False, "error": "missing xhs_record_id"}
    try:
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config

        client = FeishuClient()
        cfg = get_feishu_config()
        xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not xhs_table_id or not client.is_configured():
            return {"attempted": False, "ok": False, "error": "feishu not configured"}

        patch = {}
        if title:
            patch["小红书标题模板"] = title
        if content:
            patch["正文开头模板"] = content
        if tags:
            patch["热门标签推荐"] = tags
        if patch:
            client.update_record_in_table(xhs_table_id, xhs_record_id, patch)
        log_ok = client.save_modification_log(
            xhs_table_id,
            xhs_record_id,
            _diff_log_for_feishu(log_line),
            score.get("total", 0) if isinstance(score, dict) else 0,
        )
        return {"attempted": True, "ok": bool(log_ok), "error": None if log_ok else "log write failed"}
    except Exception as e:
        return {"attempted": True, "ok": False, "error": str(e)}


def _diff_log_for_feishu(log_line):
    parts = [p.strip() for p in str(log_line or "").split("|")]
    if len(parts) >= 3:
        return " | ".join(parts[1:-1])
    return str(log_line or "").strip()


@bp.post("/api/task/<task_id>/regenerate-note")
def regenerate_note(task_id):
    """重新生成笔记"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        work = {
            "作品名称": task.get("work_name", ""),
            "作者": task.get("author", ""),
            "平台": task.get("platform", ""),
            "分类": task.get("category", ""),
        }
        generation_context = build_generation_context(task)
        analysis = analyze_work(work, **generation_context)
        note_text = build_xhs_note(work, analysis)
        score = score_note(note_text)
        updated = update_task_fields(
            task_id,
            deconstruct_result=analysis,
            note_content=note_text,
            quality_score=score,
        )
        if not updated:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        return jsonify({
            "ok": True,
            "data": {
                "note_content": note_text,
                "quality_score": score,
                "generation_context": context_counts(generation_context),
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/rescore")
def rescore_note(task_id):
    """重新评分"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        note_text = str((request.get_json(silent=True) or {}).get("note_content") or task.get("note_content") or "")
        if not note_text.strip():
            return jsonify({"ok": False, "error": "笔记内容为空"}), 400
        score = score_note(note_text)
        update_task_fields(task_id, quality_score=score)
        return jsonify({"ok": True, "data": {"quality_score": score, "score": _format_score(score)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/save-draft")
def save_draft(task_id):
    """保存草稿"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        data = request.get_json(force=True) or {}
        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", [])
        note_text = _compose_note(title, content, tags)
        if not note_text:
            return jsonify({"ok": False, "error": "草稿内容为空"}), 400

        score = task.get("quality_score") if isinstance(task.get("quality_score"), dict) else {}
        log_line = _build_modification_log(task, note_text, score)
        local_log = _append_local_modification_log(task, log_line)
        feishu_result = _save_to_feishu_note(task, title, content, tags, log_line, score)
        update_task_fields(
            task_id,
            note_content=note_text,
            modification_log=local_log,
        )
        return jsonify({
            "ok": True,
            "data": {
                "saved": True,
                "modification_log": log_line,
                "feishu": feishu_result,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/approve")
def approve_task(task_id):
    """保存并通过审核"""
    try:
        # 更新状态为已完成
        update_status(task_id, "done")
        return jsonify({"ok": True, "message": "已通过审核"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/retry")
def retry_task_api(task_id):
    """重试任务——重置为 pending 强制重新拆文"""
    try:
        # queue_manager.retry_task 只处理 failed，这里强制重置
        items = read_jsonl(QUEUE_FILE)
        for i in items:
            if i.get("record_id") == task_id:
                i["status"] = "pending"
                i["error"] = None
                i["retry_count"] = i.get("retry_count", 0) + 1
                i["deconstruct_result"] = None
                i["note_content"] = None
                i["quality_score"] = None
                i["images"] = {}
                write_jsonl(QUEUE_FILE, items)
                return jsonify({"ok": True, "data": {"retried": True, "message": "已重置，worker 将重新拆文"}})
        return jsonify({"ok": False, "error": "任务未找到"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 图片生成策略 API ────────────────────────────────────────────────────
import os as _os
from pathlib import Path as _Path

_STRATEGY_CONFIG_DIR = _Path(__file__).resolve().parent.parent.parent.parent / "data" / "config"
_STRATEGY_CONFIG_FILE = _STRATEGY_CONFIG_DIR / "image_strategy.json"

def _read_strategy_config():
    if not _STRATEGY_CONFIG_FILE.exists():
        return {"strategy": "ai", "style": "warm", "count": 3, "provider": _os.getenv("IMAGE_PROVIDER", "jimeng")}
    import json as _json
    with open(_STRATEGY_CONFIG_FILE, "r", encoding="utf-8") as _f:
        config = _json.load(_f)
    config.setdefault("strategy", "ai")
    config.setdefault("style", "warm")
    config.setdefault("count", 3)
    config.setdefault("provider", _os.getenv("IMAGE_PROVIDER", "jimeng"))
    return config

def _write_strategy_config(data: dict):
    _STRATEGY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(_STRATEGY_CONFIG_FILE, "w", encoding="utf-8") as _f:
        _json.dump(data, _f, ensure_ascii=False, indent=2)


@bp.get("/api/config/image_strategy")
def get_image_strategy():
    """获取当前图片生成策略"""
    try:
        return jsonify(_read_strategy_config())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/config/image_strategy")
def set_image_strategy():
    """更新图片生成策略（需重启 worker 生效）"""
    try:
        data = request.get_json(force=True) or {}
        strategy = data.get("strategy", "ai").strip().lower()
        if strategy not in ("ai", "html_card", "auto"):
            return jsonify({"ok": False, "error": "strategy must be ai, html_card or auto"}), 400
        provider = data.get("provider", _os.getenv("IMAGE_PROVIDER", "jimeng")).strip().lower()
        if provider not in ("jimeng", "siliconflow", "liblib", "mock"):
            return jsonify({"ok": False, "error": "provider must be jimeng, siliconflow, liblib or mock"}), 400
        config = {
            "strategy": strategy,
            "style": data.get("style", "warm").strip(),
            "count": int(data.get("count", 3) or 3),
            "provider": provider,
        }
        _write_strategy_config(config)
        return jsonify({"ok": True, "data": config, "warning": "需重启 jimeng_worker 生效"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
