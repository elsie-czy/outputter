"""
本地数据管理模块
支持 owner 模式：飞书数据本地缓存 + 本地工作 + 归档到飞书
"""
import os
import json
from datetime import datetime

from scripts.config import PATHS, ensure_dirs
from scripts.utils import read_jsonl, write_jsonl, append_jsonl
from scripts.feishu_reader import _is_deconstructed

# 本地数据目录
LOCAL_DATA_DIR = os.path.join(PATHS["data"], "local")
LOCAL_TOPICS_FILE = os.path.join(LOCAL_DATA_DIR, "topics.jsonl")
LOCAL_RESULTS_FILE = os.path.join(LOCAL_DATA_DIR, "results.jsonl")
LOCAL_ARCHIVE_FILE = os.path.join(LOCAL_DATA_DIR, "archive_queue.jsonl")
ACTIVE_QUEUE_STATUSES = {
    "pending",
    "waiting",
    "processing",
    "deconstructing",
    "generating_note",
    "ai_scoring",
    "human_review",
    "generating_image",
    "paused",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_work_mode():
    """获取工作模式: owner / client"""
    return os.getenv("WORK_MODE", "client").strip().lower()


def ensure_local_dirs():
    """确保本地数据目录存在"""
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)


def sync_topics_from_feishu():
    """从飞书同步选题库到本地"""
    from scripts.feishu_client import FeishuClient
    from scripts.feishu_config import get_feishu_config
    
    ensure_local_dirs()
    client = FeishuClient()
    
    if not client.is_configured():
        return {"ok": False, "error": "飞书未配置"}
    
    config = get_feishu_config()
    topic_table_id = config.get("related_table_ids", {}).get("选题库", "")
    
    if not topic_table_id:
        return {"ok": False, "error": "选题库表ID未配置"}
    
    try:
        records = client.list_records(topic_table_id, page_size=1000)
        
        # 本地历史只作为提示，不再覆盖飞书选题库里的「是否拆解」。
        # 用户把飞书状态改回「否」时，应允许该作品重新出现在选题池。
        local_result_names = set()
        try:
            results = get_local_results()
            for r in results:
                n = (r.get("work_name") or "").strip()
                if n:
                    local_result_names.add(n)
        except Exception:
            pass
        active_queue_ids = set()
        active_queue_names = set()
        try:
            queue_file = os.path.join(PATHS["data"], "queue", "deconstruct_queue.jsonl")
            if os.path.exists(queue_file):
                with open(queue_file) as f:
                    for line in f:
                        if not line.strip():
                            continue
                        rec = json.loads(line)
                        status = str(rec.get("status") or "").strip()
                        if status in ACTIVE_QUEUE_STATUSES:
                            rid = str(rec.get("record_id") or "").strip()
                            n = (rec.get("work_name") or "").strip()
                            if rid:
                                active_queue_ids.add(rid)
                            if n:
                                active_queue_names.add(n)
        except Exception:
            pass

        # 转换为本地格式，仅按飞书「是否拆解」过滤。
        items = []
        for r in records:
            fields = r.get("fields", {}) or {}
            work_name = str(fields.get("作品名称", "")).strip()
            feishu_deconstructed = _is_deconstructed(fields.get("是否拆解"))
            rid = str(r.get("record_id", "") or "").strip()
            if feishu_deconstructed:
                continue  # 跳过已拆解的作品
            item = {
                "record_id": rid,
                "work_name": fields.get("作品名称", ""),
                "author": fields.get("作者", ""),
                "platform": fields.get("平台", ""),
                "category": fields.get("分类", ""),
                "synopsis": fields.get("简介", ""),
                "orientation": fields.get("取向", ""),
                "word_count": fields.get("字数", 0),
                "favorites": fields.get("收藏", 0),
                "likes": fields.get("点赞", 0),
                "monthly_votes": fields.get("月票", 0),
                "recommend_votes": fields.get("推荐票", 0),
                "comments": fields.get("评论", 0),
                "rank": fields.get("排名", 0),
                "quality_score": fields.get("评分", 0),
                "是否拆解": fields.get("是否拆解", ""),
                "has_local_result": work_name in local_result_names if work_name else False,
                "is_in_active_queue": (rid in active_queue_ids) or (work_name in active_queue_names if work_name else False),
                "synced_at": _now(),
                "feishu_record_id": rid,
            }
            items.append(item)
        
        # 写入本地
        write_jsonl(LOCAL_TOPICS_FILE, items)
        filtered_count = len(records) - len(items)
        return {"ok": True, "count": len(items), "total": len(records), "filtered": filtered_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_local_topics():
    """获取本地选题列表"""
    ensure_local_dirs()
    items = read_jsonl(LOCAL_TOPICS_FILE)
    return items or []


def save_result_to_local(result):
    """保存拆文结果到本地"""
    ensure_local_dirs()
    result["saved_at"] = _now()
    append_jsonl(LOCAL_RESULTS_FILE, result)


def get_local_results(status=None):
    """获取本地结果列表"""
    ensure_local_dirs()
    items = read_jsonl(LOCAL_RESULTS_FILE) or []
    if status:
        items = [i for i in items if i.get("archive_status") == status]
    return items


def get_pending_archive_count():
    """获取待归档数量"""
    results = get_local_results(status="pending")
    return len(results)


def archive_to_feishu(record_ids=None):
    """归档本地结果到飞书"""
    from scripts.feishu_client import FeishuClient
    from scripts.feishu_config import get_feishu_config
    
    ensure_local_dirs()
    client = FeishuClient()
    
    if not client.is_configured():
        return {"ok": False, "error": "飞书未配置"}
    
    config = get_feishu_config()
    main_table_id = config.get("table_id", "")
    note_table_id = config.get("related_table_ids", {}).get("小红书笔记库", "")
    
    if not main_table_id:
        return {"ok": False, "error": "主表ID未配置"}
    
    # 获取待归档记录
    results = get_local_results(status="pending")
    if record_ids:
        results = [r for r in results if r.get("record_id") in record_ids]
    
    if not results:
        return {"ok": True, "archived": 0, "message": "无待归档记录"}
    
    archived = 0
    errors = []
    
    for result in results:
        try:
            # 写入飞书主表
            fields = {
                "作品名称": result.get("work_name", ""),
                "作者": result.get("author", ""),
                "平台": result.get("platform", ""),
                "分类": result.get("category", ""),
                "拆解时间": _now(),
                "拆文结果": json.dumps(result.get("deconstruct_result", {}), ensure_ascii=False),
            }
            
            # 创建飞书记录
            record = client.create_record(main_table_id, fields)
            
            if record:
                # 标记已归档
                result["archive_status"] = "done"
                result["archived_at"] = _now()
                result["feishu_record_id"] = record.get("record_id", "")
                archived += 1
                
        except Exception as e:
            errors.append(f"{result.get('work_name')}: {str(e)}")
    
    # 更新本地文件
    all_results = read_jsonl(LOCAL_RESULTS_FILE) or []
    updated_results = []
    for r in all_results:
        for archived_r in results:
            if r.get("record_id") == archived_r.get("record_id"):
                r = archived_r
                break
        updated_results.append(r)
    write_jsonl(LOCAL_RESULTS_FILE, updated_results)
    
    return {
        "ok": True,
        "archived": archived,
        "errors": errors if errors else None
    }
