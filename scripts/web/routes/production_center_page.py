from flask import Blueprint, jsonify, render_template

from scripts.queue_manager import get_queue

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
        
        processing = [i for i in items if i.get("status") == "processing"]
        pending = [i for i in items if i.get("status") == "pending"]
        
        today_prefix = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        today_completed = [i for i in items 
                          if i.get("status") == "completed" 
                          and str(i.get("completed_at", "")).startswith(today_prefix)]
        today_failed = [i for i in items 
                       if i.get("status") == "failed" 
                       and str(i.get("created_at", "")).startswith(today_prefix)]
        
        # 平均处理时长（分钟）
        completed_with_time = [i for i in items 
                              if i.get("status") == "completed" 
                              and i.get("processing_start") 
                              and i.get("completed_at")]
        avg_duration = 0
        if completed_with_time:
            from datetime import datetime
            durations = []
            for i in completed_with_time:
                try:
                    start = datetime.strptime(i["processing_start"], "%Y-%m-%d %H:%M:%S")
                    end = datetime.strptime(i["completed_at"], "%Y-%m-%d %H:%M:%S")
                    durations.append((end - start).total_seconds() / 60)
                except:
                    pass
            if durations:
                avg_duration = round(sum(durations) / len(durations), 1)
        
        return jsonify({
            "ok": True,
            "data": {
                "processing": len(processing),
                "pending": len(pending),
                "today_completed": len(today_completed),
                "today_failed": len(today_failed),
                "avg_duration": avg_duration,
                "resource_usage": len(processing) * 10,  # 简单估算
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/production/list")
def production_list():
    """生产任务列表"""
    try:
        from flask import request
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        status = request.args.get("status")
        q = request.args.get("q")
        
        result = get_queue(page=page, per_page=per_page, status=status, q=q)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
