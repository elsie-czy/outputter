import os
from scripts.feishu_config import FEISHU_CONFIG


def validate_required(table_name, fields, available_fields=None):
    required = FEISHU_CONFIG.get("required_fields", {}).get(table_name, [])
    # Optional relax: allow skipping certain required fields via env.
    skip_raw = os.getenv("REQUIRED_FIELDS_SKIP", "").strip()
    if skip_raw:
        skip = {s.strip() for s in skip_raw.split(",") if s.strip()}
        required = [k for k in required if k not in skip]
    if available_fields is not None:
        required = [k for k in required if k in available_fields]
    missing = []
    for key in required:
        val = fields.get(key)
        if val is None or val == "" or val == []:
            missing.append(key)
    return missing
