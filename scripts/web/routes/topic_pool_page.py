from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import get_queue, enqueue_works
from scripts.local_data_manager import (
    get_work_mode, get_local_topics, sync_topics_from_feishu,
    get_local_results, get_pending_archive_count, archive_to_feishu,
    save_result_to_local
)
from scripts.feishu_reader import _is_deconstructed
pass  # module loaded

bp = Blueprint("web_topic_pool", __name__)

ACTIVE_QUEUE_STATUSES = {
    "pending",
    "waiting",
    "processing",
    "deconstructing",
    "generating_note",
    "ai_scoring",
    "human_review",
    "generating_image",
    "paused",
}


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
        show_all = request.args.get("show_all") == "1"
        queued_items = get_queue(per_page=9999).get("items", [])
        queue_by_id = {
            str(i.get("record_id") or "").strip(): i
            for i in queued_items
            if str(i.get("record_id") or "").strip()
            and str(i.get("status") or "").strip() in ACTIVE_QUEUE_STATUSES
        }
        
        if mode == "owner":
            # owner 模式：从本地读取，过滤已拆解
            items = get_local_topics()
            # 飞书「是否拆解」是重新出现/隐藏选题的主开关；
            # 本地 results 只作为历史提示，不再覆盖用户在飞书里改回「否」的操作。
            local_result_names = set()
            try:
                results = get_local_results()
                for r in results:
                    n = (r.get("work_name") or "").strip()
                    if n:
                        local_result_names.add(n)
            except Exception:
                pass
            for item in items:
                rid = str(item.get("record_id") or "").strip()
                queue_item = queue_by_id.get(rid)
                feishu_deconstructed = _is_deconstructed(item.get("是否拆解"))
                has_local_result = item.get("work_name", "") in local_result_names
                item["is_deconstructed"] = feishu_deconstructed
                item["deconstruct_status_label"] = item.get("是否拆解", "")
                item["has_local_result"] = has_local_result
                item["is_in_queue"] = bool(queue_item)
                item["queue_status"] = queue_item.get("status", "") if queue_item else ""
            # 默认过滤已拆解；?show_all=1 可查看全部
            if not show_all:
                items = [i for i in items if not i.get("is_deconstructed") and not i.get("is_in_queue")]
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
            pass  # client mode: got records from feishu
            
            items = []
            for r in records:
                fields = r.get("fields", {}) or {}
                is_deconstructed = _is_deconstructed(fields.get("是否拆解"))
                rid = str(r.get("record_id", "") or "").strip()
                queue_item = queue_by_id.get(rid)
                # 默认过滤已拆解作品；?show_all=1 可查看全部
                if (is_deconstructed or queue_item) and not show_all:
                    continue
                item = {
                    "record_id": rid,
                    "work_name": fields.get("作品名称", ""),
                    "author": fields.get("作者", ""),
                    "platform": fields.get("平台", ""),
                    "category": fields.get("分类", ""),
                    "synopsis": fields.get("简介", ""),
                    "orientation": fields.get("取向", ""),
                    "word_count": fields.get("字数", 0),
                    "favorites": fields.get("收藏", 0),
                    "likes": fields.get("点赞", 0),
                    "monthly_votes": fields.get("月票", 0),
                    "recommend_votes": fields.get("推荐票", 0),
                    "comments": fields.get("评论", 0),
                    "rank": fields.get("排名", 0),
                    "quality_score": fields.get("评分", 0),
                    "status": fields.get("状态", "pending"),
                    "is_deconstructed": is_deconstructed,
                    "deconstruct_status_label": fields.get("是否拆解", ""),
                    "is_in_queue": bool(queue_item),
                    "queue_status": queue_item.get("status", "") if queue_item else "",
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
