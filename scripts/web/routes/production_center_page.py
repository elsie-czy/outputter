from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import (
    get_queue, get_stats, pause_task, cancel_task, retry_task,
    batch_pause_tasks, batch_retry_tasks, batch_cancel_tasks,
    STATUS_WAITING, STATUS_DECONSTRUCTING, STATUS_GENERATING_NOTE,
    STATUS_AI_SCORING, STATUS_HUMAN_REVIEW, STATUS_GENERATING_IMAGE,
    STATUS_DONE, STATUS_FAILED, STATUS_PAUSED, STATUS_CANCELLED,
    STAGE_PROGRESS, STAGE_LABELS
)

bp = Blueprint("web_production_center", __name__)


@bp.get("/production-center")
def production_center_page():
    """生产中心页面"""
    return render_template("production_center.html", active_page="production", page_title="生产中心")


@bp.get("/api/production/stats")
def production_stats():
    """生产中心统计"""
    try:
        items = get_queue(per_page=9999).get("items", [])
        today_prefix = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        
        # 按状态统计（兼容旧的 pending 状态）
        running = [i for i in items if i.get("status") in (
            STATUS_DECONSTRUCTING, STATUS_GENERATING_NOTE, STATUS_AI_SCORING,
            STATUS_HUMAN_REVIEW, STATUS_GENERATING_IMAGE, "processing"
        )]
        waiting = [i for i in items if i.get("status") in (STATUS_WAITING, STATUS_PAUSED, "pending", "retry")]
        today_completed = [i for i in items 
                          if i.get("status") in (STATUS_DONE, "done")
                          and str(i.get("completed_at", "")).startswith(today_prefix)]
        today_failed = [i for i in items 
                       if i.get("status") in (STATUS_FAILED, "failed")
                       and str(i.get("created_at", "")).startswith(today_prefix)]
        
        # 平均处理时长（分钟）
        completed_with_time = [i for i in items 
                              if i.get("status") in (STATUS_DONE, "done")
                              and i.get("processing_start") 
                              and i.get("completed_at")]
        avg_duration = 0
        if completed_with_time:
            from datetime import datetime
            durations = []
            for i in completed_with_time[-100:]:  # 最近100条
                try:
                    start = datetime.strptime(i["processing_start"], "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(i["completed_at"], "%Y-%m-%d %H:%M:%S")
                    durations.append((end - start).total_seconds() / 60)
                except:
                    pass
            if durations:
                avg_duration = round(sum(durations) / len(durations), 1)
        
        # 资源使用率（今日token消耗 / 预算）
        token_used = len(running) * 3000 + len(today_completed) * 3000
        token_budget = 5000000
        resource_usage = min(100, round(token_used / token_budget * 100))
        
        return jsonify({
            "ok": True,
            "data": {
                "processing": len(running),
                "pending": len(waiting),
                "today_completed": len(today_completed),
                "today_failed": len(today_failed),
                "avg_duration": avg_duration,
                "resource_usage": resource_usage,
                "token_used": token_used,
                "token_budget": token_budget,
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/production/list")
def production_list():
    """生产任务列表"""
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        status = request.args.get("status")
        q = request.args.get("q")
        
        result = get_queue(page=page, per_page=per_page, status=status, q=q)
        
        # 添加阶段信息
        for item in result.get("items", []):
            # 兼容旧的 pending 状态
            item_status = item.get("status", "")
            if item_status == "pending":
                item_status = "waiting"
            
            item["stage_label"] = STAGE_LABELS.get(item_status, item_status or "未知")
            item["stage_progress"] = STAGE_PROGRESS.get(item_status, 0)
            item["progress_percent"] = round(STAGE_PROGRESS.get(item_status, 0) / 6 * 100)
            item["display_status"] = item_status
        
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/pause")
def production_pause():
    """暂停任务"""
    try:
        data = request.get_json()
        record_id = data.get("record_id")
        if not record_id:
            return jsonify({"ok": False, "error": "缺少 record_id"}), 400
        success = pause_task(record_id)
        return jsonify({"ok": success})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/retry")
def production_retry():
    """重试任务"""
    try:
        data = request.get_json()
        record_id = data.get("record_id")
        if not record_id:
            return jsonify({"ok": False, "error": "缺少 record_id"}), 400
        success = retry_task(record_id)
        return jsonify({"ok": success})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/cancel")
def production_cancel():
    """终止任务"""
    try:
        data = request.get_json()
        record_id = data.get("record_id")
        if not record_id:
            return jsonify({"ok": False, "error": "缺少 record_id"}), 400
        success = cancel_task(record_id)
        return jsonify({"ok": success})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/batch-pause")
def production_batch_pause():
    """批量暂停"""
    try:
        data = request.get_json()
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "缺少 record_ids"}), 400
        count = batch_pause_tasks(record_ids)
        return jsonify({"ok": True, "data": {"paused": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/batch-retry")
def production_batch_retry():
    """批量重试"""
    try:
        data = request.get_json()
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "缺少 record_ids"}), 400
        count = batch_retry_tasks(record_ids)
        return jsonify({"ok": True, "data": {"retried": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/production/batch-cancel")
def production_batch_cancel():
    """批量终止"""
    try:
        data = request.get_json()
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "缺少 record_ids"}), 400
        count = batch_cancel_tasks(record_ids)
        return jsonify({"ok": True, "data": {"cancelled": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
