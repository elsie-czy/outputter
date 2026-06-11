import os

import requests
from scripts.feishu_config import FEISHU_CONFIG, get_feishu_config


class FeishuClient:
    def __init__(self):
        self.config = get_feishu_config()
        self.base_url = self.config["base_url"]
        self.app_token = self.config["app_token"]
        self.table_id = self.config["table_id"]
        self._token = None
        self._field_cache = {}
        self._field_meta_cache = {}

    def is_configured(self):
        return all(
            [
                self.config.get("app_id"),
                self.config.get("app_secret"),
                self.app_token,
                self.table_id,
            ]
        )

    def get_token(self):
        if self._token:
            return self._token
        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.config["app_id"],
            "app_secret": self.config["app_secret"],
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"feishu auth error: {data}")
        self._token = data.get("tenant_access_token")
        return self._token

    def _headers(self):
        token = self.get_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def get_table_fields(self, table_id):
        if table_id in self._field_cache:
            return self._field_cache[table_id]
        meta = self.get_table_field_meta(table_id)
        field_names = set(meta.keys())
        self._field_cache[table_id] = field_names
        return field_names

    def get_table_field_meta(self, table_id):
        if table_id in self._field_meta_cache:
            return self._field_meta_cache[table_id]
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields"
        resp = requests.get(url, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"feishu fields error: {data}")
        items = data.get("data", {}).get("items", [])
        meta = {}
        for item in items:
            name = item.get("field_name")
            if name:
                meta[name] = item
        self._field_meta_cache[table_id] = meta
        return meta

    def resolve_single_select_option_id(self, table_id, field_name, option_name):
        """
        For SingleSelect (type=3) fields, Feishu expects the option id as the value.
        This helper returns that option id when possible; returns None if not found.
        """
        meta = self.get_table_field_meta(table_id) or {}
        item = meta.get(field_name) or {}
        prop = item.get("property") or {}
        options = prop.get("options") or []
        want = str(option_name or "").strip()
        if not want:
            return None
        for opt in options:
            if str(opt.get("name", "")).strip() == want:
                return opt.get("id") or opt.get("option_id") or opt.get("value")
        return None

    def filter_fields(self, table_id, fields):
        available = self.get_table_fields(table_id)
        return {k: v for k, v in fields.items() if k in available}

    def _escape_filter_value(self, value):
        s = str(value or "")
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        s = s.replace("\n", " ").replace("\r", " ")
        return s

    def iter_records(self, table_id, page_size=200, filter_expr=None, view_id=None):
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        if filter_expr:
            params["filter"] = filter_expr
        if view_id:
            params["view_id"] = view_id
        page_token = None
        while True:
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
            try:
                data = resp.json()
            except Exception:
                data = {"code": -1, "msg": resp.text}
            if resp.status_code >= 400:
                raise RuntimeError(f"feishu list http error: status={resp.status_code}, body={data}")
            if data.get("code") != 0:
                raise RuntimeError(f"feishu list error: {data}")
            chunk = data.get("data", {}).get("items", [])
            for it in chunk:
                yield it
            page_token = data.get("data", {}).get("page_token")
            if not page_token:
                break

    def list_records(self, table_id, page_size=200, filter_expr=None, view_id=None):
        return list(self.iter_records(table_id, page_size=page_size, filter_expr=filter_expr, view_id=view_id))

    def list_records_page(self, table_id, page_size=50, page_token=None, filter_expr=None, view_id=None):
        """
        Fetch a single page of records and return (items, next_page_token).
        """
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        params = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        if view_id:
            params["view_id"] = view_id
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu list http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu list error: {data}")
        items = data.get("data", {}).get("items", []) or []
        next_token = data.get("data", {}).get("page_token")
        return items, next_token

    def _build_filter_expr_and_eq(self, match_fields):
        parts = []
        for k, v in match_fields.items():
            vv = self._escape_filter_value(v)
            parts.append(f'\"{k}\"=\"{vv}\"')
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return f"AND({','.join(parts)})"

    def find_record_id_by_fields(self, table_id, match_fields):
        # Prefer server-side filter; fall back to scan on any errors.
        filter_expr = None
        try:
            if all(isinstance(v, (str, int, float, bool)) for v in match_fields.values()):
                filter_expr = self._build_filter_expr_and_eq(match_fields)
                if filter_expr:
                    for item in self.iter_records(table_id, page_size=50, filter_expr=filter_expr):
                        return item.get("record_id")
        except Exception:
            pass

        for item in self.iter_records(table_id, page_size=200):
            fields = item.get("fields", {})
            if all(str(fields.get(k, "")).strip() == str(v).strip() for k, v in match_fields.items()):
                return item.get("record_id")
        return None

    def find_first_record_by_fields(self, table_id, match_fields):
        rid = self.find_record_id_by_fields(table_id, match_fields)
        if not rid:
            return None
        # Fast path: query by filter again to fetch the record payload
        try:
            filter_expr = self._build_filter_expr_and_eq(match_fields)
            for item in self.iter_records(table_id, page_size=10, filter_expr=filter_expr):
                if item.get("record_id") == rid:
                    return item
        except Exception:
            pass
        # Slow fallback
        for item in self.iter_records(table_id, page_size=200):
            if item.get("record_id") == rid:
                return item
        return None

    def create_record(self, fields):
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        resp = requests.post(url, headers=self._headers(), json={"fields": fields}, timeout=10)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu create http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu create error: {data}")
        return data.get("data", {}).get("record", {}).get("record_id")

    def update_record(self, record_id, fields):
        url = (
            f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/"
            f"{self.table_id}/records/{record_id}"
        )
        resp = requests.put(url, headers=self._headers(), json={"fields": fields}, timeout=10)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu update http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu update error: {data}")
        return True

    def create_record_in_table(self, table_id, fields):
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/records"
        resp = requests.post(url, headers=self._headers(), json={"fields": fields}, timeout=10)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu create http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu create error: {data}")
        return data.get("data", {}).get("record", {}).get("record_id")

    def update_record_in_table(self, table_id, record_id, fields):
        url = (
            f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/"
            f"{table_id}/records/{record_id}"
        )
        resp = requests.put(url, headers=self._headers(), json={"fields": fields}, timeout=10)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu update http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu update error: {data}")
        return True

    def upload_file_to_bitable(self, file_path):
        if not os.path.exists(file_path):
            raise RuntimeError(f"file not found: {file_path}")
        ext = os.path.splitext(file_path)[1].lower()
        mime = "application/octet-stream"
        if ext in [".md", ".txt"]:
            mime = "text/markdown"
        elif ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        elif ext == ".webp":
            mime = "image/webp"
        url = f"{self.base_url}/drive/v1/medias/upload_all"
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, mime)}
            data = {
                "file_name": os.path.basename(file_path),
                "parent_type": "bitable_file",
                "parent_node": self.app_token,
                "size": str(size),
            }
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=60)
        try:
            payload = resp.json()
        except Exception:
            payload = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu upload file http error: status={resp.status_code}, body={payload}")
        if payload.get("code") != 0:
            raise RuntimeError(f"feishu upload file error: {payload}")
        file_token = payload.get("data", {}).get("file_token")
        if not file_token:
            raise RuntimeError(f"feishu upload file missing file_token: {payload}")
        return file_token

    def create_field_in_table(self, table_id, field_name, field_type, prop=None):
        """
        Create a field in a given table.
        field_type:
          - 1 Text
          - 2 Number
          - 3 SingleSelect
          - 4 MultiSelect
          - 5 DateTime
        prop: dict for field property (e.g. select options)
        """
        url = f"{self.base_url}/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields"
        payload = {"field_name": field_name, "type": int(field_type)}
        if prop:
            payload["property"] = prop
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {"code": -1, "msg": resp.text}
        if resp.status_code >= 400:
            raise RuntimeError(f"feishu create field http error: status={resp.status_code}, body={data}")
        if data.get("code") != 0:
            raise RuntimeError(f"feishu create field error: {data}")
        return (data.get("data", {}) or {}).get("field", {}).get("field_id")
