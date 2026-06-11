import argparse
import os
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config


def to_ms(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return int(datetime.strptime(s, fmt).timestamp() * 1000)
        except Exception:
            pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--experiment-id", required=True, help="实验ID，建议格式 exp_YYYYMMDD_xx")
    p.add_argument("--status", default="进行中", help="实验状态")
    p.add_argument("--variable", default="", help="实验变量")
    p.add_argument("--a-desc", default="", help="A版本说明")
    p.add_argument("--b-desc", default="", help="B版本说明")
    p.add_argument("--controls", default="", help="固定条件")
    p.add_argument("--start-date", default="", help="开始日期 YYYY-MM-DD")
    p.add_argument("--end-date", default="", help="结束日期 YYYY-MM-DD")
    p.add_argument("--metric", default="", help="主指标")
    p.add_argument("--winner", default="未判定", help="胜出版本 A/B/平/未判定")
    p.add_argument("--lift", type=float, default=0.0, help="提升幅度")
    p.add_argument("--samples", type=float, default=0.0, help="样本数")
    p.add_argument("--note-uids", default="", help="关联笔记唯一键，逗号分隔")
    p.add_argument("--conclusion", default="", help="结论")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    c = FeishuClient()
    if not c.is_configured():
        raise RuntimeError("飞书未配置")
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("实验台账")
    if not table_id:
        raise RuntimeError("未配置 FEISHU_EXPERIMENT_LEDGER_TABLE_ID")

    exp_id = (args.experiment_id or "").strip()
    if not exp_id:
        raise RuntimeError("experiment-id 不能为空")
    fields = {
        "实验ID": exp_id,
        "实验状态": (args.status or "").strip(),
        "实验变量": (args.variable or "").strip(),
        "A版本说明": (args.a_desc or "").strip(),
        "B版本说明": (args.b_desc or "").strip(),
        "固定条件": (args.controls or "").strip(),
        "开始日期": to_ms(args.start_date),
        "结束日期": to_ms(args.end_date),
        "主指标": (args.metric or "").strip(),
        "胜出版本": (args.winner or "").strip(),
        "提升幅度": float(args.lift or 0),
        "样本数": float(args.samples or 0),
        "关联笔记唯一键": (args.note_uids or "").strip(),
        "结论": (args.conclusion or "").strip(),
        "更新时间": int(datetime.now().timestamp() * 1000),
    }
    fields = {k: v for k, v in c.filter_fields(table_id, fields).items() if v is not None}

    rec = c.find_first_record_by_fields(table_id, {"实验ID": exp_id})
    if rec and rec.get("record_id"):
        c.update_record_in_table(table_id, rec["record_id"], fields)
        print({"action": "updated", "experiment_id": exp_id, "record_id": rec["record_id"]})
    else:
        rid = c.create_record_in_table(table_id, fields)
        print({"action": "created", "experiment_id": exp_id, "record_id": rid})


if __name__ == "__main__":
    main()
