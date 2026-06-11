import json
import os

from scripts.config import PATHS, ensure_dirs


def load_records():
    ensure_dirs()
    path = os.path.join(PATHS["logs"], "records.jsonl")
    if not os.path.exists(path):
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    items.sort(key=lambda x: x.get("run_date", ""), reverse=True)
    return items


def load_run_summary():
    path = os.path.join(PATHS["logs"], "run_summary.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_read_int(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int((f.read() or "").strip() or "0")
    except Exception:
        return 0


def _count_lines(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def load_image_queue_status():
    logs_dir = PATHS["logs"]
    jobs_path = os.path.join(logs_dir, "image_jobs.jsonl")
    cursor_path = os.path.join(logs_dir, "image_jobs.cursor")
    results_path = os.path.join(logs_dir, "image_job_results.jsonl")

    jobs_total = _count_lines(jobs_path)
    cursor_pos = _safe_read_int(cursor_path)
    results_total = _count_lines(results_path)

    pending_unique = 0
    pending_ids = set()
    try:
        with open(jobs_path, "r", encoding="utf-8") as f:
            if cursor_pos > 0:
                try:
                    f.seek(cursor_pos)
                except Exception:
                    pass
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    job = json.loads(line)
                except Exception:
                    continue
                rid = str(job.get("xhs_record_id", "")).strip()
                if rid:
                    pending_ids.add(rid)
        pending_unique = len(pending_ids)
    except Exception:
        pending_unique = 0

    latest = []
    ok = 0
    failed = 0
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f if x.strip()]
        for line in lines[-20:][::-1]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            latest.append(rec)
        for line in lines[-200:]:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            st = str(rec.get("status", "")).lower()
            if st.startswith("updated") or st == "updated":
                ok += 1
            elif st.startswith("failed"):
                failed += 1
    except Exception:
        latest = []

    return {
        "jobs_total": jobs_total,
        "cursor_pos": cursor_pos,
        "results_total": results_total,
        "pending_unique": pending_unique,
        "recent_ok": ok,
        "recent_failed": failed,
        "latest": latest,
    }
