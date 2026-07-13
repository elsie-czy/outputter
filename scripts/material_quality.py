import re

from scripts.material_evidence import build_material_fact_check


RICH_SOURCE_KEYS = [
    "章节摘要",
    "目录",
    "试读内容",
    "书评摘录",
    "热评",
    "读者评论",
    "正文片段",
    "高赞评论",
]


def _text_len(value):
    if isinstance(value, list):
        return sum(len(str(x).strip()) for x in value if str(x).strip())
    if isinstance(value, dict):
        return sum(_text_len(v) for v in value.values())
    return len(str(value or "").strip())


def _sentence_count(text):
    return len([x for x in re.split(r"[。！？!?；;\n]+", str(text or "")) if x.strip()])


def assess_material_quality(work, search_info=None):
    """Assess whether source material can support a real note or only a quick-screen note."""
    search_info = search_info or {}
    intro = str(work.get("剧情简介") or work.get("简介") or search_info.get("剧情简介") or search_info.get("简介") or "").strip()
    source = str(work.get("简介来源") or search_info.get("搜索来源链接") or search_info.get("搜索模式") or "").strip()

    rich_keys = []
    rich_chars = 0
    for key in RICH_SOURCE_KEYS:
        size = _text_len(work.get(key) or search_info.get(key))
        if size:
            rich_keys.append(key)
            rich_chars += size

    intro_len = len(intro)
    intro_sentences = _sentence_count(intro)
    score = 0
    if intro_len >= 120:
        score += 1
    if intro_len >= 260 and intro_sentences >= 4:
        score += 1
    if source and source not in ("off", "fallback_required_field"):
        score += 1
    if rich_chars >= 160:
        score += 2

    if score >= 4:
        level = "rich"
    elif score >= 2:
        level = "usable"
    else:
        level = "thin"

    gaps = []
    if intro_len < 260:
        gaps.append("简介偏短，缺少足够剧情节点")
    if not rich_keys:
        gaps.append("缺少章节/试读/书评/评论等二级素材")
    if not source or source in ("off", "fallback_required_field"):
        gaps.append("缺少可追溯的线上来源")

    fact_check = build_material_fact_check(work, search_info)
    if fact_check.get("generation_mode") == "grounded_note":
        score = max(score, 4)
        level = "rich"
    elif fact_check.get("generation_mode") == "synopsis_grounded" and score < 2:
        score = 2
        level = "usable"

    return {
        "level": level,
        "score": score,
        "intro_len": intro_len,
        "intro_sentences": intro_sentences,
        "source": source,
        "rich_keys": rich_keys,
        "gaps": gaps,
        "recommendation": (
            "可生成正式拆书笔记" if level == "rich"
            else "只建议生成简介快筛笔记，避免伪深度"
        ),
        "fact_check": fact_check,
    }
