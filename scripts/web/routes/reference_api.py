from flask import Blueprint, jsonify

from scripts.feishu_client import FeishuClient

bp = Blueprint("web_reference_api", __name__, url_prefix="/api/reference")


@bp.get("/top-notes")
def top_notes():
    try:
        client = FeishuClient()
        notes = client.get_top_notes(limit=3)
        return jsonify({"ok": True, "data": {"notes": notes, "total": len(notes)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
