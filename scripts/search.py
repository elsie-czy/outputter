import os
import re
import json
import time
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from scripts.source_cleaner import clean_source_synopsis


def _build_search_info(work, result, source):
    """将抓取结果转换为标准 search_info 字典"""
    desc = str(result.get("desc", "") or "").strip()
    cleaned = clean_source_synopsis(desc or work.get("简介", ""))
    platform = work.get("平台", "") or result.get("platform", "")
    author = work.get("作者", "") or result.get("author", "")

    info = {
        "平台": platform,
        "分类": work.get("分类", "") or result.get("type", ""),
        "评分": work.get("评分", "") or str(result.get("score_num", "")),
        "字数（万）": work.get("字数（万）", ""),
        "完结状态": result.get("finish", "未知"),
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "搜索模式": source,
        "简介": cleaned.get("剧情简介") or desc or work.get("简介", ""),
        "剧情简介": cleaned.get("剧情简介", ""),
        "原始简介": cleaned.get("原始简介", desc or work.get("简介", "")),
        "非剧情信息": cleaned.get("非剧情信息", []),
        "作者": author,
        "作品名称": work.get("作品名称", ""),
        "取向": work.get("取向", ""),
        "搜索来源链接": result.get("link", ""),
        "收藏量": str(result.get("collect_num", "") or ""),
        "书评量": str(result.get("review_num", "") or ""),
        "平台评分": str(result.get("score_num", "") or ""),
        "在读量": str(result.get("inread_num", "") or ""),
    }
    return info


def _search_jjwxc(work):
    """在晋江搜索作品，按作者匹配，返回 enriched info。
    晋江搜索速度快（~2s），库大且简介详细，是主要搜索通道。"""
    name = (work.get("作品名称") or "").strip()
    author = (work.get("作者") or "").strip()
    if not name:
        return {}

    from scripts.prescreen_fetch_insert import fetch_jjwxc_search

    try:
        results = fetch_jjwxc_search(query=name, limit=5)
    except Exception as e:
        _log_search("jjwxc", name, author, error=str(e))
        return {}

    if not results:
        return {}

    # 匹配优先级：1) 作者完全匹配 2) 作品名完全匹配 3) 作者包含匹配
    for r in results:
        r_author = (r.get("author") or "").strip()
        if author and r_author and author == r_author:
            return _build_search_info(work, r, "jjwxc_exact")

    for r in results:
        r_title = (r.get("title") or "").strip()
        if name and r_title and name == r_title:
            return _build_search_info(work, r, "jjwxc_title")

    for r in results:
        r_author = (r.get("author") or "").strip()
        if author and r_author and (author in r_author or r_author in author):
            return _build_search_info(work, r, "jjwxc_fuzzy")

    return {}


def _search_fanqie(work):
    """在番茄搜索作品。
    注意：番茄只能通过排行池+关键词筛选，速度慢（10-20s），且只能匹配排行靠前的作品。
    大部分知名作品同时会出现在晋江，因此优先用晋江搜索。"""
    name = (work.get("作品名称") or "").strip()
    author = (work.get("作者") or "").strip()
    if not name:
        return {}

    from scripts.prescreen_fetch_insert import fetch_fanqie_rank_filtered

    try:
        # 严格控制搜索范围，避免超时
        results = fetch_fanqie_rank_filtered(query=name, limit=5, max_pool=20)
    except Exception as e:
        _log_search("fanqie", name, author, error=str(e))
        return {}

    if not results:
        return {}

    for r in results:
        r_author = (r.get("author") or "").strip()
        if author and r_author and author == r_author:
            return _build_search_info(work, r, "fanqie_exact")

    for r in results:
        r_title = (r.get("title") or "").strip()
        if name and r_title and name == r_title:
            return _build_search_info(work, r, "fanqie_title")

    for r in results:
        r_author = (r.get("author") or "").strip()
        if author and r_author and (author in r_author or r_author in author):
            return _build_search_info(work, r, "fanqie_fuzzy")

    return {}


def _log_search(platform, name, author, error=None, result_source=None):
    """记录搜索日志（debug 用）"""
    try:
        from scripts.utils import append_jsonl, now_ts
        from scripts.config import PATHS

        log_path = os.path.join(PATHS.get("logs", os.path.join(BASE_DIR, "data", "logs")),
                                "search_debug.jsonl")
        append_jsonl(log_path, {
            "ts": now_ts(),
            "platform": platform,
            "name": name,
            "author": author,
            "error": error or "",
            "source": result_source or "",
        })
    except Exception:
        pass


def search_work_info(work):
    """根据作品名+作者在线上平台搜索真实作品信息。

    搜索策略：
    1. 晋江优先 — 速度快(~2s)，库大，简介详细，大部分作品跨平台收录
    2. 如果平台是番茄且晋江没找到，再尝试番茄排行搜索
    3. 任何情况都保留本地数据兜底

    返回标准 search_info 字典，包含 简介/作者/完结状态/收藏量 等字段。
    """
    platform = (work.get("平台") or "").strip()
    name = (work.get("作品名称") or "").strip()
    author = (work.get("作者") or "").strip()

    if not name:
        return _fallback_info(work)

    result = {}
    source_tag = "off"

    # 1. 优先晋江搜索（大部分作品都能在这找到）
    result = _search_jjwxc(work)
    if result.get("简介"):
        source_tag = result.get("搜索模式", "jjwxc")

    # 2. 晋江无结果且平台是番茄时，尝试番茄搜索（慢但可能找到独家作品）
    if not result.get("简介") and platform in ("番茄", "fanqie"):
        result = _search_fanqie(work)
        if result.get("简介"):
            source_tag = result.get("搜索模式", "fanqie")

    # 3. 构建最终结果
    cleaned_work_intro = clean_source_synopsis(work.get("简介", ""))
    result_intro = result.get("剧情简介") or result.get("简介", "")
    base = {
        "平台": platform or result.get("平台", ""),
        "分类": work.get("分类") or result.get("分类", ""),
        "评分": work.get("评分") or result.get("评分", ""),
        "字数（万）": work.get("字数（万）", ""),
        "完结状态": result.get("完结状态") or work.get("完结状态", ""),
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "搜索模式": source_tag,
        "简介": result_intro or cleaned_work_intro.get("剧情简介") or work.get("简介", ""),
        "剧情简介": result.get("剧情简介") or cleaned_work_intro.get("剧情简介", ""),
        "原始简介": result.get("原始简介") or cleaned_work_intro.get("原始简介", ""),
        "非剧情信息": result.get("非剧情信息") or cleaned_work_intro.get("非剧情信息", []),
        "作者": author or result.get("作者", ""),
        "作品名称": name,
        "取向": work.get("取向", ""),
        "搜索来源链接": result.get("搜索来源链接", ""),
        "收藏量": result.get("收藏量", ""),
        "书评量": result.get("书评量", ""),
        "平台评分": result.get("平台评分", ""),
        "在读量": result.get("在读量", ""),
    }

    if result.get("简介"):
        _log_search(platform, name, author, result_source=source_tag)

    return base


def _fallback_info(work):
    """无作品名时直接回退"""
    cleaned = clean_source_synopsis(work.get("简介", ""))
    return {
        "平台": work.get("平台", ""),
        "分类": work.get("分类", ""),
        "评分": work.get("评分", ""),
        "字数（万）": work.get("字数（万）", ""),
        "完结状态": work.get("完结状态", ""),
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "搜索模式": "off",
        "简介": cleaned.get("剧情简介") or work.get("简介", ""),
        "剧情简介": cleaned.get("剧情简介", ""),
        "原始简介": cleaned.get("原始简介", work.get("简介", "")),
        "非剧情信息": cleaned.get("非剧情信息", []),
        "作者": work.get("作者", ""),
        "作品名称": "",
        "取向": work.get("取向", ""),
    }
