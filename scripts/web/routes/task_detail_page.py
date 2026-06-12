from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import get_queue, update_status, retry_task, get_task_progress, is_task_truly_done

bp = Blueprint("web_task_detail", __name__)


@bp.get("/task/<task_id>")
def task_detail_page(task_id):
    """任务详情页面"""
    return render_template("task_detail.html", task_id=task_id, page_title="任务详情")


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
        if not deconstruct_result or deconstruct_result.get("缓存"):
            # 没有真实拆文结果或缓存命中
            task["deconstruct_result"] = None
        else:
            # 转换字段名（中文 -> 英文）
            task["deconstruct_result"] = {
                "openings": deconstruct_result.get("开篇套路", []),
                "characters": _format_characters(deconstruct_result.get("人物设定", {})),
                "conflicts": _format_conflicts(deconstruct_result.get("冲突设计", {})),
                "emotions": deconstruct_result.get("情绪触发", []),
                "quotes": deconstruct_result.get("金句", []),
            }
        
        # 处理笔记内容
        note_content = task.get("note_content")
        if not note_content or note_content.startswith("（缓存"):
            # 没有真实笔记内容
            task["note_content"] = None
        else:
            # 笔记内容是 markdown 字符串
            task["note_content"] = {
                "title": _extract_title(note_content),
                "content": note_content,
                "tags": _extract_tags(note_content),
                "score": None,  # 评分需要单独计算
            }
        
        return jsonify({"ok": True, "data": task})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _format_characters(characters):
    """格式化人物设定"""
    if isinstance(characters, dict):
        result = []
        for role, desc in characters.items():
            result.append(f"{role}：{desc}")
        return result
    return characters if isinstance(characters, list) else []


def _format_conflicts(conflicts):
    """格式化冲突设计"""
    if isinstance(conflicts, dict):
        result = []
        for level, desc in conflicts.items():
            result.append(f"{level}：{desc}")
        return result
    return conflicts if isinstance(conflicts, list) else []


def _extract_title(note_content):
    """从笔记内容提取标题"""
    if not note_content:
        return ""
    lines = note_content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line and not line.startswith("#"):
            return line[:50]
    return ""


def _extract_tags(note_content):
    """从笔记内容提取标签"""
    if not note_content:
        return []
    tags = []
    import re
    # 查找 # 标签
    matches = re.findall(r'#(\w+)', note_content)
    tags.extend(matches[:5])
    return tags


@bp.post("/api/task/<task_id>/regenerate-note")
def regenerate_note(task_id):
    """重新生成笔记"""
    try:
        # TODO: 调用 model_adapter.generate_note()
        return jsonify({"ok": True, "message": "笔记重新生成中..."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/rescore")
def rescore_note(task_id):
    """重新评分"""
    try:
        # TODO: 调用 quality_scorer.score_note()
        return jsonify({"ok": True, "message": "重新评分中..."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/save-draft")
def save_draft(task_id):
    """保存草稿"""
    try:
        data = request.get_json()
        # TODO: 写入飞书笔记库
        return jsonify({"ok": True, "message": "草稿已保存"})
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
    """重试任务"""
    try:
        success = retry_task(task_id)
        return jsonify({"ok": success})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
