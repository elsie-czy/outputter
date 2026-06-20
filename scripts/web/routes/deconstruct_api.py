from flask import Blueprint, jsonify, request

from scripts.queue_manager import (
    get_queue, enqueue_works, update_status, batch_update_status,
    retry_task, get_stats, get_next_pending,
)

bp = Blueprint("web_deconstruct_api", __name__, url_prefix="/api/deconstruct")


@bp.get("/queue")
def queue_list():
    """获取队列列表，支持筛选"""
    try:
        status = request.args.get("status", "").strip() or None
        platform = request.args.get("platform", "").strip() or None
        category = request.args.get("category", "").strip() or None
        q = request.args.get("q", "").strip() or None
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))
        result = get_queue(status=status, platform=platform,
                           category=category, q=q, page=page, per_page=per_page)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-start")
def batch_start():
    """批量开启拆文"""
    try:
        data = request.get_json(force=True) or {}
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "record_ids 为空"}), 400
        count = batch_update_status(record_ids, "processing")
        return jsonify({"ok": True, "data": {"updated": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-complete")
def batch_complete():
    """批量标记完成"""
    try:
        data = request.get_json(force=True) or {}
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "record_ids 为空"}), 400
        count = batch_update_status(record_ids, "done")
        return jsonify({"ok": True, "data": {"updated": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-enqueue")
def batch_enqueue():
    """批量入队（自动从本地选题库补全简介/取向）"""
    try:
        data = request.get_json(force=True) or {}
        works = data.get("works", [])
        if not works:
            return jsonify({"ok": False, "error": "works 为空"}), 400

        # 安全网：从本地选题库补全简介/取向
        from scripts.local_data_manager import get_local_topics
        local_map = {}
        try:
            local_items = get_local_topics()
            for item in local_items:
                key = (item.get("work_name", ""), item.get("author", ""))
                local_map[key] = item
        except Exception:
            pass

        enriched = []
        for w in works:
            w = dict(w)  # 浅拷贝，避免修改原数据
            if not w.get("简介"):
                key = (w.get("作品名称", ""), w.get("作者", ""))
                local_item = local_map.get(key)
                if local_item:
                    w["简介"] = local_item.get("synopsis", "")
                    w["取向"] = local_item.get("orientation", "")
            enriched.append(w)

        count = enqueue_works(enriched)
        return jsonify({"ok": True, "data": {"enqueued": count}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/retry")
def retry_single(rid):
    """重试失败任务"""
    try:
        ok = retry_task(rid)
        return jsonify({"ok": ok, "data": {"retried": ok}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/<rid>/result")
def task_result(rid):
    """获取单个拆文结果"""
    result = get_queue()
    for item in result.get("items", []):
        if item.get("record_id") == rid:
            return jsonify({"ok": True, "data": item})
    return jsonify({"ok": False, "error": "任务未找到"}), 404


@bp.get("/stats")
def queue_stats():
    """队列统计"""
    try:
        stats = get_stats()
        return jsonify({"ok": True, "data": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/<rid>/assets")
def task_assets(rid):
    """获取任务的图片和视频脚本生成状态"""
    try:
        import os
        from scripts.config import PATHS
        from scripts.utils import read_jsonl

        # 图片队列状态
        image_jobs = read_jsonl(os.path.join(PATHS["logs"], "image_jobs.jsonl"))
        image_results = read_jsonl(os.path.join(PATHS["logs"], "image_job_results.jsonl"))

        pending = 0
        done = 0
        failed = 0
        for j in image_jobs:
            if j.get("xhs_record_id") == rid:
                pending += 1
        for r in image_results:
            if str(r.get("xhs_record_id", "")) == rid:
                if r.get("status") == "updated":
                    done += 1
                elif r.get("status") == "failed":
                    failed += 1

        return jsonify({"ok": True, "data": {
            "record_id": rid,
            "image_status": {
                "pending": pending,
                "done": done,
                "failed": failed,
                "total": pending + done + failed,
            },
            "video_status": "not_generated",
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
