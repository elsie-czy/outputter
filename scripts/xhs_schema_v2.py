"""小红书笔记库 V2 字段迁移脚本"""
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config


def ensure_xhs_note_schema_v2():
    """确保小红书笔记库包含 V2 所需字段"""
    load_dotenv(os.path.join(BASE_DIR, ".env"))

    client = FeishuClient()
    if not client.is_configured():
        print("飞书未配置，跳过 schema 迁移")
        return

    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
    if not table_id:
        print("小红书笔记库 table_id 未配置")
        return

    desired = [
        ("修改日志", 1, None),
        ("修改后评分", 2, None),
        ("笔记正文全文", 1, None),
        ("AI质量评分", 2, None),
    ]

    meta = client.get_table_field_meta(table_id) or {}
    existing = set(meta.keys())
    created = []
    skipped = []

    for name, ftype, prop in desired:
        if name in existing:
            skipped.append(name)
            continue
        try:
            field_id = client.create_field_in_table(table_id, name, ftype, prop=prop)
            created.append({"name": name, "field_id": field_id, "type": ftype})
            print(f"  ✓ 创建字段: {name} (type={ftype}, id={field_id})")
        except Exception as e:
            print(f"  ✗ 创建字段失败: {name} — {e}")

    print(f"\n创建 {len(created)} 个，跳过 {len(skipped)} 个（已存在）")
    return created, skipped


if __name__ == "__main__":
    ensure_xhs_note_schema_v2()
