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
            # owner 模式：从本地读取，过滤已拆解
            items = get_local_topics()
            # 从本地结果文件判断拆解状态
            deconstructed_names = set()
            try:
                results = get_local_results()
                for r in results:
                    n = (r.get("work_name") or "").strip()
                    if n:
                        deconstructed_names.add(n)
            except Exception:
                pass
            # 补充拆解状态字段
            for item in items:
                raw = item.get("是否拆解", "")
                if not raw and item.get("work_name", "") in deconstructed_names:
                    raw = "已拆解"
                item["is_deconstructed"] = _is_deconstructed(raw) or (item.get("work_name", "") in deconstructed_names)
                item["deconstruct_status_label"] = raw or ("已拆解" if item.get("work_name", "") in deconstructed_names else "")
            # 默认过滤已拆解；?show_all=1 可查看全部
            if request.args.get("show_all") != "1":
                items = [i for i in items if not i.get("is_deconstructed")]
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
                # 默认过滤已拆解作品；?show_all=1 可查看全部
                if is_deconstructed and request.args.get("show_all") != "1":
                    continue
                item = {
                    "record_id": r.get("record_id", ""),
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
