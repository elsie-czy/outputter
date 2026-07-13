from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, jsonify, render_template

from scripts.local_data_manager import get_local_topics
from scripts.queue_manager import get_queue, get_stats

bp = Blueprint("web_dashboard", __name__)


@bp.get("/dashboard")
def dashboard_page():
    """运营工作台首页。"""
    return render_template("dashboard.html", active_page="dashboard", page_title="AI内容生产驾驶舱")


@bp.get("/api/dashboard/overview")
def dashboard_overview():
    """聚合首页总览数据，不改动现有业务接口和队列结构。"""
    try:
        queue = get_queue(per_page=9999).get("items", [])
        stats = get_stats()
        topics = _safe_local_topics()
        return jsonify({"ok": True, "data": _build_overview(queue, stats, topics)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _build_overview(items: list[dict], stats: dict, topics: list[dict]) -> dict:
    completed_notes = [
        item for item in items
        if item.get("normalized_status") == "completed" and item.get("note_content")
    ]
    pending_publish = [item for item in completed_notes if not _is_published(item)]
    avg_score = _avg_score(items)

    return {
        "summary": {
            "notes_total": len(completed_notes),
            "reads_total": None,
            "deconstruct_tasks": stats.get("total", len(items)),
            "pending_publish": len(pending_publish),
            "days_active": _days_active(items),
            "today_goal": {
                "deconstruct": max(1, min(3, stats.get("pending", 0) or 1)),
                "notes": max(1, min(10, len(pending_publish) or stats.get("today_done", 0) or 1)),
            },
        },
        "trend": _build_trend(items),
        "top_topics": _top_topics(items, topics),
        "account": {
            "total": None,
            "metrics": [
                {"label": "总任务数", "value": len(items)},
                {"label": "已完成", "value": stats.get("done", 0)},
                {"label": "失败", "value": stats.get("failed", 0)},
                {"label": "平均评分", "value": avg_score},
            ],
        },
        "content_status": {
            "pending": stats.get("pending", 0),
            "processing": stats.get("processing", 0),
            "review": stats.get("review", 0),
            "completed": stats.get("done", 0),
            "failed": stats.get("failed", 0),
        },
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "empty_metrics": ["reads_total", "account_growth"],
        },
    }


def _safe_local_topics() -> list[dict]:
    try:
        return get_local_topics()
    except Exception:
        return []


def _build_trend(items: list[dict]) -> list[dict]:
    today = datetime.now().date()
    rows = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        date_text = day.isoformat()
        rows.append({
            "date": date_text,
            "completed": sum(1 for item in items if _date_key(item.get("completed_at")) == date_text),
            "created": sum(1 for item in items if _date_key(item.get("created_at")) == date_text),
        })
    return rows


def _top_topics(items: list[dict], topics: list[dict]) -> list[dict]:
    pool = {}
    for source in topics + items:
        name = str(source.get("work_name") or source.get("作品名称") or "").strip()
        if not name:
            continue
        key = (name, str(source.get("author") or source.get("作者") or "").strip())
        score = _topic_rank_score(source)
        if key not in pool or score > pool[key]["rank_score"]:
            pool[key] = {
                "title": name,
                "author": key[1] or "未知作者",
                "platform": source.get("platform") or source.get("平台") or "",
                "category": source.get("category") or source.get("分类") or "",
                "favorites": _number(source.get("favorites") or source.get("收藏")),
                "likes": _number(source.get("likes") or source.get("点赞")),
                "comments": _number(source.get("comments") or source.get("评论")),
                "quality_score": _score_total(source.get("quality_score") or source.get("评分")),
                "created_at": source.get("created_at") or source.get("synced_at") or "",
                "rank_score": score,
            }
    ranked = sorted(pool.values(), key=lambda item: item["rank_score"], reverse=True)
    return [{k: v for k, v in item.items() if k != "rank_score"} for item in ranked[:5]]


def _topic_rank_score(item: dict) -> float:
    score = (_score_total(item.get("quality_score") or item.get("评分")) or 0) * 100
    score += _number(item.get("favorites") or item.get("收藏")) * 3
    score += _number(item.get("likes") or item.get("点赞")) * 2
    score += _number(item.get("comments") or item.get("评论"))
    parsed = _parse_datetime(item.get("created_at") or item.get("synced_at"))
    if parsed:
        score += parsed.timestamp() / 100000000
    return score


def _is_published(item: dict) -> bool:
    if item.get("published") is True:
        return True
    result = item.get("deconstruct_result") or {}
    published = result.get("是否发布笔记") if isinstance(result, dict) else None
    return str(published or "").strip() in ("是", "已发布", "true", "True", "1")


def _days_active(items: list[dict]) -> int:
    dates = [_parse_datetime(item.get("created_at")) for item in items]
    dates = [d.date() for d in dates if d]
    if not dates:
        return 1
    return max(1, (datetime.now().date() - min(dates)).days + 1)


def _date_key(value) -> Optional[str]:
    parsed = _parse_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _parse_datetime(value) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(timestamp)
        except Exception:
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _avg_score(items: list[dict]) -> Optional[float]:
    scores = [_score_total(item.get("quality_score")) for item in items]
    scores = [score for score in scores if score is not None]
    return round(sum(scores) / len(scores), 1) if scores else None


def _score_total(score) -> Optional[float]:
    if isinstance(score, dict):
        score = score.get("total")
    return _number(score, none_on_blank=True)


def _number(value, none_on_blank: bool = False) -> Optional[float]:
    if value in (None, ""):
        return None if none_on_blank else 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None if none_on_blank else 0
