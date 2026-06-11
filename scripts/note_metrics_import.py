import argparse
import hashlib
import os
import re
import sys
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, now_ts


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _col_to_idx(col):
    n = 0
    for ch in col:
        if ch.isalpha():
            n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _cell_val(c):
    isel = c.find("a:is", NS)
    if isel is not None:
        t = isel.find("a:t", NS)
        return (t.text or "") if t is not None else ""
    v = c.find("a:v", NS)
    return (v.text or "") if v is not None else ""


def parse_xlsx(path):
    """
    Parse exported xlsx without pandas/openpyxl.
    Assumes row2 is header in current export format.
    """
    with zipfile.ZipFile(path) as z:
        xml = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    maxc = 0
    for r in xml.findall("a:sheetData/a:row", NS):
        arr = []
        for c in r.findall("a:c", NS):
            ref = c.attrib.get("r", "")
            col = "".join(ch for ch in ref if ch.isalpha())
            idx = _col_to_idx(col)
            while len(arr) <= idx:
                arr.append("")
            arr[idx] = _cell_val(c)
            maxc = max(maxc, idx + 1)
        rows.append(arr + [""] * (maxc - len(arr)))
    if len(rows) < 2:
        return []
    header = [str(x).strip() for x in rows[1]]
    out = []
    for raw in rows[2:]:
        rec = {}
        for i, h in enumerate(header):
            if not h:
                continue
            rec[h] = str(raw[i]).strip() if i < len(raw) else ""
        if rec.get("笔记标题"):
            out.append(rec)
    return out


def to_float(v):
    try:
        if v is None:
            return 0.0
        s = str(v).strip()
        if not s:
            return 0.0
        return float(s)
    except Exception:
        return 0.0


def parse_cn_datetime(s):
    if isinstance(s, (int, float)):
        x = float(s)
        # Support epoch seconds or milliseconds.
        if x > 100000000000:
            x = x / 1000.0
        try:
            return datetime.fromtimestamp(x)
        except Exception:
            return None
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ["%Y年%m月%d日%H时%M分%S秒", "%Y-%m-%d %H:%M:%S"]:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None


def build_uid(title, pub_time_text):
    seed = f"{title}|{pub_time_text}".strip()
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    return f"note_{h}"


def classify_recovery(dt, recovery_date):
    if not dt:
        return "未知"
    return "恢复后" if dt.date() >= recovery_date.date() else "恢复前"


def transform(records, source_file, batch, recovery_date, account_name, experiment_id="", experiment_version="NA", experiment_variable=""):
    out = []
    for r in records:
        title = str(r.get("笔记标题", "")).strip()
        pub_text = str(r.get("首次发布时间", "")).strip()
        dt = parse_cn_datetime(pub_text)
        pub_ts = int(dt.timestamp() * 1000) if dt else None
        uid = build_uid(title, pub_text)

        exposure = to_float(r.get("曝光"))
        views = to_float(r.get("观看量"))
        cover_ctr = to_float(r.get("封面点击率"))
        likes = to_float(r.get("点赞"))
        comments = to_float(r.get("评论"))
        favs = to_float(r.get("收藏"))
        fans = to_float(r.get("涨粉"))
        shares = to_float(r.get("分享"))
        avg_watch = to_float(r.get("人均观看时长"))
        danmaku = to_float(r.get("弹幕"))

        inter_total = likes + comments + favs + shares
        inter_rate_exp = inter_total / exposure if exposure > 0 else 0.0
        fav_rate_view = favs / views if views > 0 else 0.0
        comment_rate_view = comments / views if views > 0 else 0.0
        share_rate_view = shares / views if views > 0 else 0.0
        fan_rate_exp = fans / exposure if exposure > 0 else 0.0

        hot_score = (
            0.45 * fav_rate_view + 0.25 * comment_rate_view + 0.2 * share_rate_view + 0.1 * fan_rate_exp
        ) * 100

        out.append(
            {
                "笔记唯一键": uid,
                "实验ID": experiment_id,
                "实验版本": experiment_version,
                "实验变量": experiment_variable,
                "笔记标题": title,
                # Feishu DateTime field expects epoch milliseconds.
                "首次发布时间": pub_ts,
                "体裁": str(r.get("体裁", "")).strip(),
                "曝光": exposure,
                "观看量": views,
                "封面点击率": cover_ctr,
                "点赞": likes,
                "评论": comments,
                "收藏": favs,
                "涨粉": fans,
                "分享": shares,
                "人均观看时长": avg_watch,
                "弹幕": danmaku,
                "互动总量": inter_total,
                "互动率_按曝光": inter_rate_exp,
                "收藏率_按观看": fav_rate_view,
                "评论率_按观看": comment_rate_view,
                "分享率_按观看": share_rate_view,
                "涨粉率_按曝光": fan_rate_exp,
                "爆款分": hot_score,
                "账号名": account_name,
                "恢复期标签": classify_recovery(dt, recovery_date),
                "导入批次": batch,
                "数据来源文件": os.path.basename(source_file),
                "导入时间": int(datetime.now().timestamp() * 1000),
            }
        )
    return out


def upsert_to_feishu(items, table_id, dry_run=False):
    c = FeishuClient()
    if not c.is_configured():
        raise RuntimeError("飞书未配置")
    if not table_id:
        raise RuntimeError("未配置 FEISHU_NOTE_METRICS_TABLE_ID")
    created = 0
    updated = 0
    skipped = 0
    errors = 0
    for it in items:
        uid = it.get("笔记唯一键")
        if not uid:
            continue
        rec = c.find_first_record_by_fields(table_id, {"笔记唯一键": uid})
        fields = c.filter_fields(table_id, it)
        # Avoid sending null to strict DateTime fields.
        fields = {k: v for k, v in fields.items() if v is not None}
        try:
            if rec and rec.get("record_id"):
                if dry_run:
                    skipped += 1
                else:
                    c.update_record_in_table(table_id, rec["record_id"], fields)
                    updated += 1
            else:
                if dry_run:
                    created += 1
                else:
                    c.create_record_in_table(table_id, fields)
                    created += 1
        except Exception as e:
            errors += 1
            append_jsonl(
                os.path.join(PATHS["logs"], "note_metrics_import_errors.jsonl"),
                {"ts": now_ts(), "uid": uid, "title": it.get("笔记标题"), "error": str(e)},
            )
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", required=True, help="创作者平台导出 xlsx 路径")
    p.add_argument("--batch", default="", help="导入批次，默认 YYYY-MM-DD")
    p.add_argument("--account-name", default="默认账号")
    p.add_argument("--recovery-date", default="2026-03-01", help="恢复可发日期 YYYY-MM-DD")
    p.add_argument("--experiment-id", default="", help="实验ID（可选）")
    p.add_argument("--experiment-version", default="NA", help="实验版本：A/B/NA")
    p.add_argument("--experiment-variable", default="", help="实验变量（如 标题钩子/发布时间段）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write-feishu", action="store_true", help="写入飞书笔记结果库")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()

    if not os.path.exists(args.xlsx):
        raise RuntimeError(f"xlsx 不存在: {args.xlsx}")
    batch = args.batch.strip() or datetime.now().strftime("%Y-%m-%d")
    rec_date = datetime.strptime(args.recovery_date, "%Y-%m-%d")

    raw = parse_xlsx(args.xlsx)
    exp_ver = (args.experiment_version or "NA").strip().upper()
    if exp_ver not in ["A", "B", "NA"]:
        exp_ver = "NA"
    items = transform(
        raw,
        args.xlsx,
        batch,
        rec_date,
        args.account_name,
        experiment_id=(args.experiment_id or "").strip(),
        experiment_version=exp_ver,
        experiment_variable=(args.experiment_variable or "").strip(),
    )

    # Always keep local snapshot for decoupled analysis.
    for it in items:
        append_jsonl(os.path.join(PATHS["logs"], "note_metrics_records.jsonl"), {"ts": now_ts(), **it})

    res = {"parsed": len(raw), "normalized": len(items), "feishu": None}
    if args.write_feishu:
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("笔记结果库")
        res["feishu"] = upsert_to_feishu(items, table_id=table_id, dry_run=args.dry_run)
    print(res)


if __name__ == "__main__":
    main()
