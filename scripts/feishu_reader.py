import requests
from scripts.feishu_config import get_feishu_config
from scripts.utils import append_jsonl, now_ts
from scripts.config import PATHS


def _is_deconstructed(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip()
        if v in ["", "否", "未", "未拆解", "0", "false", "False"]:
            return False
        if v in ["是", "已", "已拆解", "1", "true", "True"]:
            return True
        # default: non-empty string treated as true
        return True
    if isinstance(value, list):
        # any non-empty selection treated as true
        return len(value) > 0
    if isinstance(value, dict):
        return True
    return bool(value)
from scripts.feishu_client import FeishuClient


def _normalize_select_fields(table_id, record_fields, client):
    meta = client.get_table_field_meta(table_id) or {}
    if not meta:
        return record_fields

    def _option_map(field_name):
        item = meta.get(field_name) or {}
        prop = item.get("property") or {}
        options = prop.get("options") or []
        mapping = {}
        for opt in options:
            oid = opt.get("id") or opt.get("option_id") or opt.get("value")
            name = opt.get("name") or opt.get("text")
            if oid:
                mapping[str(oid)] = str(name or oid)
        return mapping

    out = dict(record_fields or {})
    for name, fmeta in meta.items():
        ftype = fmeta.get("type")
        if name not in out or ftype not in (3, 4):
            continue
        opts = _option_map(name)
        if not opts:
            continue
        val = out.get(name)
        if ftype == 3:
            if isinstance(val, dict):
                raw = val.get("id") or val.get("option_id") or val.get("value") or val.get("name") or val.get("text")
                out[name] = opts.get(str(raw), raw)
            else:
                out[name] = opts.get(str(val), val)
        elif ftype == 4:
            if isinstance(val, list):
                mapped = []
                for it in val:
                    if isinstance(it, dict):
                        raw = it.get("id") or it.get("option_id") or it.get("value") or it.get("name") or it.get("text")
                        mapped.append(opts.get(str(raw), raw))
                    else:
                        mapped.append(opts.get(str(it), it))
                out[name] = mapped
            else:
                out[name] = [opts.get(str(val), val)] if val is not None else []
    return out


def list_records(table_id, page_size=50):
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")

    url = f"{client.base_url}/bitable/v1/apps/{client.app_token}/tables/{table_id}/records"
    headers = client._headers()
    params = {"page_size": page_size}

    items = []
    page_token = None
    while True:
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"feishu list error: {data}")
        chunk = data.get("data", {}).get("items", [])
        items.extend(chunk)
        page_token = data.get("data", {}).get("page_token")
        if not page_token:
            break
    return items


def select_work_from_topic_library():
    config = get_feishu_config()
    table_id = config["related_table_ids"].get("选题库")
    if not table_id:
        raise RuntimeError("未配置选题库 table_id")

    records = list_records(table_id)
    append_jsonl(
        PATHS["logs"] + "/feishu_topic_debug.jsonl",
        {
            "ts": now_ts(),
            "table_id": table_id,
            "count": len(records),
        },
    )
    for record in records:
        fields = record.get("fields", {})
        if not _is_deconstructed(fields.get("是否拆解")):
            # Normalize select option ids to names for readability and downstream consistency.
            record["fields"] = _normalize_select_fields(table_id, fields, FeishuClient())
            return record
    return None


def mark_work_deconstructed(record_id):
    config = get_feishu_config()
    table_id = config["related_table_ids"].get("选题库")
    if not table_id:
        raise RuntimeError("未配置选题库 table_id")

    client = FeishuClient()
    url = (
        f"{client.base_url}/bitable/v1/apps/{client.app_token}/tables/"
        f"{table_id}/records/{record_id}"
    )
    # In current topic table this field is text(type=1), use explicit text to avoid type mismatch.
    payloads = [
        {"fields": {"是否拆解": "已拆解"}},
        {"fields": {"是否拆解": "是"}},
        {"fields": {"是否拆解": True}},
    ]
    last_err = None
    for payload in payloads:
        try:
            resp = requests.put(url, headers=client._headers(), json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return True
            last_err = data
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"feishu update topic error: {last_err}")
