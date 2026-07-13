import re


BAD_COMMENT_PATTERNS = [
    "欢迎评论",
    "评论区聊聊",
    "你怎么看",
    "大家怎么看",
    "喜欢就点赞",
    "欢迎留言",
]

GOOD_COMMENT_PATTERNS = [
    "书名",
    "求投喂",
    "求同款",
    "你更吃哪种",
    "你们更喜欢",
    "最怕什么雷",
    "丢我",
    "我去试毒",
    "蹲几本",
]

DEFAULT_FOLLOW_REASON = "我继续按“能不能追、雷点在哪、适合谁”来拆，书荒的时候少踩点雷。"
DEFAULT_FIRST_COMMENT = "我先蹲：有没有女主不圣母、靠本事活下来的同款？书名丢我。"
DEFAULT_REPLY_PROMPTS = [
    "这本偏囤货还是偏打怪？我想排进下一批。",
    "收到，我去看看适不适合做下一篇。",
    "这个听起来像我会吃的，女主是清醒挂吗？",
    "好，我先记下，后面做一版同类整理。",
]

GROUP_SURVIVAL_FIRST_COMMENT = "我先蹲：有没有这种硬核丧尸、生存压迫感强、不是无脑开挂的文？书名丢我。"
GROUP_SURVIVAL_REPLY_PROMPTS = [
    "这本更偏丧尸压迫，还是更偏活人互坑？我想排进下一批。",
    "收到，我去看看群像稳不稳、会不会只剩血浆刺激。",
    "这个听起来有点对味，开局有没有特别抓人的场景？",
    "好，我先记下，后面做一版硬核末世/丧尸文整理。",
]


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sentences(text):
    parts = re.split(r"[\n。！？!?]+", str(text or ""))
    return [_clean(p) for p in parts if _clean(p)]


def _extract_tags(text):
    return re.findall(r"#([\w\u4e00-\u9fff]+)", str(text or ""))


def _guess_genre_tags(note_text, account_strategy=None):
    text = str(note_text or "")
    tags = _extract_tags(text)
    for key in ["末世", "穿书", "女强", "种田", "修真", "循环", "无限复活"]:
        if key in text and key not in tags:
            tags.append(key)
    return tags[:6]


def _context_text(work=None, note_text="", account_strategy=None):
    pieces = [str(note_text or "")]
    if isinstance(work, dict):
        for key in ["作品名称", "work_name", "分类", "category", "取向", "orientation", "简介", "synopsis"]:
            pieces.append(str(work.get(key, "") or ""))
    if isinstance(account_strategy, dict):
        pieces.append(str(account_strategy.get("positioning", "") or ""))
    return " ".join(pieces)


def _is_group_survival_context(text):
    text = str(text or "")
    signals = ["无CP", "无cp", "囚车", "囚犯", "死刑犯", "押运", "群像", "硬核丧尸", "行尸走肉"]
    return sum(1 for s in signals if s in text) >= 2


def default_comment_hook(note_type=None, genre_tags=None, context_text=""):
    genre_tags = genre_tags or []
    tag_text = " ".join(genre_tags) + " " + str(context_text or "")
    if note_type == "warning_review":
        if _is_group_survival_context(tag_text):
            return "这类硬核末世文你们最怕什么雷？我先投“活人突然背刺”一票。"
        return "这类文你们最怕什么雷？我先投“女主圣母救全世界”一票。"
    if note_type == "comment_experiment":
        return "我现在真的书荒，求投喂一本能接上的，书名丢我。"
    if note_type == "booklist":
        return "这几本里你最想先看哪本？我下一篇先拆呼声最高的。"
    if _is_group_survival_context(tag_text):
        return "末世文里你们更怕丧尸，还是更怕身边的活人？我先投活人一票。"
    if "末世" in tag_text:
        return "还有没有女主清醒、靠本事活下来的末世文？书名丢我，我去试毒。"
    if "穿书" in tag_text:
        return "还有没有这种不憋屈的穿书文？书名丢我，我去试毒。"
    return "还有没有这种女主清醒、靠本事活下来的文？书名丢我，我去试毒。"


def _find_comment_hook(note_text):
    candidates = []
    for s in _sentences(note_text):
        if "?" in s or "？" in s or any(p in s for p in GOOD_COMMENT_PATTERNS + ["评论区"]):
            candidates.append(s)
    return candidates[-1] if candidates else ""


def _hook_type(text):
    if not text:
        return "无"
    if "书名" in text or "丢我" in text:
        return "报书名"
    if "求同款" in text or "同款" in text:
        return "求同款"
    if "雷" in text:
        return "雷点投票"
    if "还是" in text or "更喜欢" in text or "更吃" in text:
        return "二选一"
    if "求投喂" in text:
        return "求投喂"
    return "无"


def _score_comment_hook(hook):
    hook = _clean(hook)
    score = 0
    reasons = []
    if hook:
        score += 4
    if len(hook) <= 45:
        score += 4
    else:
        reasons.append("评论钩子偏长，3秒内不容易回复")
    if any(p in hook for p in GOOD_COMMENT_PATTERNS):
        score += 7
    else:
        reasons.append("缺少报书名/求同款/说雷点/求投喂等低门槛动作")
    if not any(p in hook for p in BAD_COMMENT_PATTERNS):
        score += 5
    else:
        reasons.append("出现“欢迎评论/你怎么看”等低质量互动表达")
    return min(score, 20), reasons


def _has_follow_reason(note_text):
    text = str(note_text or "")
    signals = ["继续", "下一篇", "少踩雷", "试毒", "筛书", "能不能追", "雷点", "适合谁", "书荒"]
    return sum(1 for s in signals if s in text) >= 3


def _build_suggestions(comment_score, follow_score, first_comment_score, reply_score, fallback_hook, follow_reason=None, first_comment=None):
    follow_reason = follow_reason or DEFAULT_FOLLOW_REASON
    first_comment = first_comment or DEFAULT_FIRST_COMMENT
    suggestions = []
    if comment_score < 15:
        suggestions.append({
            "dimension": "评论钩子",
            "problem": "评论入口不够低门槛，读者看完不知道该回什么。",
            "action": f"替换为：{fallback_hook}",
            "reason": "优先引导报书名/求同款/说雷点，比“你怎么看”更容易转评论。",
        })
    if follow_score < 15:
        suggestions.append({
            "dimension": "关注理由",
            "problem": "单篇有用，但账号持续价值没有说清楚。",
            "action": f"补一句：{follow_reason}",
            "reason": "涨粉需要让读者知道关注后还能持续获得筛书、试毒和避雷价值。",
        })
    if first_comment_score < 11:
        suggestions.append({
            "dimension": "首评",
            "problem": "缺少发布后可直接自评的评论引导。",
            "action": f"发布后第一条评论用：{first_comment}",
            "reason": "首评要比正文更口语，继续把读者往报书名/求同款方向带。",
        })
    if reply_score < 11:
        suggestions.append({
            "dimension": "回复话术",
            "problem": "缺少可复用回复，评论区不容易接成二轮对话。",
            "action": "准备2-4条追问式回复，用来判断题材、雷点和是否进下一批。",
            "reason": "前2小时互动要把单条评论接成连续对话。",
        })
    return suggestions


def review_note_conversion(note_text, note_type=None, account_strategy=None, work=None):
    note_text = str(note_text or "")
    genre_tags = _guess_genre_tags(note_text, account_strategy)
    context_text = _context_text(work=work, note_text=note_text, account_strategy=account_strategy)
    group_survival = _is_group_survival_context(context_text)
    fallback_hook = default_comment_hook(note_type, genre_tags, context_text=context_text)
    detected_hook = _find_comment_hook(note_text)
    comment_hook = detected_hook if detected_hook else fallback_hook
    comment_score, comment_reasons = _score_comment_hook(comment_hook)
    if comment_reasons or comment_score < 15:
        comment_hook = fallback_hook
        comment_score, _ = _score_comment_hook(comment_hook)

    follow_reason = (
        "我继续挖这种硬核末世、生存压迫感强、不是无脑开挂的文，书荒时少踩点空壳设定。"
        if group_survival else DEFAULT_FOLLOW_REASON
    )
    follow_score = 18 if _has_follow_reason(note_text) else 10
    if any(bad in note_text for bad in ["喜欢就关注", "点个关注", "关注我"]):
        follow_score = min(follow_score, 8)

    first_comment = GROUP_SURVIVAL_FIRST_COMMENT if group_survival else DEFAULT_FIRST_COMMENT
    first_comment_score = 14 if any(p in first_comment for p in ["书名", "同款", "丢我"]) else 8
    reply_prompts = GROUP_SURVIVAL_REPLY_PROMPTS[:] if group_survival else DEFAULT_REPLY_PROMPTS[:]
    reply_score = 14 if len(reply_prompts) >= 3 else 8

    total = comment_score + follow_score + first_comment_score + reply_score
    if total >= 58:
        grade = "good"
    elif total >= 44:
        grade = "review"
    else:
        grade = "retry"

    return {
        "comment_score": comment_score,
        "follow_score": follow_score,
        "first_comment_score": first_comment_score,
        "reply_score": reply_score,
        "total": total,
        "grade": grade,
        "comment_hook": comment_hook,
        "comment_hook_type": _hook_type(comment_hook),
        "follow_reason": follow_reason,
        "first_comment": first_comment,
        "reply_prompts": reply_prompts,
        "suggestions": _build_suggestions(
            comment_score,
            follow_score,
            first_comment_score,
            reply_score,
            fallback_hook,
            follow_reason,
            first_comment,
        ),
        "has_follow_reason": follow_score >= 15,
        "has_first_comment": bool(first_comment),
    }
