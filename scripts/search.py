import os
import re
import json
import time
from urllib.parse import quote_plus
from html import unescape
from datetime import datetime

import requests

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from scripts.source_cleaner import clean_source_synopsis


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
RICH_SOURCE_FIELDS = [
    "目录",
    "章节摘要",
    "试读内容",
    "书评摘录",
    "热评",
    "读者评论",
    "正文片段",
    "高赞评论",
    "网络搜索摘要",
    "素材来源明细",
]


def _clean_ws(text):
    text = unescape(str(text or ""))
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _dedupe_keep_order(items, limit=12):
    out = []
    seen = set()
    for item in items or []:
        text = _clean_ws(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _merge_rich_fields(info, rich):
    for key in RICH_SOURCE_FIELDS:
        value = rich.get(key)
        if not value:
            continue
        if isinstance(value, list):
            info[key] = _dedupe_keep_order(value, limit=20)
        else:
            info[key] = value
    return info


def _extract_novel_id(link):
    m = re.search(r"novelid=(\d+)", str(link or ""))
    return m.group(1) if m else ""


def _extract_jjwxc_chapters(html):
    """Extract visible chapter titles from a JJWXC work page.

    The page markup has changed several times, so this deliberately uses broad
    link patterns and filters obvious navigation/metadata rows.
    """
    candidates = []
    patterns = [
        r"<a[^>]+href=[\"'][^\"']*onebook\.php\?novelid=\d+&chapterid=\d+[^\"']*[\"'][^>]*>(.*?)</a>",
        r"<a[^>]+href=[\"'][^\"']*chapterid=\d+[^\"']*[\"'][^>]*>(.*?)</a>",
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, html, flags=re.I | re.S):
            title = _clean_ws(raw)
            title = re.sub(r"^\s*(第[一二三四五六七八九十百千万\d]+章|chapter\s*\d+)[:：、.\-\s]*", "", title, flags=re.I)
            if not title:
                continue
            if any(bad in title for bad in ["点击", "收藏", "评论", "霸王票", "营养液", "返回", "作者有话"]):
                continue
            if len(title) > 42:
                continue
            candidates.append(title)
    return _dedupe_keep_order(candidates, limit=18)


def _extract_jjwxc_reviews(html):
    """Extract short visible reader-comment snippets from detail HTML when present."""
    text = _clean_ws(html)
    snippets = []
    for keyword in ["撒花", "好看", "大大", "加油", "更新", "评论", "喜欢", "心疼", "女主", "男主"]:
        for m in re.finditer(rf"[^。！？\n]{{0,36}}{re.escape(keyword)}[^。！？\n]{{0,46}}[。！？]?", text):
            s = _clean_ws(m.group(0))
            if 8 <= len(s) <= 90 and not any(bad in s for bad in ["登录", "注册", "投诉", "验证码", "手机版"]):
                snippets.append(s)
    return _dedupe_keep_order(snippets, limit=8)


def _extract_text_fragments(html, desc):
    text = _clean_ws(html)
    fragments = []
    for cue in ["内容标签", "主角", "配角", "一句话简介", "立意"]:
        m = re.search(rf"{cue}[:：]\s*([^\n]{{4,90}})", text)
        if m:
            fragments.append(f"{cue}：{m.group(1)}")
    if desc:
        for sent in re.split(r"[。！？!?；;\n]+", desc):
            sent = _clean_ws(sent)
            if 18 <= len(sent) <= 90:
                fragments.append(sent)
    return _dedupe_keep_order(fragments, limit=10)


def _fetch_jjwxc_rich_material(result):
    link = result.get("link", "")
    novel_id = _extract_novel_id(link)
    if not novel_id:
        return {}

    try:
        resp = requests.get(
            f"https://www.jjwxc.net/onebook.php?novelid={novel_id}",
            headers={"User-Agent": UA},
            timeout=20,
        )
        resp.encoding = "gbk"
        html = resp.text or ""
    except Exception as e:
        _log_search("jjwxc_detail", result.get("title", ""), result.get("author", ""), error=str(e))
        return {}

    desc = result.get("desc", "")
    chapters = _extract_jjwxc_chapters(html)
    reviews = _extract_jjwxc_reviews(html)
    fragments = _extract_text_fragments(html, desc)
    material = {
        "目录": chapters,
        "章节摘要": chapters[:8],
        "书评摘录": reviews,
        "读者评论": reviews,
        "正文片段": fragments,
        "素材来源明细": [
            {"type": "work_detail", "url": f"https://www.jjwxc.net/onebook.php?novelid={novel_id}", "fields": ["简介", "目录", "正文片段"]},
        ],
    }
    if reviews:
        material["素材来源明细"].append(
            {"type": "visible_reviews", "url": f"https://www.jjwxc.net/onebook.php?novelid={novel_id}", "fields": ["书评摘录", "读者评论"]}
        )
    return {k: v for k, v in material.items() if v}


def _extract_duckduckgo_results(html, limit=6):
    results = []
    # DuckDuckGo html results are intentionally simple; keep the parser broad so
    # the enrichment remains best-effort instead of brittle.
    pattern = r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
    matches = list(re.finditer(pattern, html or "", flags=re.I | re.S))
    for idx, match in enumerate(matches[:limit]):
        url = unescape(match.group(1))
        title = _clean_ws(match.group(2))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else min(len(html), start + 1500)
        block = html[start:end]
        snippet_match = re.search(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        if not snippet_match:
            snippet_match = re.search(r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', block, flags=re.I | re.S)
        snippet = _clean_ws(snippet_match.group(1) if snippet_match else "")
        if title or snippet:
            results.append({"title": title, "url": url, "snippet": snippet})
    if results:
        return results[:limit]

    # Fallback for mocked/simple HTML in tests.
    text = _clean_ws(html or "")
    for m in re.finditer(r"https?://\S+", text):
        url = m.group(0).rstrip(".,)")
        before = text[max(0, m.start() - 90):m.start()].strip()
        after = text[m.end():m.end() + 160].strip()
        results.append({"title": before[-60:], "url": url, "snippet": after[:160]})
        if len(results) >= limit:
            break
    return results


def _search_web_expanded(work):
    """Best-effort broad source enrichment when platform-specific search is thin.

    This does not pretend to have read the book. It collects traceable search
    result links and snippets so the material evidence layer can decide what is
    writable, cautious, or still insufficient.
    """
    name = (work.get("作品名称") or "").strip()
    author = (work.get("作者") or "").strip()
    if not name:
        return {}

    queries = [
        f'"{name}" "{author}" 简介' if author else f'"{name}" 简介',
        f'"{name}" 书评',
        f'"{name}" 前几章',
        f'"{name}" 好看吗',
    ]
    collected = []
    errors = []
    for query in queries:
        try:
            url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=8)
            html = resp.text or ""
            for result in _extract_duckduckgo_results(html, limit=4):
                hay = " ".join([result.get("title", ""), result.get("snippet", "")])
                if name not in hay:
                    continue
                if author and author not in hay and len(collected) < 2:
                    # Keep a couple title-only matches, but prefer title+author.
                    pass
                collected.append({**result, "query": query})
        except Exception as e:
            errors.append(f"{query}: {e}")
        if len(collected) >= 6:
            break

    if not collected:
        if errors:
            _log_search("web_expanded", name, author, error="；".join(errors[:2]))
        return {}

    snippets = _dedupe_keep_order([x.get("snippet") or x.get("title") for x in collected], limit=8)
    first_url = next((x.get("url") for x in collected if x.get("url")), "")
    info = {
        "搜索模式": "web_expanded",
        "搜索来源链接": first_url,
        "网络搜索摘要": snippets,
        "素材来源明细": [
            {
                "type": "web_search",
                "query": item.get("query", ""),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "fields": ["网络搜索摘要"],
            }
            for item in collected[:6]
        ],
    }
    # Only use snippets as a synopsis if the task itself has no synopsis. Search
    # snippets are evidence for traceability, not a replacement for platform text.
    if not str(work.get("简介") or "").strip() and snippets:
        info["简介"] = snippets[0]
        info["剧情简介"] = snippets[0]
    _log_search("web_expanded", name, author, result_source="web_expanded")
    return info


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
    rich = {}
    for key in RICH_SOURCE_FIELDS:
        if result.get(key):
            rich[key] = result.get(key)
    if source.startswith("jjwxc"):
        rich.update(_fetch_jjwxc_rich_material(result))
    return _merge_rich_fields(info, rich)


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
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
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
    search_mode = os.getenv("SEARCH_MODE", "auto").strip().lower()

    if not name:
        return _fallback_info(work)

    result = {}
    source_tag = "off"

    if search_mode in ("web", "web_expanded", "expanded"):
        result = _search_web_expanded(work)
        if result.get("搜索来源链接") or result.get("网络搜索摘要"):
            source_tag = result.get("搜索模式", "web_expanded")

    # 1. 优先晋江搜索（大部分作品都能在这找到）
    if not result:
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
    _merge_rich_fields(base, result)

    # 4. If platform-specific search cannot provide a traceable source or rich
    # material, try a broad web enrichment pass before giving up. This makes
    # "素材不足" a backend action trigger rather than a dead-end UI message.
    has_traceable_source = bool(base.get("搜索来源链接"))
    has_rich = any(base.get(k) for k in RICH_SOURCE_FIELDS if k != "素材来源明细")
    if not has_traceable_source or not has_rich:
        expanded = _search_web_expanded({**work, **base})
        if expanded:
            if expanded.get("搜索来源链接") and not base.get("搜索来源链接"):
                base["搜索来源链接"] = expanded["搜索来源链接"]
            if expanded.get("搜索模式") and source_tag == "off":
                base["搜索模式"] = expanded["搜索模式"]
            _merge_rich_fields(base, expanded)

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
        "目录": work.get("目录", []),
        "章节摘要": work.get("章节摘要", []),
        "试读内容": work.get("试读内容", ""),
        "书评摘录": work.get("书评摘录", []),
        "热评": work.get("热评", []),
        "读者评论": work.get("读者评论", []),
        "正文片段": work.get("正文片段", []),
        "高赞评论": work.get("高赞评论", []),
    }
