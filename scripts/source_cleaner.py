import re


_EVENT_OR_PROMO_RE = re.compile(
    r"(\d{4}年|\d+月\d+[日号]?|\d+点|第[一二三四五六七八九十\d]+册|"
    r"开售|出版|预售|签名|特签|限时|抽奖|活动|详情|关注|上线|有声|广播剧|"
    r"微博|围脖|喜马拉雅|实体书|番外|作话|链接|群|私信)"
)

_STORY_SIGNAL_RE = re.compile(
    r"(主角|女主|男主|穿|重生|绑定|系统|学院|军校|机甲|星际|修真|宗门|"
    r"身份|能力|冲突|危机|秘密|选择|成长|对抗|破局|命运|感情|关系|"
    r"误报|捡垃圾|攒学费|工程师|单兵|训练|比赛|战斗|剧情|故事)"
)

_NOISE_BRACKET_RE = re.compile(r"[【\[]([^】\]]{4,160})[】\]]")


def clean_source_synopsis(text):
    """Split raw platform description into story facts and non-story notices.

    The goal is not to blacklist every possible noisy word. We classify sentence
    fragments by role: story-like fragments need narrative signals; notice-like
    fragments carry date/platform/promotion/action signals and are kept out of
    model grounding.
    """
    raw = str(text or "").strip()
    if not raw:
        return {"剧情简介": "", "非剧情信息": [], "原始简介": ""}

    fragments = _split_fragments(raw)
    story = []
    non_story = []

    for frag in fragments:
        normalized = _normalize_fragment(frag)
        if not normalized:
            continue
        if _is_non_story_notice(normalized):
            non_story.append(normalized)
            continue
        if _is_story_fragment(normalized):
            story.append(normalized)
            continue
        # Ambiguous fragments are safer as non-story. They can be inspected
        # later, but should not become plot facts.
        non_story.append(normalized)

    if not story:
        # Last-resort fallback: keep the original only when it has no obvious
        # notice signals; otherwise avoid feeding noisy text as plot.
        story_text = raw if not _EVENT_OR_PROMO_RE.search(raw) else ""
    else:
        story_text = "。".join(story)
        if story_text and not story_text.endswith("。"):
            story_text += "。"

    return {
        "剧情简介": story_text,
        "非剧情信息": non_story,
        "原始简介": raw,
    }


def apply_clean_synopsis(work):
    """Return a shallow copy with 简介 replaced by cleaned story synopsis."""
    out = dict(work or {})
    cleaned = clean_source_synopsis(out.get("简介", ""))
    out["原始简介"] = cleaned["原始简介"]
    out["剧情简介"] = cleaned["剧情简介"]
    out["非剧情信息"] = cleaned["非剧情信息"]
    if cleaned["剧情简介"]:
        out["简介"] = cleaned["剧情简介"]
    return out


def _split_fragments(text):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    bracket_parts = [m.group(1).strip() for m in _NOISE_BRACKET_RE.finditer(s)]
    s = _NOISE_BRACKET_RE.sub("。", s)
    parts = [p.strip() for p in re.split(r"[。；;！!？?\n\r]+", s) if p.strip()]
    return bracket_parts + parts


def _normalize_fragment(text):
    s = str(text or "").strip()
    s = re.sub(r"^[~～\-—\s]+|[~～\-—\s]+$", "", s)
    return s


def _is_non_story_notice(text):
    s = str(text or "")
    if _EVENT_OR_PROMO_RE.search(s):
        return True
    if re.search(r"\d{2,}", s) and not _STORY_SIGNAL_RE.search(s):
        return True
    return False


def _is_story_fragment(text):
    s = str(text or "")
    if _STORY_SIGNAL_RE.search(s):
        return True
    # Longer non-promotional prose is often a valid synopsis even without our
    # known genre words.
    return len(s) >= 24 and not _EVENT_OR_PROMO_RE.search(s)
