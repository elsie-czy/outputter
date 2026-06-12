from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import get_queue, enqueue_works
from scripts.local_data_manager import (
    get_work_mode, get_local_topics, sync_topics_from_feishu,
    get_local_results, get_pending_archive_count, archive_to_feishu,
    save_result_to_local
)

bp = Blueprint("web_topic_pool", __name__)


@bp.get("/topic-pool")
def topic_pool_page():
    """选题池页面"""
    return render_template("topic_pool.html", active_page="topic-pool", page_title="选题池")


@bp.get("/api/topic-pool/stats")
def topic_pool_stats():
    """顶部 KPI 统计"""
    try:
        mode = get_work_mode()
        
        if mode == "owner":
            # owner 模式：从本地读取
            items = get_local_topics()
        else:
            # client 模式：从队列读取
            items = get_queue(per_page=9999).get("items", [])
        
        today_prefix = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        pending = [i for i in items if i.get("status") in ("pending", "waiting", None)]
        today_added = [i for i in items
                       if str(i.get("created_at", "")).startswith(today_prefix)
                       or str(i.get("synced_at", "")).startswith(today_prefix)]
        scores = [i.get("quality_score") for i in items
                  if i.get("quality_score") and i.get("quality_score") >= 80]
        
        # 待归档数量
        pending_archive = get_pending_archive_count() if mode == "owner" else 0
        
        return jsonify({
            "ok": True,
            "data": {
                "pending_topics": len(pending),
                "today_added": len(today_added),
                "high_potential": len(scores),
                "selected_count": 0,
                "pending_archive": pending_archive,
                "work_mode": mode,
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/topic-pool/list")
def topic_pool_list():
    """获取选题列表"""
    try:
        mode = get_work_mode()
        
        if mode == "owner":
            # owner 模式：从本地读取
            items = get_local_topics()
            source = "local"
        else:
            # client 模式：从飞书读取
            from scripts.feishu_client import FeishuClient
            from scripts.feishu_config import get_feishu_config
            
            client = FeishuClient()
            if not client.is_configured():
                # 飞书未配置，降级使用本地队列
                items = get_queue(per_page=9999, status="pending").get("items", [])
                return jsonify({"ok": True, "data": {"items": items, "source": "local"}})
            
            config = get_feishu_config()
            topic_table_id = config.get("related_table_ids", {}).get("选题库", "")
            if not topic_table_id:
                return jsonify({"ok": False, "error": "选题库表ID未配置"}), 500
            
            records = client.list_records(topic_table_id, page_size=500)
            
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
            source = "feishu"
        
        return jsonify({"ok": True, "data": {"items": items, "source": source}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/topic-pool/sync")
def topic_pool_sync():
    """同步飞书选题到本地（owner 模式）"""
    try:
        mode = get_work_mode()
        if mode != "owner":
            return jsonify({"ok": False, "error": "仅 owner 模式支持同步"}), 400
        
        result = sync_topics_from_feishu()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/topic-pool/pending-archive")
def topic_pool_pending_archive():
    """获取待归档记录"""
    try:
        results = get_local_results(status="pending")
        return jsonify({"ok": True, "data": {"items": results, "count": len(results)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/topic-pool/archive")
def topic_pool_archive():
    """归档到飞书"""
    try:
        data = request.get_json() or {}
        record_ids = data.get("record_ids")
        result = archive_to_feishu(record_ids)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
