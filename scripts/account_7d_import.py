import argparse
import hashlib
import math
import os
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
WBNS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


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


def _parse_sheet_rows(zf, sheet_xml_path):
    xml = ET.fromstring(zf.read(sheet_xml_path))
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
        if arr:
            rows.append(arr + [""] * (maxc - len(arr)))
    return rows


def parse_metric_xlsx(path):
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        rel = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            x.attrib.get("Id"): x.attrib.get("Target")
            for x in rel.findall("pr:Relationship", WBNS)
        }

        summary = {}
        trends = []
        for s in wb.findall("a:sheets/a:sheet", WBNS):
            sheet_name = s.attrib.get("name", "")
            rid = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = rel_map.get(rid, "")
            if not target:
                continue
            rows = _parse_sheet_rows(zf, f"xl/{target}")
            if not rows:
                continue

            if sheet_name == "账号总体观看数据":
                for r in rows[1:]:
                    if len(r) < 2:
                        continue
                    key = str(r[0]).strip()
                    val = str(r[1]).strip()
                    if key:
                        summary[key] = val
                continue

            # date/value trend sheets
            metric_name = sheet_name.replace("趋势", "").strip() or sheet_name
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                d = str(r[0]).strip()
                v = str(r[1]).strip()
                if not d:
                    continue
                trends.append(
                    {
                        "sheet_name": sheet_name,
                        "metric_name": metric_name,
                        "date_text": d,
                        "value_text": v,
                    }
                )
        return {"summary": summary, "trends": trends}


def _to_num(v):
    s = str(v or "").strip().replace("%", "").replace("秒", "").replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _to_date_ms(v):
    text = str(v or "").strip()
    for fmt in ["%Y年%m月%d日", "%Y-%m-%d"]:
        try:
            return int(datetime.strptime(text, fmt).timestamp() * 1000)
        except Exception:
            pass
    return None


def _build_summary_item(summary, source_file, batch, account_name, snapshot_date):
    snap_ms = int(datetime.strptime(snapshot_date, "%Y-%m-%d").timestamp() * 1000)
    seed = f"{account_name}|{snapshot_date}|summary"
    uniq = "acct7d_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
    exposure = _to_num(summary.get("曝光"))
    views = _to_num(summary.get("观看"))
    view_rate = (views / exposure * 100.0) if exposure > 0 else 0.0
    return {
        "快照唯一键": uniq,
        "数据类型": "总体",
        "快照日期": snap_ms,
        "账号名": account_name,
        "导入批次": batch,
        "数据来源文件": os.path.basename(source_file),
        "导入时间": int(datetime.now().timestamp() * 1000),
        "曝光": exposure,
        "观看": views,
        "观看率(%)": view_rate,
        "封面点击率(%)": _to_num(summary.get("封面点击率(%)")),
        "平均观看时长(s)": _to_num(summary.get("平均观看时长(s)")),
        "总观看时长(s)": _to_num(summary.get("总观看时长(s)")),
        "总完播率(%)": _to_num(summary.get("总完播率(%)")),
        "曝光环比(%)": _to_num(summary.get("曝光环比(%)")),
        "观看环比(%)": _to_num(summary.get("观看环比(%)")),
        "封面点击率环比(%)": _to_num(summary.get("封面点击率环比(%)")),
        "平均观看时长环比(%)": _to_num(summary.get("平均观看时长环比(%)")),
        "总观看时长环比(%)": _to_num(summary.get("总观看时长环比(%)")),
        "总完播率环比(%)": _to_num(summary.get("总完播率环比(%)")),
    }


def _build_trend_items(trends, source_file, batch, account_name, snapshot_date):
    snap_ms = int(datetime.strptime(snapshot_date, "%Y-%m-%d").timestamp() * 1000)
    out = []
    for t in trends:
        seed = f"{account_name}|{snapshot_date}|{t.get('sheet_name')}|{t.get('date_text')}"
        uniq = "acct7dt_" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        out.append(
            {
                "快照唯一键": uniq,
                "数据类型": "趋势",
                "快照日期": snap_ms,
                "账号名": account_name,
                "导入批次": batch,
                "数据来源文件": os.path.basename(source_file),
                "导入时间": int(datetime.now().timestamp() * 1000),
                "趋势指标": t.get("metric_name", ""),
                "趋势日期": _to_date_ms(t.get("date_text")),
                "趋势数值": _to_num(t.get("value_text")),
                "趋势来源sheet": t.get("sheet_name", ""),
            }
        )
    return out


def _compute_volatility_coef(trends, metric_name="观看"):
    vals = []
    for t in trends:
        if str(t.get("metric_name", "")).strip() == metric_name:
            vals.append(_to_num(t.get("value_text")))
    if not vals:
        return 0.0
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in vals) / len(vals)
    std = math.sqrt(var)
    return std / mean


def upsert_feishu(items, table_id, dry_run=False):
    c = FeishuClient()
    if not c.is_configured():
        raise RuntimeError("飞书未配置")
    if not table_id:
        raise RuntimeError("未配置 FEISHU_ACCOUNT_7D_TABLE_ID")

    created = 0
    updated = 0
    for item in items:
        rec = c.find_first_record_by_fields(table_id, {"快照唯一键": item.get("快照唯一键")})
        fields = c.filter_fields(table_id, item)
        fields = {k: v for k, v in fields.items() if v is not None}
        if rec and rec.get("record_id"):
            if not dry_run:
                c.update_record_in_table(table_id, rec["record_id"], fields)
            updated += 1
        else:
            if not dry_run:
                c.create_record_in_table(table_id, fields)
            created += 1
    return {"created": created, "updated": updated}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--xlsx", required=True)
    p.add_argument("--batch", default="")
    p.add_argument("--account-name", default="主账号")
    p.add_argument("--snapshot-date", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write-feishu", action="store_true")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()

    if not os.path.exists(args.xlsx):
        raise RuntimeError(f"xlsx 不存在: {args.xlsx}")
    batch = args.batch.strip() or datetime.now().strftime("%Y-%m-%d")
    parsed = parse_metric_xlsx(args.xlsx)
    summary = parsed.get("summary", {})
    trends = parsed.get("trends", [])

    summary_item = _build_summary_item(summary, args.xlsx, batch, args.account_name.strip(), args.snapshot_date.strip())
    summary_item["7日波动系数"] = _compute_volatility_coef(trends, metric_name="观看")
    items = [summary_item]
    items.extend(
        _build_trend_items(trends, args.xlsx, batch, args.account_name.strip(), args.snapshot_date.strip())
    )

    for it in items:
        append_jsonl(os.path.join(PATHS["logs"], "account_7d_records.jsonl"), {"ts": now_ts(), **it})

    res = {
        "parsed_metrics": len(summary),
        "parsed_trend_rows": len(trends),
        "rows": len(items),
        "feishu": None,
    }
    if args.write_feishu:
        table_id = (get_feishu_config().get("related_table_ids") or {}).get("账号7日快照")
        res["feishu"] = upsert_feishu(items, table_id=table_id, dry_run=args.dry_run)
    print(res)


if __name__ == "__main__":
    main()
