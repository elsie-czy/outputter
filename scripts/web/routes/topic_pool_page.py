from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import get_queue, enqueue_works
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config

bp = Blueprint("web_topic_pool", __name__)


@bp.get("/topic-pool")
def topic_pool_page():
    """选题池页面"""
    return render_template("topic_pool.html", active_page="topic-pool", page_title="选题池")


@bp.get("/api/topic-pool/stats")
def topic_pool_stats():
    """顶部 KPI 统计"""
    try:
        items = get_queue(per_page=9999).get("items", [])
        today_prefix = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        pending = [i for i in items if i.get("status") in ("pending", "waiting")]
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


@bp.get("/api/topic-pool/list")
def topic_pool_list():
    """从飞书读取选题列表"""
    try:
        client = FeishuClient()
        if not client.is_configured():
            # 飞书未配置，降级使用本地队列
            items = get_queue(per_page=9999, status="pending").get("items", [])
            return jsonify({"ok": True, "data": {"items": items, "source": "local"}})
        
        # 从飞书选题库读取
        config = get_feishu_config()
        topic_table_id = config.get("related_table_ids", {}).get("选题库", "")
        if not topic_table_id:
            return jsonify({"ok": False, "error": "选题库表ID未配置"}), 500
        
        records = client.list_records(topic_table_id, page_size=500)
        
        # 转换为前端需要的格式
        items = []
        for r in records:
            fields = r.get("fields", {}) or {}
            item = {
                "record_id": r.get("record_id", ""),
                "work_name": fields.get("作品名称", ""),
                "author": fields.get("作者", ""),
                "platform": fields.get("平台", ""),
                "category": fields.get("分类", ""),
                "word_count": fields.get("字数", 0),
                "favorites": fields.get("收藏", 0),
                "likes": fields.get("点赞", 0),
                "monthly_votes": fields.get("月票", 0),
                "recommend_votes": fields.get("推荐票", 0),
                "comments": fields.get("评论", 0),
                "rank": fields.get("排名", 0),
                "quality_score": fields.get("评分", 0),
                "status": fields.get("状态", "pending"),
            }
            items.append(item)
        
        return jsonify({"ok": True, "data": {"items": items, "source": "feishu"}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
