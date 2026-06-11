from flask import Blueprint, jsonify, request

bp = Blueprint("web_image_api", __name__, url_prefix="/api/image")


@bp.get("/<rid>/preview")
def image_preview(rid):
    """预览封面图"""
    try:
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config
        client = FeishuClient()
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not table_id:
            return jsonify({"ok": False, "error": "小红书笔记库未配置"}), 500

        records = client.list_records(table_id, page_size=10)
        images = []
        for r in records:
            if r.get("record_id") == rid:
                f = r.get("fields", {}) or {}
                for i in range(1, 6):
                    img = f.get(f"即梦生图{i}")
                    if img:
                        images.append({"index": i, "file_token": img})
                return jsonify({"ok": True, "data": {"record_id": rid, "images": images}})
        return jsonify({"ok": False, "error": "记录未找到"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-generate")
def batch_generate_images():
    """批量生成图片 — 将指定任务配图提示词入队到 image_jobs"""
    try:
        data = request.get_json(force=True) or {}
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "record_ids 为空"}), 400

        from scripts.queue_manager import get_queue
        from scripts.utils import append_jsonl, now_ts
        from scripts.config import PATHS
        import os

        queue_items = get_queue().get("items", [])
        enqueued = 0
        job_path = os.path.join(PATHS["logs"], "image_jobs.jsonl")

        for item in queue_items:
            if item.get("record_id") in record_ids:
                prompts = []
                result = item.get("deconstruct_result", {}) or {}
                pts = result.get("配图提示词", [])
                if not pts and isinstance(result, dict):
                    xhs = result.get("小红书包装", {}) or {}
                    cover_desc = xhs.get("封面图描述建议", "")
                    if cover_desc:
                        pts = [cover_desc]
                for p in pts[:5]:
                    if p:
                        prompts.append(str(p))
                if prompts:
                    append_jsonl(job_path, {
                        "xhs_record_id": item["record_id"],
                        "prompts": prompts,
                        "per_field_images": 2,
                        "provider": "jimeng",
                        "ts": now_ts(),
                        "status": "pending",
                    })
                    enqueued += 1

        return jsonify({"ok": True, "data": {"enqueued": enqueued}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
