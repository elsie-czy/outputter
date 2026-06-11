from flask import Blueprint, jsonify, request

from scripts.model_adapter import analyze_work
from scripts.quality_scorer import score_note

bp = Blueprint("web_note_api", __name__, url_prefix="/api/note")


@bp.get("/<rid>")
def get_note(rid):
    try:
        from scripts.queue_manager import get_queue
        result = get_queue()
        for item in result.get("items", []):
            if item.get("record_id") == rid:
                return jsonify({"ok": True, "data": {
                    "record_id": rid,
                    "note_content": item.get("note_content", ""),
                    "quality_score": item.get("quality_score"),
                    "status": item.get("status"),
                }})
        # Fallback: check feishu
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config
        client = FeishuClient()
        cfg = get_feishu_config()
        xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if xhs_table_id and client.is_configured():
            records = client.list_records(xhs_table_id, page_size=10)
            for r in records:
                if r.get("record_id") == rid:
                    f = r.get("fields", {}) or {}
                    return jsonify({"ok": True, "data": {
                        "record_id": rid,
                        "title": str(f.get("小红书标题模板", "")),
                        "note_content": str(f.get("正文开头模板", "")),
                        "tags": str(f.get("热门标签推荐", "")),
                        "cta": str(f.get("互动话术模板", "")),
                    }})
        return jsonify({"ok": False, "error": "笔记未找到"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/regenerate")
def regenerate_note(rid):
    try:
        data = request.get_json(force=True) or {}
        fields = data.get("fields", ["title", "body", "tags", "cta"])
        reference_ids = data.get("reference_ids", [])

        # Build work dict from queue
        from scripts.queue_manager import get_queue
        result = get_queue()
        work = {}
        for item in result.get("items", []):
            if item.get("record_id") == rid:
                work = {
                    "作品名称": item.get("work_name", ""),
                    "作者": item.get("author", ""),
                    "平台": item.get("platform", ""),
                    "分类": item.get("category", ""),
                }
                break
        if not work:
            return jsonify({"ok": False, "error": "任务未找到"}), 404

        # Fetch reference notes if specified
        reference_notes = None
        if reference_ids:
            from scripts.feishu_client import FeishuClient
            client = FeishuClient()
            reference_notes = client.get_top_notes(limit=3)

        analysis = analyze_work(work, reference_notes=reference_notes)
        return jsonify({"ok": True, "data": {
            "title": analysis.get("小红书包装", {}).get("小红书标题模板", ""),
            "body": analysis.get("小红书包装", {}).get("正文开头模板", ""),
            "tags": analysis.get("小红书包装", {}).get("热门标签推荐", []),
            "cta": analysis.get("小红书包装", {}).get("互动话术模板", ""),
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/save")
def save_note(rid):
    try:
        data = request.get_json(force=True) or {}
        diff_log = data.get("diff_log", "")
        quality_score = data.get("quality_score", 0)

        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config
        client = FeishuClient()
        cfg = get_feishu_config()
        xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not xhs_table_id:
            return jsonify({"ok": False, "error": "小红书笔记库未配置"}), 500

        # Update fields
        patch = {}
        if data.get("title"):
            patch["小红书标题模板"] = data["title"]
        if data.get("body"):
            patch["正文开头模板"] = data["body"]
        if data.get("tags"):
            patch["热门标签推荐"] = data["tags"]
        if data.get("cta"):
            patch["互动话术模板"] = data["cta"]

        if patch:
            client.update_record_in_table(xhs_table_id, rid, patch)

        # Append modification log
        if diff_log:
            client.save_modification_log(xhs_table_id, rid, diff_log, quality_score)

        return jsonify({"ok": True, "data": {"saved": True}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/batch-generate")
def batch_generate():
    try:
        data = request.get_json(force=True) or {}
        record_ids = data.get("record_ids", [])
        if not record_ids:
            return jsonify({"ok": False, "error": "record_ids 为空"}), 400

        from scripts.queue_manager import get_queue
        result = get_queue()
        generated = []
        for item in result.get("items", []):
            if item.get("record_id") in record_ids and item.get("note_content"):
                generated.append({
                    "record_id": item["record_id"],
                    "work_name": item.get("work_name", ""),
                    "note_content": item["note_content"],
                })

        return jsonify({"ok": True, "data": {"generated": len(generated), "notes": generated}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/<rid>/score")
def rescore_note(rid):
    try:
        from scripts.queue_manager import get_queue
        result = get_queue()
        note_text = ""
        for item in result.get("items", []):
            if item.get("record_id") == rid and item.get("note_content"):
                note_text = item["note_content"]
                break

        if not note_text:
            return jsonify({"ok": False, "error": "笔记内容为空"}), 400

        score_result = score_note(note_text)
        return jsonify({"ok": True, "data": score_result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
