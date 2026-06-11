import ast
import json
import os
from datetime import datetime

from scripts.config import PATHS, ensure_dirs
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config

_PRESCREEN_LATEST_CACHE = {"ts": 0.0, "data": None, "err": None}
_PRESCREEN_LATEST_CACHE_SEC = 45


def load_prescreen_recent():
    ensure_dirs()
    path = os.path.join(PATHS["logs"], "prescreen_web_job_results.jsonl")
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


def load_prescreen_jobs_tail():
    ensure_dirs()
    path = os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl")
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
        j["summary_cn"] = humanize_prescreen_summary(j.get("summary") or "")
        latest.append(j)

    return {"total": len(order), "queued": queued, "running": running, "latest": latest}


def humanize_prescreen_summary(summary):
    s = str(summary or "").strip()
    if not s:
        return ""
    obj = None
    try:
        obj = json.loads(s)
    except Exception:
        obj = None
    if obj is None:
        try:
            tmp = ast.literal_eval(s)
            if isinstance(tmp, dict):
                obj = tmp
        except Exception:
            obj = None
    if isinstance(obj, dict):
        fetched = obj.get("fetched")
        created = obj.get("created")
        updated = obj.get("updated")
        skipped = obj.get("skipped")
        errors = obj.get("errors")
        dry = obj.get("dry_run")
        parts = []
        if fetched is not None:
            parts.append(f"抓取 {int(fetched)}")
        if created is not None:
            parts.append(f"新增 {int(created)}")
        if updated is not None:
            parts.append(f"更新 {int(updated)}")
        if skipped is not None and int(skipped) > 0:
            parts.append(f"跳过 {int(skipped)}")
        if errors is not None and int(errors) > 0:
            parts.append(f"错误 {int(errors)}")
        if dry:
            parts.append("dry-run")
        return "，".join(parts)
    return s[:120]


def fmt_compact_num(v):
    try:
        if v is None or v == "":
            return ""
        x = float(v)
    except Exception:
        s = str(v).strip()
        return s[:16] if len(s) > 16 else s
    if x >= 100000000:
        return f"{x / 100000000:.2f}".rstrip("0").rstrip(".") + "亿"
    if x >= 10000:
        return f"{x / 10000:.2f}".rstrip("0").rstrip(".") + "万"
    if x >= 1000:
        return f"{x / 1000:.2f}".rstrip("0").rstrip(".") + "k"
    if x.is_integer():
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def load_prescreen_latest_cached(limit=20):
    now = datetime.now().timestamp()
    if _PRESCREEN_LATEST_CACHE.get("data") is not None and (
        now - _PRESCREEN_LATEST_CACHE.get("ts", 0)
    ) < _PRESCREEN_LATEST_CACHE_SEC:
        return _PRESCREEN_LATEST_CACHE.get("data"), _PRESCREEN_LATEST_CACHE.get("err")
    data = None
    err = None
    try:
        client = FeishuClient()
        if not client.is_configured():
            raise RuntimeError("飞书未配置")
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
        if not table_id:
            raise RuntimeError("未配置 选题库-初筛 table_id")

        rows = []
        for i, rec in enumerate(client.iter_records(table_id, page_size=50)):
            if i >= 120:
                break
            f = rec.get("fields") or {}
            heat = f.get("推荐热度_数值") or f.get("推荐热度") or f.get("在读量_数值") or ""
            rows.append(
                {
                    "title": str(f.get("作品名称", "")).strip(),
                    "author": str(f.get("作者", "")).strip(),
                    "platform": str(f.get("平台", "")).strip(),
                    "finish": str(f.get("是否完结", "")).strip(),
                    "type": str(f.get("类型", "")).strip(),
                    "heat_raw": heat,
                    "heat_disp": fmt_compact_num(heat),
                    "desc": str(f.get("简介", "")).strip()[:120],
                    "link": str(f.get("作品链接", "")).strip(),
                    "batch": str(f.get("抓取批次", "")).strip(),
                    "ts": float(f.get("最近更新") or f.get("添加时间") or 0),
                }
            )
        rows.sort(key=lambda x: x.get("ts") or 0, reverse=True)
        data = rows[: int(limit or 20)]
    except Exception as e:
        err = str(e)
        data = []
    _PRESCREEN_LATEST_CACHE["ts"] = now
    _PRESCREEN_LATEST_CACHE["data"] = data
    _PRESCREEN_LATEST_CACHE["err"] = err
    return data, err
