from flask import Blueprint, jsonify, request

from scripts.web.services.xhs_preview_data import load_xhs_preview_data

bp = Blueprint("web_xhs_api", __name__, url_prefix="/api/xhs")


@bp.get("/<rid>/preview")
def xhs_preview_api(rid):
    notice = (request.args.get("notice", "") or "").strip().lower()
    payload, status = load_xhs_preview_data(rid=rid, notice=notice, is_fact_repairing=False)
    return jsonify(payload), status
