import re


OFFICIAL_SOURCE_MODES = {"jjwxc_exact", "jjwxc_title", "jjwxc_fuzzy", "fanqie_exact", "fanqie_title", "fanqie_fuzzy"}

SOURCE_GRADES = {
    "official_intro": 5,
    "trial_or_chapter": 5,
    "reader_review": 4,
    "reader_discussion": 4,
    "wiki_or_booklist": 2,
}


def _clean(text, max_len=120):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    text = text.strip(" -:：，,。")
    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip() + "..."
    return text


def _sentences(text, limit=8):
    parts = re.split(r"[。！？!?；;\n]+", str(text or ""))
    out = []
    for part in parts:
        s = _clean(part, max_len=140)
        if len(s) < 8:
            continue
        if s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def _items(value, limit=8):
    if isinstance(value, list):
        raw = value
    elif value:
        raw = _sentences(value, limit=limit)
    else:
        raw = []
    out = []
    for item in raw:
        text = _clean(item, max_len=120)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _source_url(search_info):
    return str((search_info or {}).get("搜索来源链接") or "").strip()


def _fact(text, source_type, source_label, status, usage_rule, source_url="", evidence_count=1):
    grade = SOURCE_GRADES.get(source_type, 1)
    return {
        "text": _clean(text, max_len=120),
        "source_type": source_type,
        "source_label": source_label,
        "source_grade": grade,
        "source_url": source_url,
        "evidence_count": evidence_count,
        "status": status,
        "usage_rule": usage_rule,
    }


def build_material_fact_check(work, search_info=None):
    """Build a compact fact ledger for generation.

    The goal is not to feed a full book to the LLM. It is to provide a small,
    source-labeled set of facts that downstream prompts and deterministic note
    builders are allowed to use.
    """
    work = work or {}
    search_info = search_info or {}
    source_mode = str(search_info.get("搜索模式") or work.get("简介来源") or "").strip()
    source_url = _source_url(search_info)
    intro = str(
        work.get("剧情简介")
        or work.get("简介")
        or search_info.get("剧情简介")
        or search_info.get("简介")
        or ""
    ).strip()

    usable = []
    cautious = []
    blocked = [
        "不可使用仅来自 LLM 记忆、题材联想或参考笔记模板的情节/人物/设定。",
        "未实际阅读全文时，不可写“我看完/熬夜看到/看到第几章”等伪阅读体验。",
        "单一读者评价不可当作共识；必须写成“有读者说/据评论反馈”。",
        "不可写超出公开简介、目录、试读或可验证评论范围的后期情节。",
    ]

    source_confidence = str(work.get("素材置信度") or work.get("source_confidence") or "").strip().lower()
    trusted_task_synopsis = source_confidence in ("synopsis", "official", "platform", "verified")
    official_label = "官方/平台简介" if source_mode in OFFICIAL_SOURCE_MODES or source_url else "任务原始简介"
    for sent in _sentences(intro, limit=6):
        status = "可写" if source_url or source_mode in OFFICIAL_SOURCE_MODES or trusted_task_synopsis else "谨慎写"
        target = usable if status == "可写" else cautious
        target.append(_fact(
            sent,
            "official_intro",
            official_label,
            status,
            "可直接用于剧情设定和开篇冲突" if status == "可写" else "只能作为简介信息使用，不扩写细节",
            source_url=source_url,
        ))

    for key in ["目录", "章节摘要", "试读内容", "正文片段"]:
        for item in _items(work.get(key) or search_info.get(key), limit=8):
            usable.append(_fact(
                item,
                "trial_or_chapter",
                key,
                "可写",
                "可用于开篇节点、阶段目标、人物处境；不扩展到未提供章节",
                source_url=source_url,
            ))

    for key in ["书评摘录", "热评", "读者评论", "高赞评论", "网络搜索摘要"]:
        for item in _items(work.get(key) or search_info.get(key), limit=8):
            cautious.append(_fact(
                item,
                "reader_discussion" if key == "网络搜索摘要" else "reader_review",
                key,
                "谨慎写",
                "只能写成搜索到的资料/读者反馈；不可冒充博主亲身阅读结论",
                source_url=source_url,
            ))

    seen = set()
    usable_unique = []
    for item in usable:
        text = item.get("text", "")
        if text and text not in seen:
            seen.add(text)
            usable_unique.append(item)
    cautious_unique = []
    for item in cautious:
        text = item.get("text", "")
        if text and text not in seen:
            seen.add(text)
            cautious_unique.append(item)

    if len(usable_unique) >= 3 and any(f.get("source_type") == "trial_or_chapter" for f in usable_unique):
        generation_mode = "grounded_note"
        read_scope = "public_trial_or_rich_material"
    elif usable_unique:
        generation_mode = "synopsis_grounded"
        read_scope = "official_or_task_synopsis"
    else:
        generation_mode = "insufficient"
        read_scope = "unknown"

    return {
        "generation_mode": generation_mode,
        "read_scope": read_scope,
        "source_mode": source_mode or "off",
        "source_url": source_url,
        "usable_facts": usable_unique[:10],
        "cautious_facts": cautious_unique[:8],
        "blocked_rules": blocked,
        "checklist": [
            "书名、作者、状态只能来自任务字段或官方/平台信息。",
            "每个具体情节必须能在 usable_facts 中找到对应来源。",
            "读者评价必须来自 cautious_facts，并标注为读者反馈。",
            "如果 read_scope 不是 full_read，不可写成全文读后感。",
        ],
    }


def public_fact_texts(fact_check, include_cautious=False, limit=6):
    fact_check = fact_check or {}
    facts = list(fact_check.get("usable_facts") or [])
    if include_cautious:
        facts.extend(fact_check.get("cautious_facts") or [])
    out = []
    for fact in facts:
        text = _clean(fact.get("text", ""), max_len=80)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out
