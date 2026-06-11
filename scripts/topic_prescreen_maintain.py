import argparse
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, now_ts
from scripts.config import PATHS, ensure_dirs


def _to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if not s:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _to_int(x):
    v = _to_float(x)
    if v is None:
        return None
    return int(v)


def _normalize_multi(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[/、,，;；]", value) if p.strip()]
        return parts if parts else [value.strip()]
    return [str(value)]


def _derive_dimensions(fields):
    """
    Derive selection dimensions/tags from numeric fields if present.
    This is intentionally conservative; you can tune thresholds via env.
    """
    rating = _to_float(fields.get("评分") or fields.get("平台评分") or fields.get("评分(平台)"))
    comments = _to_int(fields.get("评论数") or fields.get("评论") or fields.get("评论量"))
    recommends = _to_int(fields.get("推荐数") or fields.get("推荐") or fields.get("推荐量") or fields.get("热度"))
    collects = _to_int(fields.get("收藏数") or fields.get("收藏") or fields.get("收藏量"))

    t_rating = float(os.getenv("PRESCREEN_MIN_RATING", "8.8") or 8.8)
    t_comments = int(float(os.getenv("PRESCREEN_MIN_COMMENTS", "10000") or 10000))
    t_recommends = int(float(os.getenv("PRESCREEN_MIN_RECOMMENDS", "5000") or 5000))
    t_collects = int(float(os.getenv("PRESCREEN_MIN_COLLECTS", "5000") or 5000))

    dims = []
    if rating is not None and rating >= t_rating:
        dims.append("高评分")
    if comments is not None and comments >= t_comments:
        dims.append("高评论")
    if recommends is not None and recommends >= t_recommends:
        dims.append("高推荐/热度")
    if collects is not None and collects >= t_collects:
        dims.append("高收藏")
    if not dims:
        dims.append("待人工判断")
    return dims


def _parse_count_text(s):
    """
    Parse common Chinese count formats: '1.2万', '3万+', '12000', '1,234'.
    Returns int or None.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(float(s))
    t = str(s).strip().replace(",", "").replace("+", "")
    if not t:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    v = float(m.group(1))
    if "万" in t:
        v *= 10000
    elif "亿" in t:
        v *= 100000000
    return int(v)


def _parse_rating_text(s):
    v = _to_float(s)
    return v


def enrich_prescreen_table(dry_run=False, limit=50):
    """
    Enrich '选题库-初筛' table records:
    - If there is a dimension/tag field, fill it (optional).
      Otherwise, fill '推荐理由' with derived dimensions when empty.
    - Normalize common numeric fields (optional, when those fields exist).
    """
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
    if not table_id:
        raise RuntimeError("未配置 选题库-初筛 table_id，请在 .env 设置 FEISHU_TOPIC_PRESCREEN_TABLE_ID")

    meta = client.get_table_field_meta(table_id)
    available = set(meta.keys())

    updated = 0
    scanned = 0
    for rec in client.iter_records(table_id, page_size=200):
        scanned += 1
        if scanned > int(limit or 50):
            break
        rid = rec.get("record_id")
        f = rec.get("fields", {}) or {}

        patch = {}

        # Structured fields: parse from text into *_数值 for sorting.
        if "平台评分_数值" in available:
            cur = f.get("平台评分_数值")
            if cur in [None, ""] and str(f.get("平台评分", "")).strip():
                rv = _parse_rating_text(f.get("平台评分"))
                if rv is not None:
                    patch["平台评分_数值"] = rv

        if "书评量_数值" in available:
            cur = f.get("书评量_数值")
            if cur in [None, ""] and str(f.get("书评量", "")).strip():
                cv = _parse_count_text(f.get("书评量"))
                if cv is not None:
                    patch["书评量_数值"] = cv

        if "收藏量_数值" in available:
            cur = f.get("收藏量_数值")
            if cur in [None, ""] and str(f.get("收藏量", "")).strip():
                fv = _parse_count_text(f.get("收藏量"))
                if fv is not None:
                    patch["收藏量_数值"] = fv

        if "推荐热度_数值" in available:
            cur = f.get("推荐热度_数值")
            if cur in [None, ""] and f.get("推荐热度") not in [None, ""]:
                try:
                    patch["推荐热度_数值"] = float(f.get("推荐热度"))
                except Exception:
                    hv = _parse_count_text(f.get("推荐热度"))
                    if hv is not None:
                        patch["推荐热度_数值"] = hv

        # Derive dimensions/tags.
        dims = _derive_dimensions(
            {
                "评分": f.get("平台评分_数值") or f.get("平台评分"),
                "评论数": f.get("书评量_数值") or f.get("书评量"),
                "推荐数": f.get("推荐热度_数值") or f.get("推荐热度"),
                "收藏数": f.get("收藏量_数值") or f.get("收藏量"),
            }
        )

        if "入选维度" in available:
            cur = f.get("入选维度")
            is_empty = (cur is None) or (isinstance(cur, list) and len(cur) == 0) or (isinstance(cur, str) and not cur.strip())
            if is_empty:
                # MultiSelect expects option ids; resolve by option name when possible.
                opt_ids = []
                for d in dims:
                    oid = client.resolve_single_select_option_id(table_id, "入选维度", d)
                    if oid:
                        opt_ids.append(oid)
                patch["入选维度"] = opt_ids if opt_ids else dims

        # Fill 推荐理由 if empty (human-readable).
        if "推荐理由" in available:
            cur = f.get("推荐理由")
            if cur is None or (isinstance(cur, str) and not cur.strip()):
                rating = f.get("平台评分", "")
                hot = f.get("推荐热度", "")
                fav = f.get("收藏量", "")
                com = f.get("书评量", "")
                brief = "；".join(
                    [
                        x
                        for x in [
                            f"入选维度：{' / '.join(dims)}",
                            f"评分：{rating}" if str(rating).strip() else "",
                            f"热度：{hot}" if str(hot).strip() else "",
                            f"收藏：{fav}" if str(fav).strip() else "",
                            f"书评：{com}" if str(com).strip() else "",
                        ]
                        if x
                    ]
                )
                patch["推荐理由"] = brief[:400]

        # Composite score for sorting (simple and interpretable).
        if "综合得分" in available and f.get("综合得分") in [None, ""]:
            r = _to_float(f.get("平台评分_数值") or f.get("平台评分")) or 0.0
            hot = _to_float(f.get("推荐热度_数值") or f.get("推荐热度")) or 0.0
            com = _to_float(f.get("书评量_数值") or f.get("书评量")) or 0.0
            fav = _to_float(f.get("收藏量_数值") or f.get("收藏量")) or 0.0
            # Scale counts down to keep score in a sane range.
            score = round(r * 10 + (hot ** 0.5) + (com ** 0.5) + (fav ** 0.5), 3)
            patch["综合得分"] = score

        # Optional status hint
        if "提取状态" in available:
            cur = f.get("提取状态")
            if cur is None or (isinstance(cur, str) and not cur.strip()):
                patch["提取状态"] = "待审核"

        # Keep only fields that exist
        patch = client.filter_fields(table_id, patch)
        if not patch:
            continue

        if dry_run:
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_enrich_dryrun.jsonl"),
                {"ts": now_ts(), "record_id": rid, "patch": patch},
            )
            continue

        client.update_record_in_table(table_id, rid, patch)
        updated += 1
        append_jsonl(
            os.path.join(PATHS["logs"], "prescreen_enrich.jsonl"),
            {"ts": now_ts(), "record_id": rid, "patch": patch},
        )

    return {"scanned": scanned, "updated": updated, "dry_run": dry_run}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("enrich", help="补全选题库-初筛的维度字段（不做外部搜索）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(base_dir, ".env"))
    ensure_dirs()

    if args.cmd == "enrich":
        res = enrich_prescreen_table(dry_run=args.dry_run, limit=args.limit)
        print(res)


if __name__ == "__main__":
    main()
