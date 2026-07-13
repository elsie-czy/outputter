import re


SKILL_NAME = "xhs-humanize-note"

FORBIDDEN_PATTERNS = [
    "这篇只按简介",
    "本篇只按",
    "不提前替它贷款",
    "资料边界",
    "简介快筛",
    "先说结论",
    "我会重点看",
    "重点看",
    "我的判断",
    "我的结论",
    "判断它合不合口味",
    "收藏时可以直接按",
    "欢迎评论",
]

SECTION_LABEL_PATTERNS = [
    r"^[\s>]*[🏚️🧱🔥📖📚🌶️💘✅📝💬📌🏷️]+\s*(标签|适合|不太适合|我的判断|我的结论|你来选)[:：]?\s*$",
    r"^[\s>]*(标签|适合|不太适合|我的判断|我的结论|你来选)[:：]?\s*$",
]

EMOTION_EMOJIS = ["🫠", "👀", "🔥", "⚠️", "📚"]


def _emoji_count(text):
    # Include the common warning sign outside the astral emoji ranges.
    return len(re.findall(r"[\U0001F300-\U0001FAFF⚠]", str(text or "")))


def _normalize_hashtags(lines, tags):
    clean_tags = []
    for tag in tags or []:
        tag = str(tag or "").strip().lstrip("#")
        if tag and tag not in clean_tags:
            clean_tags.append(tag)
    if not clean_tags:
        return lines
    hashtag_line = " ".join(f"#{tag}" for tag in clean_tags[:5])
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("🏷️ 标签", "标签", "🏷 标签"):
            continue
        if stripped and all(part.startswith("#") for part in stripped.split()):
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    out.extend(["", hashtag_line])
    return out


def _has_follow_reason(text):
    text = str(text or "")
    signals = ["关注我", "继续挖", "继续按", "少踩雷", "试毒", "筛书", "能不能追", "雷点在哪", "适合谁"]
    return sum(1 for s in signals if s in text) >= 2


def _has_next_preview(text):
    text = str(text or "")
    return any(s in text for s in ["下期预告", "下一篇", "下期我", "下篇"])


def _topic_from_work(work, text):
    combined = " ".join([
        str((work or {}).get("分类", "")),
        str((work or {}).get("简介", "")),
        str(text or ""),
    ])
    if "末世" in combined:
        return "末世文"
    if "穿书" in combined:
        return "穿书文"
    if "种田" in combined:
        return "种田文"
    if "修真" in combined or "仙侠" in combined:
        return "修真文"
    if "甜" in combined:
        return "甜文"
    return "网文"


def _is_hardcore_group_survival(work, text):
    combined = " ".join([
        str((work or {}).get("作品名称", "")),
        str((work or {}).get("分类", "")),
        str((work or {}).get("取向", "")),
        str((work or {}).get("简介", "")),
        str(text or ""),
    ])
    signals = ["无CP", "囚车", "囚犯", "死刑犯", "押运", "群像", "硬核丧尸", "行尸走肉"]
    return sum(1 for s in signals if s in combined) >= 2


def _next_preview_line(work, text):
    combined = " ".join([
        str((work or {}).get("分类", "")),
        str((work or {}).get("简介", "")),
        str(text or ""),
    ])
    if _is_hardcore_group_survival(work, text):
        return "🔔 下期我想继续挖这种硬核末世文，最好是活人比丧尸更吓人、群像也能立住的那种。"
    if "圣母" in combined or "穿书" in combined:
        return "🔔 下期我想挖一本女主更清醒的同类文，最好是末世里不圣母、能自己扛事的那种。"
    if "无限复活" in combined or "循环" in combined or "复活" in combined:
        return "🔔 下期我想继续找这种高压设定文，最好是越死越清醒、越看越想追的那种。"
    if "基建" in combined or "囤货" in combined:
        return "🔔 下期我想挖一本更有烟火气的基建文，最好是从破屋一路攒到基地那种。"
    return "🔔 下期我继续挖一本不同口味的书，重点看开局够不够抓人、雷点重不重。"


def _inject_conversion_lines(lines, work):
    text = "\n".join(lines)
    additions = []
    if not _has_follow_reason(text):
        topic = _topic_from_work(work, text)
        additions.append(f"📌 关注我，继续挖这种“能不能追、雷点在哪、适合谁”都说清楚的{topic}，书荒少踩雷。")
    if not _has_next_preview(text):
        additions.append(_next_preview_line(work, text))
    if not additions:
        return lines
    out = list(lines)
    while out and not out[-1].strip():
        out.pop()
    out.extend([""] + additions)
    return out


def diagnose_xhs_ai_traces(note):
    text = str(note or "")
    findings = []
    lines = text.splitlines()
    heading_emoji_lines = [
        line for line in lines
        if re.match(r"^\s*[🏚️🧱🔥📖📚🌶️💘✅📝💬📌🏷️]", line)
    ]
    if len(heading_emoji_lines) >= 4:
        findings.append({"issue": "emoji_as_section_numbers", "count": len(heading_emoji_lines)})
    if any(pattern in text for pattern in FORBIDDEN_PATTERNS):
        findings.append({"issue": "ai_review_phrases"})
    if re.search(r"^\s*[-*]\s*[^：:\n]{2,12}[：:]", text, flags=re.M):
        findings.append({"issue": "inline_header_list"})
    if "🏷️ 标签" in text or "\n标签\n" in text:
        findings.append({"issue": "ritual_tag_label"})
    if not any(token in text for token in ["我看", "我觉得", "我一开始", "我个人", "家人们", "救命"]):
        findings.append({"issue": "missing_first_person"})
    return findings


def apply_xhs_humanize_note_skill(note, work=None, analysis=None, tags=None):
    """Apply the xhs-humanize-note skill rules as a deterministic post-pass.

    The model still owns story facts. This pass keeps the public note from
    drifting back into product-spec structure: heading emoji, disclaimer lines,
    ritual tag labels and neutral CTA phrasing.
    """
    work = work or {}
    analysis = analysis if isinstance(analysis, dict) else {}
    tags = tags or []
    original = str(note or "")
    lines = original.splitlines()
    out = []
    removed = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        if any(re.match(pattern, stripped) for pattern in SECTION_LABEL_PATTERNS):
            removed.append(stripped)
            continue
        if any(pattern in stripped for pattern in FORBIDDEN_PATTERNS):
            removed.append(stripped)
            continue
        # Strip emoji that only acts as a heading marker, but keep the sentence.
        line = re.sub(r"^\s*[🏚🧱📖📚🌶💘✅📝💬📌🏷]\ufe0f?\s+", "", line)
        line = line.replace("你更吃", "你们更喜欢")
        out.append(line.rstrip())

    out = _inject_conversion_lines(out, work)
    out = _normalize_hashtags(out, tags)
    text = "\n".join(out).strip()

    # Keep emoji as emotion punctuation: enough to feel native, not enough to
    # become section numbering.
    count = _emoji_count(text)
    if count == 0 and "【标题】" in text:
        text = text.replace("\n\n", "\n\n家人们 这本我想单独拎出来聊聊。👀\n\n", 1)
        count = _emoji_count(text)
    if count < 3:
        text = text.replace("评论区", "评论区📚", 1) if "评论区" in text else text
        if "但" in text and "🔥" not in text:
            text = text.replace("但", "但", 1)
            text += "\n\n这个点如果写稳，会很上头。🔥"
    if _emoji_count(text) > 6:
        seen = 0
        cleaned_chars = []
        for ch in text:
            if re.match(r"[\U0001F300-\U0001FAFF⚠]", ch):
                seen += 1
                if seen > 5:
                    continue
            cleaned_chars.append(ch)
        text = "".join(cleaned_chars)

    analysis["xhs_humanize_note"] = {
        "skill": SKILL_NAME,
        "applied": True,
        "diagnosis": diagnose_xhs_ai_traces(original),
        "removed_lines": removed[:8],
        "checks": {
            "emoji_count": _emoji_count(text),
            "has_ritual_tag_label": "🏷️ 标签" in text,
            "has_disclaimer": any(pattern in text for pattern in ["这篇只按简介", "本篇只按", "资料边界"]),
        },
    }
    return text
