"""
数据格式归一化模块
全项目唯一入口：所有 feishu 字段 → 统一 JSON 格式的转换都在这里。
"""


def normalize_feishu_value(val) -> str:
    """
    飞书字段值 → 字符串。
    处理 list/dict/text 等复杂类型，统一返回可读字符串。
    """
    if val is None:
        return ""
    if isinstance(val, list):
        if len(val) == 0:
            return ""
        item = val[0]
        if isinstance(item, dict):
            return str(item.get("text", item.get("text_arr", [""])))
        return str(item)
    return str(val)


def _text(val) -> str:
    """将飞书字段值转为拼接字符串（用于人物设定等）"""
    if isinstance(val, list):
        texts = []
        for v in val:
            if isinstance(v, dict):
                texts.append(str(v.get("text", v.get("text_arr", [""]))))
            else:
                texts.append(str(v))
        return "，".join(texts) if texts else ""
    return str(val or "")


def _text_list(val, sep=None) -> list:
    """将飞书字段值转为字符串列表"""
    if isinstance(val, list):
        return [str(v.get("text", v)) if isinstance(v, dict) else str(v) for v in val]
    s = str(val or "")
    parts = [p.strip() for p in s.split(sep) if p.strip()] if sep else [s]
    return parts if parts and parts[0] else []


def normalize_feishu_record(fields: dict, source: str = "main") -> dict:
    """
    将飞书记录字段转为统一 analysis JSON 格式

    source: "main" → 飞书主表字段
            "xhs"  → 小红书笔记库字段

    返回格式:
    {
        "openings": ["套路1", "套路2", ...],
        "characters": ["女主：描述", "男主：描述", "亮点配角：描述"],
        "conflicts": ["第一层：描述", "第二层：描述", "第三层：描述"],
        "emotions": ["情绪1", "情绪2", ...],
        "quotes": ["金句1", "金句2", ...],
        "note": {"title": "...", "body": "...", "cta": "...", "tags": "..."},
    }
    """
    if source == "xhs":
        return _normalize_xhs_record(fields)
    return _normalize_main_record(fields)


def _normalize_main_record(fields: dict) -> dict:
    """飞书主表字段 → 统一格式"""
    # 人物设定：dict → list[str]
    characters_raw = fields.get("人物设定", {})
    characters = []
    if isinstance(characters_raw, dict):
        for role, desc in characters_raw.items():
            characters.append(f"{role}：{desc}")
    elif isinstance(characters_raw, list):
        characters = [str(c) for c in characters_raw]

    # 如果没有 人物设定 字段，从单独字段构建
    if not characters:
        heroine = _text(fields.get("女主设定", ""))
        hero = _text(fields.get("男主设定", ""))
        supporting = _text(fields.get("人物反差", ""))
        if heroine:
            characters.append(f"女主：{heroine}")
        if hero:
            characters.append(f"男主：{hero}")
        if supporting:
            characters.append(f"亮点配角：{supporting}")

    # 冲突设计：dict → list[str]
    conflicts_raw = fields.get("冲突设计", {})
    conflicts = []
    if isinstance(conflicts_raw, dict):
        for level, desc in conflicts_raw.items():
            conflicts.append(f"{level}：{desc}")
    elif isinstance(conflicts_raw, list):
        conflicts = [str(c) for c in conflicts_raw]

    # 如果没有 冲突设计 字段，从单独字段构建
    if not conflicts:
        for i, key in enumerate(["第一层冲突", "第二层冲突", "第三层冲突"], 1):
            val = _text(fields.get(key, ""))
            if val:
                conflicts.append(f"第{i}层：{val}")

    return {
        "openings": _text_list(fields.get("开篇套路类型", ""), sep=","),
        "characters": characters,
        "conflicts": conflicts,
        "emotions": _text_list(fields.get("情绪分析摘要", ""), sep=","),
        "quotes": _text_list(fields.get("金句（Top5）", "") or fields.get("金句_Top5_", ""), sep="\n"),
        "note": {
            "title": str(fields.get("小红书标题模板", "")),
            "body": str(fields.get("正文开头模板", "")),
            "cta": str(fields.get("互动话术模板", "")),
            "tags": _text_list(fields.get("热门标签推荐", "")),
        },
    }


def _normalize_xhs_record(fields: dict) -> dict:
    """小红书笔记库字段 → 统一格式"""
    return {
        "openings": [],
        "characters": [],
        "conflicts": [],
        "emotions": [],
        "quotes": [],
        "note": {
            "title": normalize_feishu_value(fields.get("小红书标题模板", "")),
            "body": normalize_feishu_value(fields.get("正文开头模板", "")),
            "cta": normalize_feishu_value(fields.get("互动话术模板", "")),
            "tags": _text_list(fields.get("热门标签推荐", "")),
        },
    }


def normalize_for_frontend(normalized: dict) -> dict:
    """
    统一格式 → 前端格式（驼峰英文字段名）
    {
        "openings": [...],
        "characters": [...],
        "conflicts": [...],
        "emotions": [...],
        "quotes": [...],
        "note": {...}
    }
    """
    return {
        "openings": normalized.get("openings", []),
        "characters": normalized.get("characters", []),
        "conflicts": normalized.get("conflicts", []),
        "emotions": normalized.get("emotions", []),
        "quotes": normalized.get("quotes", []),
        "note": normalized.get("note", {}),
    }
