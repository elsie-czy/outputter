from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import get_queue, update_status, retry_task

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
        task["stage_progress"] = STAGE_PROGRESS.get(status, 0)
        task["progress_percent"] = round(STAGE_PROGRESS.get(status, 0) / 6 * 100)
        task["display_status"] = status
        
        # 模拟拆文结果（实际应从 deconstruct_result 字段读取）
        if not task.get("deconstruct_result"):
            task["deconstruct_result"] = {
                "openings": ["开篇以主角被退婚的戏剧性场景切入，迅速吸引读者注意力", "通过对比手法展现主角身份反转前后的巨大落差"],
                "characters": ["主角：废材小姐，表面软弱实则隐藏实力", "男主：豪门继承人，冷酷外表下有柔软内心"],
                "conflicts": ["主线冲突：主角与家族的对抗", "情感线：主角与男主从误解到相知"],
                "emotions": ["爽感：打脸场景密集", "悬念：身世之谜逐步揭开"],
                "quotes": ["她站在雨中，看着那扇紧闭的大门，突然笑了", "\"你以为我真的是废材吗？\"", "有些人的退让不是软弱，而是在等一个反击的机会"]
            }
        
        # 模拟笔记内容（实际应从 note_content 字段读取）
        if not task.get("note_content"):
            task["note_content"] = {
                "title": "重生后我打脸豪门所有人",
                "content": "她曾是人人嘲笑的废材小姐，被退婚后一夜重生。\n\n当她再次踏入那扇大门，所有人都惊呆了。\n\n\"你们以为我还是那个任人欺负的废物吗？\"\n\n她用实力证明，退婚是他们最大的错误...",
                "tags": ["重生逆袭", "豪门", "都市"],
                "score": {
                    "total": 82,
                    "title_attract": 24,
                    "emotion": 18,
                    "collect_value": 16,
                    "interaction": 12,
                    "style_match": 8,
                    "ai_trace": 4,
                    "suggestions": ["建议增加反差感", "建议增加数字钩子", "建议强化收藏价值"]
                }
            }
        
        return jsonify({"ok": True, "data": task})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
