import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config


def _select_prop(names):
    return {"options": [{"name": n} for n in names]}


def _ensure_fields(client, table_id, desired):
    meta = client.get_table_field_meta(table_id) or {}
    existing = set(meta.keys())
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
    return {"created": created, "skipped": skipped, "failed": failed}


def ensure_note_metrics_schema(client, table_id):
    desired = [
        ("笔记唯一键", 1, None),
        ("实验ID", 1, None),
        ("实验版本", 3, _select_prop(["A", "B", "NA"])),
        ("实验变量", 1, None),
        ("笔记标题", 1, None),
        ("首次发布时间", 5, None),
        ("体裁", 3, _select_prop(["图文", "视频", "其他", "未知"])),
        ("账号名", 1, None),
        ("恢复期标签", 3, _select_prop(["恢复前", "恢复后", "未知"])),
        ("导入批次", 1, None),
        ("数据来源文件", 1, None),
        ("导入时间", 5, None),
        ("曝光", 2, None),
        ("观看量", 2, None),
        ("封面点击率", 2, None),
        ("点赞", 2, None),
        ("评论", 2, None),
        ("收藏", 2, None),
        ("涨粉", 2, None),
        ("分享", 2, None),
        ("人均观看时长", 2, None),
        ("弹幕", 2, None),
        ("互动总量", 2, None),
        ("互动率_按曝光", 2, None),
        ("收藏率_按观看", 2, None),
        ("评论率_按观看", 2, None),
        ("分享率_按观看", 2, None),
        ("涨粉率_按曝光", 2, None),
        ("爆款分", 2, None),
    ]
    return _ensure_fields(client, table_id, desired)


def ensure_hot_factors_schema(client, table_id):
    desired = [
        ("因子名称", 1, None),
        ("实验ID", 1, None),
        ("样本数", 2, None),
        ("均值爆款分", 2, None),
        ("相对全局差值", 2, None),
        ("收藏率（按观看）", 2, None),
        ("评论率（按观看）", 2, None),
        ("分享率（按观看）", 2, None),
        ("更新时间", 5, None),
    ]
    return _ensure_fields(client, table_id, desired)


def ensure_experiment_ledger_schema(client, table_id):
    desired = [
        ("实验ID", 1, None),
        ("实验状态", 3, _select_prop(["规划中", "进行中", "已完成", "已暂停"])),
        ("实验变量", 1, None),
        ("A版本说明", 1, None),
        ("B版本说明", 1, None),
        ("固定条件", 1, None),
        ("开始日期", 5, None),
        ("结束日期", 5, None),
        ("主指标", 1, None),
        ("胜出版本", 3, _select_prop(["A", "B", "平", "未判定"])),
        ("提升幅度", 2, None),
        ("样本数", 2, None),
        ("关联笔记唯一键", 1, None),
        ("结论", 1, None),
        ("更新时间", 5, None),
    ]
    return _ensure_fields(client, table_id, desired)


def ensure_account_7d_schema(client, table_id):
    desired = [
        ("快照唯一键", 1, None),
        ("数据类型", 3, _select_prop(["总体", "趋势"])),
        ("快照日期", 5, None),
        ("账号名", 1, None),
        ("导入批次", 1, None),
        ("数据来源文件", 1, None),
        ("导入时间", 5, None),
        ("趋势指标", 1, None),
        ("趋势日期", 5, None),
        ("趋势数值", 2, None),
        ("趋势来源sheet", 1, None),
        ("曝光", 2, None),
        ("观看", 2, None),
        ("观看率(%)", 2, None),
        ("7日波动系数", 2, None),
        ("封面点击率(%)", 2, None),
        ("平均观看时长(s)", 2, None),
        ("总观看时长(s)", 2, None),
        ("总完播率(%)", 2, None),
        ("曝光环比(%)", 2, None),
        ("观看环比(%)", 2, None),
        ("封面点击率环比(%)", 2, None),
        ("平均观看时长环比(%)", 2, None),
        ("总观看时长环比(%)", 2, None),
        ("总完播率环比(%)", 2, None),
    ]
    return _ensure_fields(client, table_id, desired)


def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    client = FeishuClient()
    if not client.is_configured():
        raise RuntimeError("飞书未配置")

    cfg = get_feishu_config()
    table_map = cfg.get("related_table_ids") or {}
    note_metrics_table = table_map.get("笔记结果库")
    hot_factors_table = table_map.get("爆款因子库")
    exp_ledger_table = table_map.get("实验台账")
    account_7d_table = table_map.get("账号7日快照")
    if not note_metrics_table:
        raise RuntimeError("未配置 FEISHU_NOTE_METRICS_TABLE_ID")
    if not hot_factors_table:
        raise RuntimeError("未配置 FEISHU_HOT_FACTORS_TABLE_ID")

    res = {
        "笔记结果库": ensure_note_metrics_schema(client, note_metrics_table),
        "爆款因子库": ensure_hot_factors_schema(client, hot_factors_table),
    }
    if exp_ledger_table:
        res["实验台账"] = ensure_experiment_ledger_schema(client, exp_ledger_table)
    else:
        res["实验台账"] = {"skipped_reason": "未配置 FEISHU_EXPERIMENT_LEDGER_TABLE_ID"}
    if account_7d_table:
        res["账号7日快照"] = ensure_account_7d_schema(client, account_7d_table)
    else:
        res["账号7日快照"] = {"skipped_reason": "未配置 FEISHU_ACCOUNT_7D_TABLE_ID"}
    print(res)


if __name__ == "__main__":
    main()
