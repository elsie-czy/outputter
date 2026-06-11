import argparse
import os
import re
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.related_sync import sync_related, update_main_links
from scripts.env_loader import load_dotenv


def _parse_report(path):
    work = {}
    analysis = {
        "开篇套路": [],
        "人物设定": {"女主": "", "男主": "", "亮点配角": ""},
        "冲突设计": {"第一层": "", "第二层": "", "第三层": ""},
        "情绪触发": [],
        "金句": [],
        "小红书包装": {},
        "配图提示词": [],
        "元信息": {"来源": "report"},
    }
    section = None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if not line:
                continue
            if section == "基础信息" and line.startswith("- "):
                m = re.match(r"-\s*([^:]+):\s*(.*)$", line)
                if m:
                    key, val = m.group(1).strip(), m.group(2).strip()
                    if key and val is not None:
                        work[key] = val
                continue
            if section == "开篇套路" and line.startswith("- "):
                analysis["开篇套路"].append(line[2:].strip())
                continue
            if section == "人物设定" and line.startswith("- "):
                m = re.match(r"-\s*(女主|男主|亮点配角):\s*(.*)$", line)
                if m:
                    analysis["人物设定"][m.group(1)] = m.group(2).strip()
                continue
            if section == "冲突设计" and line.startswith("- "):
                m = re.match(r"-\s*(第一层|第二层|第三层):\s*(.*)$", line)
                if m:
                    analysis["冲突设计"][m.group(1)] = m.group(2).strip()
                continue
            if section == "情绪触发" and line.startswith("- "):
                analysis["情绪触发"].append(line[2:].strip())
                continue
            if section == "金句" and line.startswith("- "):
                analysis["金句"].append(line[2:].strip())
                continue
    return work, analysis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="拆解报告路径")
    parser.add_argument("--main-record-id", required=True, help="主表 record_id")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

    report_path = os.path.abspath(args.report)
    if not os.path.exists(report_path):
        raise SystemExit(f"report not found: {report_path}")

    work, analysis = _parse_report(report_path)
    related_ids = sync_related(args.main_record_id, work, analysis)
    update_main_links(args.main_record_id, related_ids)
    counts = {k: len(v) for k, v in (related_ids or {}).items()}
    print("related synced:", counts)
    for k, ids in (related_ids or {}).items():
        if ids:
            print(f"- {k}: {ids}")


if __name__ == "__main__":
    main()
