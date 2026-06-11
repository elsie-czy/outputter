import re

from scripts.feishu_config import get_feishu_config


def find_xhs_record_by_id(client, rid):
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
    if not table_id:
        return None, None
    rid = (rid or "").strip()
    if not rid:
        return table_id, None
    for it in client.iter_records(table_id, page_size=200):
        if (it.get("record_id") or "").strip() == rid:
            return table_id, it
    return table_id, None


def field_contains_main_record_id(value, main_record_id):
    mid = str(main_record_id or "").strip()
    if not mid:
        return False
    if isinstance(value, str):
        return value.strip() == mid
    if isinstance(value, list):
        for it in value:
            if isinstance(it, str) and it.strip() == mid:
                return True
            if isinstance(it, dict):
                ids = it.get("record_ids")
                if isinstance(ids, list) and mid in [str(x).strip() for x in ids]:
                    return True
                if str(it.get("record_id", "")).strip() == mid:
                    return True
    if isinstance(value, dict):
        ids = value.get("record_ids")
        if isinstance(ids, list) and mid in [str(x).strip() for x in ids]:
            return True
    return False


def find_main_record_by_id(client, main_record_id):
    mid = str(main_record_id or "").strip()
    if not mid:
        return None
    for it in client.iter_records(client.table_id, page_size=200):
        if str(it.get("record_id", "")).strip() == mid:
            return it
    return None


def collect_fact_pack(client, xhs_record):
    cfg = get_feishu_config()
    related = (cfg.get("related_table_ids") or {})
    f = (xhs_record or {}).get("fields", {}) or {}
    main_record_id = str(f.get("主表记录ID", "") or f.get("记录表ID", "")).strip()
    if not main_record_id:
        main_record_id = str(f.get("主表record_id", "")).strip()

    main_rec = find_main_record_by_id(client, main_record_id) if main_record_id else None
    main_fields = (main_rec or {}).get("fields", {}) or {}
    work_name = str(f.get("作品名称", "") or main_fields.get("作品名称", "")).strip()

    facts = {
        "work_name": work_name,
        "main_record_id": main_record_id,
        "main_fields": {
            "作品名称": str(main_fields.get("作品名称", "")).strip(),
            "作者": str(main_fields.get("作者", "")).strip(),
            "平台": str(main_fields.get("平台", "")).strip(),
            "分类": str(main_fields.get("分类", "")).strip(),
            "简介": str(main_fields.get("简介", "")).strip(),
            "核心冲突": str(main_fields.get("核心冲突", "")).strip(),
            "情绪钩子": str(main_fields.get("情绪钩子", "")).strip(),
            "女主设定": str(main_fields.get("女主设定", "")).strip(),
            "男主设定": str(main_fields.get("男主设定", "")).strip(),
            "金句（Top5）": str(main_fields.get("金句（Top5）", "") or main_fields.get("金句_Top5_", "")).strip(),
        },
        "开篇套路": [],
        "人物设定": [],
        "冲突设计": [],
        "情绪触发": [],
        "金句": [],
    }

    def scan_table(table_id):
        out = []
        if not table_id:
            return out
        for rec in client.iter_records(table_id, page_size=200):
            rf = rec.get("fields", {}) or {}
            linked = field_contains_main_record_id(rf.get("拆解记录表（主表）"), main_record_id)
            by_book = (str(rf.get("来源书名", "")).strip() == work_name) if work_name else False
            if linked or by_book:
                out.append(rf)
        return out

    facts["开篇套路"] = scan_table(related.get("开篇套路库"))
    facts["人物设定"] = scan_table(related.get("人物设定库"))
    facts["冲突设计"] = scan_table(related.get("冲突设计库"))
    facts["情绪触发"] = scan_table(related.get("情绪触发库"))
    facts["金句"] = scan_table(related.get("金句库"))

    missing = []
    if not main_record_id:
        missing.append("主表记录ID缺失")
    if not main_rec:
        missing.append("主表记录不存在")
    if len(facts["开篇套路"]) == 0:
        missing.append("开篇套路库缺失")
    if len(facts["人物设定"]) == 0:
        missing.append("人物设定库缺失")
    if len(facts["冲突设计"]) == 0:
        missing.append("冲突设计库缺失")
    if len(facts["情绪触发"]) == 0:
        missing.append("情绪触发库缺失")
    if len(facts["金句"]) == 0:
        missing.append("金句库缺失")
    facts["missing"] = missing
    return facts


def facts_to_text(facts):
    main = facts.get("main_fields", {}) or {}
    lines = []
    lines.append("【事实卡（仅可使用下列信息，不可新增剧情）】")
    lines.append(f"作品：{main.get('作品名称') or facts.get('work_name', '')}")
    if main.get("作者"):
        lines.append(f"作者：{main.get('作者')}")
    if main.get("平台"):
        lines.append(f"平台：{main.get('平台')}")
    if main.get("分类"):
        lines.append(f"分类：{main.get('分类')}")
    if main.get("简介"):
        lines.append("简介：" + main.get("简介"))
    if main.get("核心冲突"):
        lines.append("核心冲突：" + main.get("核心冲突"))
    if main.get("情绪钩子"):
        lines.append("情绪钩子：" + main.get("情绪钩子"))
    if main.get("女主设定"):
        lines.append("女主设定：" + main.get("女主设定"))
    if main.get("男主设定"):
        lines.append("男主设定：" + main.get("男主设定"))
    if main.get("金句（Top5）"):
        lines.append("金句Top5：" + main.get("金句（Top5）"))

    if facts.get("开篇套路"):
        lines.append("开篇套路库：")
        for r in facts["开篇套路"][:6]:
            t = str(r.get("套路名称", "")).strip()
            if t:
                lines.append("- " + t)
    if facts.get("人物设定"):
        lines.append("人物设定库：")
        for r in facts["人物设定"][:6]:
            role = str(r.get("人物类型", "")).strip()
            name = str(r.get("角色名称", "")).strip()
            desc = str(r.get("套路名称", "")).strip()
            lines.append(f"- {role}/{name}: {desc}")
    if facts.get("冲突设计"):
        lines.append("冲突设计库：")
        for r in facts["冲突设计"][:6]:
            lvl = str(r.get("冲突层级", "")).strip()
            c = str(r.get("冲突内容", "")).strip()
            if c:
                lines.append(f"- {lvl}: {c}")
    if facts.get("情绪触发"):
        lines.append("情绪触发库：")
        for r in facts["情绪触发"][:6]:
            t = str(r.get("触发词", "")).strip() or str(r.get("情绪类型", "")).strip()
            if t:
                lines.append("- " + t)
    if facts.get("金句"):
        lines.append("金句库：")
        for r in facts["金句"][:8]:
            t = str(r.get("金句内容", "")).strip()
            if t:
                lines.append("- " + t)
    return "\n".join(lines)


def apply_fact_overrides(analysis, facts):
    out = dict(analysis or {})
    main = facts.get("main_fields", {}) or {}
    out["开篇套路"] = [
        str(x.get("套路名称", "")).strip()
        for x in facts.get("开篇套路", [])
        if str(x.get("套路名称", "")).strip()
    ][:3] or out.get("开篇套路", [])

    roles = {}
    for r in facts.get("人物设定", []):
        rt = str(r.get("人物类型", "")).strip()
        desc = str(r.get("套路名称", "")).strip()
        if not desc:
            continue
        if rt == "女主" and "女主" not in roles:
            roles["女主"] = desc
        elif rt == "男主" and "男主" not in roles:
            roles["男主"] = desc
        elif rt in ["配角", "亮点配角"] and "亮点配角" not in roles:
            roles["亮点配角"] = desc
    person = out.get("人物设定", {}) or {}
    person["女主"] = roles.get("女主") or main.get("女主设定") or person.get("女主", "")
    person["男主"] = roles.get("男主") or main.get("男主设定") or person.get("男主", "")
    person["亮点配角"] = roles.get("亮点配角") or person.get("亮点配角", "")
    out["人物设定"] = person

    conf = out.get("冲突设计", {}) or {}
    crows = facts.get("冲突设计", [])
    if crows:
        for r in crows:
            lvl = str(r.get("冲突层级", "")).strip()
            txt = str(r.get("冲突内容", "")).strip()
            if lvl in ["第一层", "第二层", "第三层"] and txt:
                conf[lvl] = txt
    if main.get("核心冲突") and not any(str(conf.get(k, "")).strip() for k in ["第一层", "第二层", "第三层"]):
        conf["第一层"] = main.get("核心冲突")
    out["冲突设计"] = conf

    emos = [
        str(r.get("触发词", "")).strip() or str(r.get("情绪类型", "")).strip()
        for r in facts.get("情绪触发", [])
    ]
    emos = [x for x in emos if x][:4]
    if not emos and main.get("情绪钩子"):
        emos = [x.strip() for x in re.split(r"[/、，,;；\\s]+", main.get("情绪钩子")) if x.strip()][:4]
    if emos:
        out["情绪触发"] = emos

    quotes = [
        str(r.get("金句内容", "")).strip()
        for r in facts.get("金句", [])
        if str(r.get("金句内容", "")).strip()
    ]
    if not quotes and main.get("金句（Top5）"):
        quotes = [x.strip() for x in re.split(r"[\n/、，,;；]+", main.get("金句（Top5）")) if x.strip()]
    if quotes:
        out["金句"] = quotes[:5]
    return out
