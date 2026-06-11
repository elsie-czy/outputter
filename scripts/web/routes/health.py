from flask import Blueprint, jsonify

bp = Blueprint("web_health", __name__, url_prefix="/_health")


@bp.get("")
def health():
    return jsonify({"ok": True, "service": "personal-supertool-web"})
