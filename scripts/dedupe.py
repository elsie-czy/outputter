import requests
from scripts.feishu_config import FEISHU_CONFIG
from scripts.feishu_client import FeishuClient


def find_by_title_author(title, author):
    client = FeishuClient()
    if not client.is_configured():
        return None

    # Primary: exact match with server-side filter + fallback scan.
    rid = client.find_record_id_by_fields(client.table_id, {"作品名称": title, "作者": author})
    if rid:
        return rid

    return None
