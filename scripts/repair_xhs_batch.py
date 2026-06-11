import argparse
import json
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.deconstruct_daily import _build_image_prompts, build_xhs_note
from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.repair_xhs_record import _build_grounded_analysis, _mobile_trim


ANCIENT_KEYS = ["仙侠", "修真", "古代", "江湖", "宗门", "朝堂", "宫廷"]


def _is_ancient(work):
    s = f"{work.get('分类','')} {work.get('简介','')}"
    return any(k in s for k in ANCIENT_KEYS)


def _normalize_fields_for_type(client, table_id, meta, fields):
    out = {}
    for k, v in fields.items():
        if k not in meta:
            continue
        ftype = (meta.get(k) or {}).get("type")
        if ftype == 4:
            if k == "小红书标题模板":
                out[k] = [str(v)] if not isinstance(v, list) else v[:1]
            elif isinstance(v, list):
                out[k] = v
            elif isinstance(v, str):
                parts = [x.strip() for x in re.split(r"[,，/、;；\\s]+", v) if x.strip()]
                out[k] = parts if parts else [v]
            else:
                out[k] = [str(v)]
        elif ftype == 3:
            if isinstance(v, list):
                v = v[0] if v else ""
            s = str(v or "").strip()
            out[k] = client.resolve_single_select_option_id(table_id, k, s) or s if s else ""
        elif ftype == 5:
            if isinstance(v, int):
                out[k] = v
            else:
                out[k] = int(datetime.now().timestamp() * 1000)
        else:
            out[k] = v
    return out


def _risk_reasons(work, xhs_fields):
    reasons = []
    prompts = [str(xhs_fields.get(f"生成配图提示词{i}", "")).strip() for i in range(1, 6)]
    if not any(prompts):
        reasons.append("prompt_missing")
    if any("博主" in p and "female lead" in p for p in prompts if p):
        reasons.append("name_drift_bozhu")
    if _is_ancient(work) and any("modern era" in p.lower() for p in prompts if p):
        reasons.append("era_conflict_modern")
    mdv = xhs_fields.get("小红书笔记初稿", [])
    if not (isinstance(mdv, list) and len(mdv) >= 1):
        reasons.append("md_missing")
    if any(len(p) > 900 for p in prompts if p):
        reasons.append("prompt_too_long")
    return reasons


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="执行实际修复")
    p.add_argument("--limit", type=int, default=100, help="最多处理条数")
    p.add_argument("--work-name", default="", help="仅处理某本作品（可选）")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()
    c = FeishuClient()
    if not c.is_configured():
        raise RuntimeError("飞书未配置")
    cfg = get_feishu_config()
    xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
    topic_table_id = (cfg.get("related_table_ids") or {}).get("选题库")
    if not xhs_table_id or not topic_table_id:
        raise RuntimeError("未配置 小红书笔记库/选题库 table_id")

    # Build source map from 选题库.
    topic_map = {}
    for r in c.iter_records(topic_table_id, page_size=200):
        f = r.get("fields") or {}
        name = str(f.get("作品名称", "")).strip()
        if not name:
            continue
        topic_map[name] = {
            "作品名称": name,
            "作者": str(f.get("作者", "")).strip(),
            "平台": str(f.get("平台", "")).strip(),
            "分类": str(f.get("分类", "")).strip(),
            "简介": str(f.get("简介", "")).strip(),
        }

    xhs_meta = c.get_table_field_meta(xhs_table_id) or {}
    scan_total = 0
    risky = []
    for r in c.iter_records(xhs_table_id, page_size=200):
        scan_total += 1
        f = r.get("fields") or {}
        work_name = str(f.get("作品名称", "")).strip()
        if not work_name:
            continue
        if args.work_name and work_name != args.work_name.strip():
            continue
        work = topic_map.get(work_name)
        if not work:
            continue
        reasons = _risk_reasons(work, f)
        if reasons:
            risky.append({"record_id": r.get("record_id"), "work_name": work_name, "reasons": reasons, "work": work})

    risky = risky[: max(1, args.limit)]
    report = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "scan_total": scan_total,
        "risky_total": len(risky),
        "apply": bool(args.apply),
        "updated": 0,
        "failed": 0,
        "details": [],
    }

    if args.apply:
        for item in risky:
            rid = item["record_id"]
            work = item["work"]
            try:
                analysis = _build_grounded_analysis(work)
                note = build_xhs_note(work, analysis)
                prompts = analysis.get("配图提示词", [])[:5]
                patch = {}
                for i in range(5):
                    k = f"生成配图提示词{i+1}"
                    if k in xhs_meta:
                        patch[k] = prompts[i] if i < len(prompts) else ""
                if "正文开头模板" in xhs_meta:
                    patch["正文开头模板"] = _mobile_trim(analysis["小红书包装"]["正文开头模板"], 68)
                if "正文结构建议" in xhs_meta:
                    patch["正文结构建议"] = _mobile_trim(analysis["小红书包装"]["正文结构建议"], 56)
                if "互动话术模板" in xhs_meta:
                    patch["互动话术模板"] = _mobile_trim(analysis["小红书包装"]["互动话术模板"], 56)
                if "小红书标题模板" in xhs_meta:
                    patch["小红书标题模板"] = analysis["小红书包装"]["小红书标题模板"]
                if "热门标签推荐" in xhs_meta:
                    patch["热门标签推荐"] = analysis["小红书包装"]["热门标签推荐"]
                if "更新时间" in xhs_meta:
                    patch["更新时间"] = int(datetime.now().timestamp() * 1000)

                patch = _normalize_fields_for_type(c, xhs_table_id, xhs_meta, patch)
                c.update_record_in_table(xhs_table_id, rid, patch)

                # Refresh md attachment.
                out_dir = os.path.join(PATHS["outputs"], "小红书笔记_v3", f"{work['作品名称']}_{work.get('作者','')}")
                os.makedirs(out_dir, exist_ok=True)
                md_path = os.path.join(out_dir, f"{work['作品名称']}-小红书笔记初稿.md")
                with open(md_path, "w", encoding="utf-8") as fw:
                    fw.write(note)
                if "小红书笔记初稿" in xhs_meta:
                    token = c.upload_file_to_bitable(md_path)
                    c.update_record_in_table(xhs_table_id, rid, {"小红书笔记初稿": [{"file_token": token}]})
                report["updated"] += 1
                report["details"].append({"record_id": rid, "work_name": work["作品名称"], "status": "updated", "reasons": item["reasons"]})
            except Exception as e:
                report["failed"] += 1
                report["details"].append({"record_id": rid, "work_name": work["作品名称"], "status": "failed", "error": str(e), "reasons": item["reasons"]})
    else:
        report["details"] = [
            {"record_id": x["record_id"], "work_name": x["work_name"], "reasons": x["reasons"]} for x in risky
        ]

    out_path = os.path.join(PATHS["logs"], "xhs_consistency_repair_report.json")
    with open(out_path, "w", encoding="utf-8") as fw:
        json.dump(report, fw, ensure_ascii=False, indent=2)
    print({"out_path": out_path, "scan_total": report["scan_total"], "risky_total": report["risky_total"], "updated": report["updated"], "failed": report["failed"], "apply": report["apply"]})


if __name__ == "__main__":
    main()
