import os
import time
import json
from datetime import datetime

from scripts.config import PATHS, ensure_dirs
from scripts.utils import append_jsonl, read_jsonl, write_jsonl

QUEUE_FILE = os.path.join(PATHS["queue"], "deconstruct_queue.jsonl")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _acquire_lock():
    lock_path = os.path.join(PATHS["queue"], "deconstruct_queue.lock")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock():
    lock_path = os.path.join(PATHS["queue"], "deconstruct_queue.lock")
    try:
        os.remove(lock_path)
    except Exception:
        pass


def enqueue_works(works):
    """批量入队。works 是 list[dict]，每个 dict 含 作品名称/作者/平台/分类 等"""
    ensure_dirs()
    entries = []
    for w in works:
        entries.append({
            "record_id": w.get("record_id", ""),
            "work_name": str(w.get("作品名称", "")),
            "author": str(w.get("作者", "")),
            "platform": str(w.get("平台", "")),
            "category": str(w.get("分类", "")),
            "status": "pending",
            "error": None,
            "retry_count": 0,
            "deconstruct_result": None,
            "note_content": None,
            "quality_score": None,
            "created_at": _now(),
            "processing_start": None,
            "completed_at": None,
        })
    for entry in entries:
        append_jsonl(QUEUE_FILE, entry)
    return len(entries)


def get_queue(status=None, platform=None, category=None, q=None, page=1, per_page=20):
    """读取队列，支持筛选/搜索/分页"""
    items = read_jsonl(QUEUE_FILE)
    if not items:
        return {"items": [], "total": 0, "page": page, "per_page": per_page}

    # 筛选
    filtered = items
    if status:
        filtered = [i for i in filtered if i.get("status") == status]
    if platform:
        filtered = [i for i in filtered if i.get("platform") == platform]
    if category:
        filtered = [i for i in filtered if i.get("category") == category]
    if q:
        q_lower = q.lower()
        filtered = [i for i in filtered
                     if q_lower in str(i.get("work_name", "")).lower()
                     or q_lower in str(i.get("author", "")).lower()]

    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": filtered[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def update_status(record_id, status, error=None, deconstruct_result=None,
                  note_content=None, quality_score=None):
    """更新队列中某条记录的状态"""
    items = read_jsonl(QUEUE_FILE)
    updated = False
    for i in items:
        if i.get("record_id") == record_id:
            i["status"] = status
            if error is not None:
                i["error"] = str(error)[:500]
            if deconstruct_result is not None:
                i["deconstruct_result"] = deconstruct_result
            if note_content is not None:
                i["note_content"] = note_content
            if quality_score is not None:
                i["quality_score"] = quality_score
            if status == "processing" and not i.get("processing_start"):
                i["processing_start"] = _now()
            if status in ("done", "failed"):
                i["completed_at"] = _now()
            updated = True
            break
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def batch_update_status(record_ids, status):
    """批量更新状态"""
    if not record_ids:
        return 0
    items = read_jsonl(QUEUE_FILE)
    count = 0
    for i in items:
        if i.get("record_id") in record_ids:
            i["status"] = status
            if status == "processing" and not i.get("processing_start"):
                i["processing_start"] = _now()
            if status in ("done", "failed"):
                i["completed_at"] = _now()
            count += 1
    if count > 0:
        write_jsonl(QUEUE_FILE, items)
    return count


def retry_task(record_id):
    """重置失败任务为 pending"""
    items = read_jsonl(QUEUE_FILE)
    updated = False
    for i in items:
        if i.get("record_id") == record_id and i.get("status") == "failed":
            i["status"] = "retry"
            i["error"] = None
            i["processing_start"] = None
            i["completed_at"] = None
            i["retry_count"] = i.get("retry_count", 0) + 1
            updated = True
            break
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def get_stats():
    """队列统计：今日产出/完成率/均耗时"""
    items = read_jsonl(QUEUE_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(items)
    done = [i for i in items if i.get("status") == "done"]
    failed = [i for i in items if i.get("status") == "failed"]
    today_done = [i for i in done
                   if str(i.get("completed_at", "")).startswith(today)]

    avg_duration = None
    durations = []
    for i in done:
        start = i.get("processing_start")
        end = i.get("completed_at")
        if start and end:
            try:
                s = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                e = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
                durations.append((e - s).total_seconds())
            except Exception:
                pass
    if durations:
        avg_duration = round(sum(durations) / len(durations), 1)

    completion_rate = round(len(done) / total * 100, 1) if total > 0 else 0

    scores = [i.get("quality_score") for i in items if i.get("quality_score")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "total": total,
        "done": len(done),
        "failed": len(failed),
        "pending": total - len(done) - len(failed),
        "today_done": len(today_done),
        "completion_rate": completion_rate,
        "avg_duration_sec": avg_duration,
        "avg_score": avg_score,
    }


def get_next_pending():
    """获取下一个待处理任务"""
    items = read_jsonl(QUEUE_FILE)
    for i in items:
        if i.get("status") in ("pending", "retry"):
            return i
    return None
