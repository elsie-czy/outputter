import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config


def _select_prop(names):
    # Feishu accepts option objects; name is the only required field.
    return {"options": [{"name": n} for n in names]}


def ensure_prescreen_schema():
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")

    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("选题库-初筛")
    if not table_id:
        raise RuntimeError("未配置 选题库-初筛 table_id（请在 .env 设置 FEISHU_TOPIC_PRESCREEN_TABLE_ID）")

    meta = client.get_table_field_meta(table_id) or {}
    existing = set(meta.keys())

    # Minimal-but-sufficient fields for sorting/filtering + dedupe + traceability.
    desired = [
        # Base traceability
        ("平台", 3, _select_prop(["晋江", "起点", "番茄", "其他"])),
        ("作品链接", 1, None),
        ("去重Key", 1, None),
        ("最近更新", 5, None),
        ("榜单来源", 1, None),
        ("榜单排名", 2, None),
        ("抓取批次", 1, None),
        ("简介", 1, None),
        ("是否完结", 3, _select_prop(["完结", "连载", "未知"])),
        ("在读量", 1, None),
        ("在读量_数值", 2, None),
        # Structured numeric fields (sorting)
        ("平台评分_数值", 2, None),
        ("书评量_数值", 2, None),
        ("收藏量_数值", 2, None),
        ("推荐热度_数值", 2, None),
        # Selection dimensions
        ("入选维度", 4, _select_prop(["高评分", "高热度", "高书评", "高收藏", "黑马", "待人工判断"])),
        ("综合得分", 2, None),
    ]

    created = []
    skipped = []
    failed = []

    for name, ftype, prop in desired:
        if name in existing:
            skipped.append(name)
            continue
        try:
            field_id = client.create_field_in_table(table_id, name, ftype, prop=prop)
            created.append({"name": name, "field_id": field_id, "type": ftype})
        except Exception as e:
            failed.append({"name": name, "error": str(e)})

    return {
        "table_id": table_id,
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }


def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    res = ensure_prescreen_schema()
    print(res)


if __name__ == "__main__":
    main()
