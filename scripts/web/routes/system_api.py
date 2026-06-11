from flask import Blueprint, jsonify

from scripts.web.services.local_runs import (
    load_image_queue_status,
    load_records,
    load_run_summary,
)
from scripts.web.services.analysis_status import (
    load_analysis_jobs_tail,
    load_analysis_recent,
    load_latest_analysis_report,
)
from scripts.web.services.prescreen_status import (
    load_prescreen_jobs_tail,
    load_prescreen_recent,
)
from scripts.web_app_legacy import load_xhs_stats_cached

bp = Blueprint("web_system_api", __name__, url_prefix="/api/system")


@bp.get("/local-summary")
def local_summary():
    records = load_records()
    run_summary = load_run_summary()
    queue = load_image_queue_status()
    return jsonify(
        {
            "ok": True,
            "records_total": len(records),
            "latest_run": records[0] if records else None,
            "run_summary": run_summary,
            "image_queue": queue,
        }
    )


@bp.get("/xhs-overview")
def xhs_overview():
    stats, err = load_xhs_stats_cached()
    return jsonify({"ok": err is None, "error": err, "stats": stats})


@bp.get("/prescreen-status")
def prescreen_status():
    return jsonify(
        {
            "ok": True,
            "jobs": load_prescreen_jobs_tail(),
            "recent": load_prescreen_recent(),
        }
    )


@bp.get("/analysis-status")
def analysis_status():
    latest_report = load_latest_analysis_report()
    return jsonify(
        {
            "ok": True,
            "jobs": load_analysis_jobs_tail(),
            "recent": load_analysis_recent(),
            "latest_report": {
                "path": latest_report.get("path", ""),
                "has_content": bool((latest_report.get("content") or "").strip()),
            },
        }
    )
