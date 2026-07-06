import os
import time
import json
from datetime import datetime

from scripts.config import PATHS, ensure_dirs
from scripts.utils import append_jsonl, read_jsonl, write_jsonl

QUEUE_FILE = os.path.join(PATHS["queue"], "deconstruct_queue.jsonl")

# 状态枚举
STATUS_WAITING = "waiting"
STATUS_DECONSTRUCTING = "deconstructing"
STATUS_GENERATING_NOTE = "generating_note"
STATUS_AI_SCORING = "ai_scoring"
STATUS_HUMAN_REVIEW = "human_review"  # 已废弃，向后兼容
STATUS_GENERATING_IMAGE = "generating_image"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_PAUSED = "paused"
STATUS_CANCELLED = "cancelled"


def normalize_status(status) -> str:
    """Map legacy worker stages to the stable UI status set."""
    mapping = {
        "waiting": "pending",
        "pending": "pending",
        "retry": "pending",
        "paused": "pending",
        "processing": "processing",
        "deconstructing": "processing",
        "generating_note": "processing",
        "ai_scoring": "processing",
        "generating_image": "processing",
        "human_review": "review",   # 已废弃，向后兼容，映射为 review 显示
        "review": "review",
        "done": "completed",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "failed",
    }
    return mapping.get(str(status or "").strip().lower(), "pending")

# 阶段进度映射（共6步）
STAGE_PROGRESS = {
    STATUS_WAITING: 0,
    STATUS_DECONSTRUCTING: 1,      # 1/6 = 17%
    STATUS_GENERATING_NOTE: 2,     # 2/6 = 33%
    STATUS_AI_SCORING: 3,          # 3/6 = 50%
    STATUS_HUMAN_REVIEW: 4,        # 4/6 = 67%
    STATUS_GENERATING_IMAGE: 5,    # 5/6 = 83%
    STATUS_DONE: 6,                # 6/6 = 100%
    STATUS_FAILED: 0,
    STATUS_PAUSED: 0,
    STATUS_CANCELLED: 0,
}

# 判断任务是否真正完成（需要图片生成）
def is_task_truly_done(task: dict) -> bool:
    """判断任务是否真正完成（包括图片生成）"""
    if task.get("status") != STATUS_DONE:
        return False
    # 如果配置了图片生成，需要检查图片是否生成
    if os.getenv("IMAGE_GEN_ENABLED", "false").strip().lower() in ("1", "true", "yes"):
        images = task.get("images", {})
        if not images.get("cover"):
            return False
    return True

def get_task_progress(task: dict) -> int:
    """获取任务真实进度（考虑图片生成）"""
    status = task.get("status", "")
    base_progress = STAGE_PROGRESS.get(status, 0)
    
    # 如果是 done 状态但图片未生成，进度应该是 83% 而不是 100%
    if status == STATUS_DONE and not is_task_truly_done(task):
        return 5  # 5/6 = 83%
    
    return base_progress

STAGE_LABELS = {
    STATUS_WAITING: "等待中",
    STATUS_DECONSTRUCTING: "拆文分析",
    STATUS_GENERATING_NOTE: "生成笔记",
    STATUS_AI_SCORING: "AI评分",
    STATUS_HUMAN_REVIEW: "人工审核",
    STATUS_GENERATING_IMAGE: "生成图片",
    STATUS_DONE: "已完成",
    STATUS_FAILED: "已失败",
    STATUS_PAUSED: "已暂停",
    STATUS_CANCELLED: "已终止",
}


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


def enqueue_works(works, image_strategy=None, image_provider=None):
    """批量入队。works 是 list[dict]；image_strategy/image_provider 为任务级生图配置（可选）。"""
    ensure_dirs()
    existing = read_jsonl(QUEUE_FILE)
    existing_ids = {
        str(i.get("record_id") or "").strip()
        for i in existing
        if str(i.get("record_id") or "").strip()
    }
    seen_ids = set()
    entries = []
    for w in works:
        rid = str(w.get("record_id") or "").strip()
        if not rid or rid in existing_ids or rid in seen_ids:
            continue
        seen_ids.add(rid)
        entries.append({
            "record_id": rid,
            "work_name": str(w.get("作品名称", "")),
            "author": str(w.get("作者", "")),
            "platform": str(w.get("平台", "")),
            "category": str(w.get("分类", "")),
            "synopsis": str(w.get("简介", "")),
            "orientation": str(w.get("取向", "")),
            "word_count": w.get("字数", 0),
            "favorites": w.get("收藏", 0),
            "likes": w.get("点赞", 0),
            "monthly_votes": w.get("月票", 0),
            "recommend_votes": w.get("推荐票", 0),
            "comments": w.get("评论", 0),
            "rank": w.get("排名", 0),
            "image_strategy": image_strategy or None,
            "image_provider": image_provider or None,
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

    items = [_with_normalized_status(i) for i in items]

    # 筛选
    filtered = items
    if status:
        wanted = {
            normalize_status(s)
            for s in str(status).split(",")
            if str(s).strip()
        }
        filtered = [i for i in filtered if i.get("normalized_status") in wanted]
    if platform:
        filtered = [i for i in filtered if i.get("platform") == platform]
    if category:
        filtered = [i for i in filtered if i.get("category") == category]
    if q:
        q_lower = q.lower()
        filtered = [i for i in filtered
                     if q_lower in str(i.get("work_name", "")).lower()
                     or q_lower in str(i.get("author", "")).lower()]

    filtered = sorted(
        filtered,
        key=lambda i: str(i.get("created_at") or ""),
        reverse=True,
    )

    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": filtered[start:end],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


def _with_normalized_status(item: dict) -> dict:
    normalized = dict(item)
    normalized["normalized_status"] = normalize_status(item.get("status"))
    return normalized


def update_status(record_id, status, error=None, deconstruct_result=None,
                  note_content=None, quality_score=None, images=None, step_times=None):
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
            if images is not None:
                i["images"] = images
            if step_times is not None:
                i["step_times"] = step_times
            if status in ("processing", STATUS_DECONSTRUCTING, STATUS_GENERATING_NOTE, STATUS_AI_SCORING, 
                         STATUS_HUMAN_REVIEW, STATUS_GENERATING_IMAGE) and not i.get("processing_start"):
                i["processing_start"] = _now()
            if status in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED):
                i["completed_at"] = _now()
            updated = True
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def update_task_fields(record_id, **fields):
    """更新队列记录的指定字段，不改变任务状态。"""
    allowed = {
        "note_content",
        "quality_score",
        "modification_log",
        "main_record_id",
        "xhs_record_id",
        "deconstruct_result",
        "images",
        "step_times",
        "title_options",
    }
    patch = {k: v for k, v in fields.items() if k in allowed}
    if not patch:
        return False

    items = read_jsonl(QUEUE_FILE)
    updated = False
    for item in items:
        if item.get("record_id") == record_id:
            item.update(patch)
            item["updated_at"] = _now()
            updated = True
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def pause_task(record_id):
    """暂停任务"""
    items = read_jsonl(QUEUE_FILE)
    updated = False
    for i in items:
        if i.get("record_id") == record_id and i.get("status") not in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED):
            i["status"] = STATUS_PAUSED
            updated = True
            break
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def cancel_task(record_id):
    """终止任务"""
    items = read_jsonl(QUEUE_FILE)
    updated = False
    for i in items:
        if i.get("record_id") == record_id and i.get("status") not in (STATUS_DONE, STATUS_CANCELLED):
            i["status"] = STATUS_CANCELLED
            i["completed_at"] = _now()
            updated = True
            break
    if updated:
        write_jsonl(QUEUE_FILE, items)
    return updated


def batch_pause_tasks(record_ids):
    """批量暂停任务"""
    if not record_ids:
        return 0
    items = read_jsonl(QUEUE_FILE)
    count = 0
    for i in items:
        if i.get("record_id") in record_ids and i.get("status") not in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED):
            i["status"] = STATUS_PAUSED
            count += 1
    if count > 0:
        write_jsonl(QUEUE_FILE, items)
    return count


def batch_retry_tasks(record_ids):
    """批量重试任务"""
    if not record_ids:
        return 0
    items = read_jsonl(QUEUE_FILE)
    count = 0
    for i in items:
        if i.get("record_id") in record_ids and i.get("status") == STATUS_FAILED:
            i["status"] = STATUS_WAITING
            i["error"] = None
            i["processing_start"] = None
            i["completed_at"] = None
            i["retry_count"] = i.get("retry_count", 0) + 1
            count += 1
    if count > 0:
        write_jsonl(QUEUE_FILE, items)
    return count


def batch_cancel_tasks(record_ids):
    """批量终止任务"""
    if not record_ids:
        return 0
    items = read_jsonl(QUEUE_FILE)
    count = 0
    for i in items:
        if i.get("record_id") in record_ids and i.get("status") not in (STATUS_DONE, STATUS_CANCELLED):
            i["status"] = STATUS_CANCELLED
            i["completed_at"] = _now()
            count += 1
    if count > 0:
        write_jsonl(QUEUE_FILE, items)
    return count


def batch_update_status(record_ids, status):
    """批量更新状态（兼容旧接口）"""
    if not record_ids:
        return 0
    items = read_jsonl(QUEUE_FILE)
    count = 0
    for i in items:
        if i.get("record_id") in record_ids:
            i["status"] = status
            if status in (STATUS_DECONSTRUCTING, STATUS_GENERATING_NOTE, STATUS_AI_SCORING,
                         STATUS_HUMAN_REVIEW, STATUS_GENERATING_IMAGE) and not i.get("processing_start"):
                i["processing_start"] = _now()
            if status in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED):
                i["completed_at"] = _now()
            count += 1
    if count > 0:
        write_jsonl(QUEUE_FILE, items)
    return count


def retry_task(record_id):
    """重试失败任务"""
    items = read_jsonl(QUEUE_FILE)
    updated = False
    for i in items:
        if i.get("record_id") == record_id and i.get("status") == STATUS_FAILED:
            i["status"] = STATUS_WAITING
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
    items = [_with_normalized_status(i) for i in read_jsonl(QUEUE_FILE)]
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(items)
    done = [i for i in items if i.get("normalized_status") == "completed"]
    failed = [i for i in items if i.get("normalized_status") == "failed"]
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

    scores = [_score_total(i.get("quality_score")) for i in items if i.get("quality_score")]
    scores = [s for s in scores if s is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "total": total,
        "done": len(done),
        "failed": len(failed),
        "pending": len([i for i in items if i.get("normalized_status") == "pending"]),
        "processing": len([i for i in items if i.get("normalized_status") == "processing"]),
        "review": len([i for i in items if i.get("normalized_status") == "review"]),
        "today_done": len(today_done),
        "completion_rate": completion_rate,
        "avg_duration_sec": avg_duration,
        "avg_score": avg_score,
    }


def get_next_pending():
    """获取下一个待处理任务"""
    items = read_jsonl(QUEUE_FILE)
    blocked_ids = {
        i.get("record_id")
        for i in items
        if i.get("record_id") and normalize_status(i.get("status")) in ("processing", "completed")
    }
    for i in items:
        rid = i.get("record_id")
        if rid in blocked_ids:
            continue
        if normalize_status(i.get("status")) == "pending":
            return i
    return None


def _score_total(score):
    if isinstance(score, dict):
        value = score.get("total")
    else:
        value = score
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
