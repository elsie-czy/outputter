import os
import re
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient


def _build_option_maps(meta_item):
    opts = (meta_item.get("property") or {}).get("options") or []
    id_to_name = {}
    name_to_id = {}
    for o in opts:
        oid = o.get("id") or o.get("option_id") or o.get("value")
        name = str(o.get("name") or o.get("text") or "").strip()
        if oid:
            id_to_name[str(oid)] = name
        if name:
            name_to_id[name] = str(oid) if oid else ""
    return id_to_name, name_to_id


def _fix_field(client, table_id, field_name, dry_run=False):
    meta = client.get_table_field_meta(table_id)
    item = meta.get(field_name) or {}
    if item.get("type") != 3:
        return 0
    id_to_name, name_to_id = _build_option_maps(item)
    if not id_to_name:
        return 0

    changed = 0
    for rec in client.iter_records(table_id, page_size=200):
        rid = rec.get("record_id")
        fields = rec.get("fields", {}) or {}
        val = fields.get(field_name)
        if not isinstance(val, str):
            continue
        cur_name = id_to_name.get(val, "")
        # If current option name is itself an option id, remap to that id.
        if re.fullmatch(r"opt[0-9A-Za-z]+", cur_name) and cur_name in id_to_name:
            new_id = cur_name
        else:
            continue
        if new_id == val:
            continue
        if not dry_run:
            client.update_record_in_table(table_id, rid, {field_name: new_id})
        changed += 1
    return changed


def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
    client = FeishuClient()
    if not client.is_configured():
        raise SystemExit("Feishu 未配置")

    targets = [
        (client.table_id, "取向"),
        (client.config.get("related_table_ids", {}).get("小红书笔记库"), "是否发布笔记"),
    ]
    total = 0
    for table_id, field_name in targets:
        if not table_id:
            continue
        total += _fix_field(client, table_id, field_name, dry_run=False)
    print("fixed_records:", total)


if __name__ == "__main__":
    main()
