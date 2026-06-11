import glob
import json
import os
import time

from scripts.config import PATHS, ensure_dirs

_ANALYSIS_REPORT_CACHE = {"ts": 0.0, "data": None}
_ANALYSIS_REPORT_CACHE_SEC = 20


def load_analysis_recent():
    ensure_dirs()
    path = os.path.join(PATHS["logs"], "analysis_web_results.jsonl")
    latest = []
    total = 0
    ok = 0
    failed = 0
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if obj.get("ok"):
                        ok += 1
                    else:
                        failed += 1
                    latest.append(obj)
        latest = latest[-12:][::-1]
    except Exception:
        latest = []
    return {"total": total, "ok": ok, "failed": failed, "latest": latest}


def load_analysis_jobs_tail():
    ensure_dirs()
    path = os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl")
    by_id = {}
    order = []
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = (line or "").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    jid = obj.get("job_id")
                    if not jid:
                        continue
                    if jid not in by_id:
                        order.append(jid)
                        by_id[jid] = {}
                    by_id[jid].update(obj)
    except Exception:
        by_id = {}
        order = []

    latest = []
    queued = 0
    running = 0
    for jid in order[-15:][::-1]:
        j = by_id.get(jid) or {}
        st = j.get("status") or ""
        if st == "queued":
            queued += 1
        elif st == "running":
            running += 1
        latest.append(j)
    return {"total": len(order), "queued": queued, "running": running, "latest": latest}


def load_latest_analysis_report():
    now = time.time()
    hit = _ANALYSIS_REPORT_CACHE
    if hit.get("data") is not None and (now - hit.get("ts", 0.0)) < _ANALYSIS_REPORT_CACHE_SEC:
        return hit["data"]

    out_dir = os.path.join(PATHS["outputs"], "分析周报")
    data = {"path": "", "content": ""}
    try:
        candidates = sorted(
            glob.glob(os.path.join(out_dir, "*_爆款基因周报.md")),
            key=os.path.getmtime,
            reverse=True,
        )
        if candidates:
            path = candidates[0]
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            data = {"path": path, "content": text}
    except Exception:
        data = {"path": "", "content": ""}
    _ANALYSIS_REPORT_CACHE["ts"] = now
    _ANALYSIS_REPORT_CACHE["data"] = data
    return data


def clear_analysis_report_cache():
    _ANALYSIS_REPORT_CACHE["ts"] = 0.0
    _ANALYSIS_REPORT_CACHE["data"] = None
