from flask import Blueprint, jsonify, render_template

from scripts.queue_manager import get_queue

bp = Blueprint("web_topic_pool", __name__)


@bp.get("/topic-pool")
def topic_pool_page():
    """选题池页面"""
    return render_template("topic_pool.html", active_page="topic_pool")


@bp.get("/api/topic-pool/stats")
def topic_pool_stats():
    """顶部 KPI 统计"""
    try:
        items = get_queue(per_page=9999).get("items", [])
        today_prefix = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        pending = [i for i in items if i.get("status") == "pending"]
        today_added = [i for i in items
                       if str(i.get("created_at", "")).startswith(today_prefix)]
        scores = [i.get("quality_score") for i in items
                  if i.get("quality_score") and i.get("quality_score") >= 80]
        return jsonify({
            "ok": True,
            "data": {
                "pending_topics": len(pending),
                "today_added": len(today_added),
                "high_potential": len(scores),
                "selected_count": 0,
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
