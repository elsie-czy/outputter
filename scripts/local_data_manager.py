"""
本地数据管理模块
支持 owner 模式：飞书数据本地缓存 + 本地工作 + 归档到飞书
"""
import os
import json
from datetime import datetime

from scripts.config import PATHS, ensure_dirs
from scripts.utils import read_jsonl, write_jsonl, append_jsonl

# 本地数据目录
LOCAL_DATA_DIR = os.path.join(PATHS["data"], "local")
LOCAL_TOPICS_FILE = os.path.join(LOCAL_DATA_DIR, "topics.jsonl")
LOCAL_RESULTS_FILE = os.path.join(LOCAL_DATA_DIR, "results.jsonl")
LOCAL_ARCHIVE_FILE = os.path.join(LOCAL_DATA_DIR, "archive_queue.jsonl")


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
        
        # 转换为本地格式
        items = []
        for r in records:
            fields = r.get("fields", {}) or {}
            item = {
                "record_id": r.get("record_id", ""),
                "work_name": fields.get("作品名称", ""),
                "author": fields.get("作者", ""),
                "platform": fields.get("平台", ""),
                "category": fields.get("分类", ""),
                "word_count": fields.get("字数", 0),
                "favorites": fields.get("收藏", 0),
                "likes": fields.get("点赞", 0),
                "monthly_votes": fields.get("月票", 0),
                "recommend_votes": fields.get("推荐票", 0),
                "comments": fields.get("评论", 0),
                "rank": fields.get("排名", 0),
                "quality_score": fields.get("评分", 0),
                "是否拆解": fields.get("是否拆解", ""),
                "synced_at": _now(),
                "feishu_record_id": r.get("record_id", ""),
            }
            items.append(item)
        
        # 写入本地
        write_jsonl(LOCAL_TOPICS_FILE, items)
        
        return {"ok": True, "count": len(items)}
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
