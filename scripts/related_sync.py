from scripts.feishu_config import FEISHU_CONFIG
from scripts.feishu_client import FeishuClient
from scripts.utils import append_jsonl
from scripts.config import PATHS
from scripts.validator import validate_required
import re


def _safe_append_error(payload):
    append_jsonl(PATHS["logs"] + "/sync_errors.jsonl", payload)


def _pick_name(text):
    s = str(text or "")
    candidates = re.findall(r"[\u4e00-\u9fa5]{2,4}", s)
    blacklist = {"女主", "男主", "配角", "反派", "师兄", "师姐", "小师妹", "掌门", "宗门", "系统", "修真", "角色"}
    for c in candidates:
        if c not in blacklist:
            return c
    return ""


def _clip(text, n=120):
    t = str(text or "").strip()
    return t[:n]


def _infer_goldfinger(desc):
    s = str(desc or "")
    tags = []
    mapping = [
        ("系统", "系统"),
        ("重生", "重生"),
        ("穿越", "记忆"),
        ("记忆", "记忆"),
        ("技能", "技能"),
        ("知识", "知识"),
        ("异能", "异能"),
        ("空间", "空间"),
        ("财富", "财富"),
    ]
    for kw, tag in mapping:
        if kw in s and tag not in tags:
            tags.append(tag)
    if not tags:
        return ["知识"]
    return tags[:3]


def _infer_conflict_type(text):
    s = str(text or "")
    if any(x in s for x in ["身份", "设定", "穿越"]):
        return "身份冲突"
    if any(x in s for x in ["价值", "认知", "观念", "理念"]):
        return "价值观冲突"
    if any(x in s for x in ["利益", "资源", "权力"]):
        return "利益冲突"
    if any(x in s for x in ["情感", "爱情", "恋爱"]):
        return "情感冲突"
    return "命运冲突"


def _infer_sentence_type(sentence):
    s = str(sentence or "")
    if any(x in s for x in ["你", "我", "他", "她"]):
        return "人物金句"
    if any(x in s for x in ["不是", "就是", "因此", "所以"]):
        return "哲理金句"
    return "情绪金句"


def _normalize_emotion_type(text):
    s = str(text or "")
    for t in ["爽感", "甜宠", "悬念", "共情", "焦虑", "愤怒", "悲伤", "恐惧"]:
        if t in s:
            return t
    return "共情"


def _infer_trope_type(text):
    s = str(text or "")
    if any(x in s for x in ["系统", "任务", "面板"]):
        return "系统开篇"
    if any(x in s for x in ["倒叙", "回忆"]):
        return "倒叙开篇"
    if any(x in s for x in ["对话", "开口", "一句话"]):
        return "对话开篇"
    if any(x in s for x in ["场景", "画面", "镜头"]):
        return "场景开篇"
    if any(x in s for x in ["冲突", "危机", "对抗"]):
        return "冲突"
    if any(x in s for x in ["身份", "马甲", "穿越"]):
        return "身份"
    return "悬念"


def _infer_applicable_types(work):
    c = str(work.get("分类", "") or "")
    types = []
    mapping = [
        ("穿越", "穿越"),
        ("重生", "重生"),
        ("玄幻", "玄幻"),
        ("仙侠", "仙侠"),
        ("悬疑", "悬疑"),
        ("都市", "都市"),
        ("现代", "现代言情"),
        ("古代", "古代言情"),
    ]
    for kw, name in mapping:
        if kw in c and name not in types:
            types.append(name)
    if not types:
        types = ["玄幻"]
    return types[:3]


def _safe_create(client, table_id, fields):
    fields = client.filter_fields(table_id, fields)
    meta = client.get_table_field_meta(table_id)
    # Drop invalid link payloads (only keep link fields when value is a list of record_ids).
    cleaned = {}
    for k, v in fields.items():
        ftype = (meta.get(k) or {}).get("type")
        if ftype in (18, 21):
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                cleaned[k] = v
            continue
        cleaned[k] = v
    fields = cleaned
    return client.create_record_in_table(table_id, fields)


def _norm_value(v):
    if isinstance(v, list):
        if v and isinstance(v[0], dict):
            return "|".join(str(x.get("text", "") or x.get("name", "") or x.get("record_ids", "")) for x in v)
        return "|".join(str(x) for x in v)
    if isinstance(v, dict):
        return str(sorted(v.items()))
    return str(v or "").strip()


def _find_existing_by_keys(client, table_id, key_fields):
    if not key_fields:
        return None
    # Prefer server-side filter for exact matches; fall back to scan.
    try:
        item = client.find_first_record_by_fields(table_id, key_fields)
        if item:
            return item
    except Exception:
        pass
    for r in client.iter_records(table_id, page_size=200):
        f = r.get("fields", {})
        if all(_norm_value(f.get(k)) == _norm_value(v) for k, v in key_fields.items()):
            return r
    return None


def _upsert_record(client, table_id, fields, unique_keys):
    key_fields = {k: fields.get(k, "") for k in unique_keys if k in fields and str(fields.get(k, "")).strip()}
    exist = _find_existing_by_keys(client, table_id, key_fields) if key_fields else None
    if exist:
        rid = exist.get("record_id")
        # Merge link-array fields to avoid losing historical links on update.
        merged = dict(fields)
        oldf = exist.get("fields", {})
        def _normalize_link_ids(value):
            out = []
            if isinstance(value, list):
                for it in value:
                    if isinstance(it, str):
                        out.append(it)
                    elif isinstance(it, dict):
                        rid = it.get("record_id") or it.get("id") or it.get("value")
                        if rid:
                            out.append(str(rid))
                    elif it is not None:
                        out.append(str(it))
            elif isinstance(value, dict):
                rid = value.get("record_id") or value.get("id") or value.get("value")
                if rid:
                    out.append(str(rid))
            elif value is not None:
                out.append(str(value))
            return out

        for k, v in fields.items():
            if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                ov_ids = _normalize_link_ids(oldf.get(k, []))
                merged[k] = list(dict.fromkeys(ov_ids + v))
        merged = client.filter_fields(table_id, merged)
        meta = client.get_table_field_meta(table_id)
        cleaned = {}
        for k, v in merged.items():
            ftype = (meta.get(k) or {}).get("type")
            if ftype in (18, 21):
                if isinstance(v, list) and all(isinstance(x, str) for x in v):
                    cleaned[k] = v
                continue
            cleaned[k] = v
        merged = cleaned
        client.update_record_in_table(table_id, rid, merged)
        return rid
    return _safe_create(client, table_id, fields)


def sync_related(main_record_id, work, analysis):
    client = FeishuClient()
    if not client.is_configured():
        return {}

    table_ids = FEISHU_CONFIG.get("related_table_ids", {})

    results = {
        "开篇套路库": [],
        "人物设定库": [],
        "冲突设计库": [],
        "情绪触发库": [],
        "金句库": [],
    }

    try:
        # 开篇套路库
        tropes = []
        seen_trope = set()
        for it in analysis.get("开篇套路", []):
            t = str(it or "").strip()
            if not t or t in seen_trope:
                continue
            seen_trope.add(t)
            tropes.append(t)
        for item in tropes:
            fields = {
                "套路名称": item,
                "套路类型": _infer_trope_type(item),
                "适用类型": _infer_applicable_types(work),
                "质量评分": "中",
                "使用效果": "好用",
                "核心原理": "先给冲突或悬念，再给信息差，最后抛出阅读动机",
                "操作步骤": "1) 20秒内给危机 2) 交代主角目标 3) 留一个未解问题",
                "示例原文": _clip(item, 160),
                "应用场景": "网文开篇3-5段快速抓读者注意力",
                "拆解记录表（主表）": [main_record_id],
            }
            available = client.get_table_fields(table_ids["开篇套路库"])
            fields = {k: v for k, v in fields.items() if k in available}
            missing = validate_required("开篇套路库", fields, available_fields=available)
            if missing:
                raise RuntimeError(f"开篇套路库缺必填字段: {missing}")
            rid = _upsert_record(client, table_ids["开篇套路库"], fields, ["套路名称"])
            results["开篇套路库"].append(rid)

        # 人物设定库
        role_map = {
            "女主": analysis.get("人物设定", {}).get("女主", ""),
            "男主": analysis.get("人物设定", {}).get("男主", ""),
            "亮点配角": analysis.get("人物设定", {}).get("亮点配角", ""),
        }
        role_type_map = {"女主": "女主", "男主": "男主", "亮点配角": "配角"}
        for role, desc in role_map.items():
            role_name = _pick_name(desc) or ("未明确姓名" if role != "亮点配角" else "关键配角")
            fields = {
                "套路名称": desc,
                "角色名称": role_name,
                "人物类型": role_type_map.get(role, role),
                "性格反差": "外在克制/冷静，内在高行动力与保护欲",
                "身份反差": "表层身份与真实能力形成反差，推动剧情反转",
                "金手指类型": _infer_goldfinger(desc),
                "成长弧光": "从被动应对到主动破局，再到带动群体改变",
                "示例原文": _clip(desc, 160),
                "应用场景": "网文人物立体化与角色反差塑造",
                "质量评分": "中",
                "使用效果": "好用",
                "拆解记录表（主表）": [main_record_id],
            }
            available = client.get_table_fields(table_ids["人物设定库"])
            meta = client.get_table_field_meta(table_ids["人物设定库"])
            if "来源书名" in available:
                ftype = (meta.get("来源书名") or {}).get("type")
                if ftype in (18, 21) and main_record_id:
                    fields["来源书名"] = [main_record_id]
                else:
                    fields["来源书名"] = work.get("作品名称", "")
            fields = {k: v for k, v in fields.items() if k in available}
            missing = validate_required("人物设定库", fields, available_fields=available)
            if missing:
                raise RuntimeError(f"人物设定库缺必填字段: {missing}")
            unique_keys = ["套路名称", "角色名称"]
            if "来源书名" in fields:
                unique_keys.append("来源书名")
            rid = _upsert_record(client, table_ids["人物设定库"], fields, unique_keys)
            results["人物设定库"].append(rid)

        # 冲突设计库
        conflict_map = {
            "第一层": analysis.get("冲突设计", {}).get("第一层", ""),
            "第二层": analysis.get("冲突设计", {}).get("第二层", ""),
            "第三层": analysis.get("冲突设计", {}).get("第三层", ""),
        }
        for level, content in conflict_map.items():
            fields = {
                "套路名称": f"{level}冲突：{_clip(content, 24)}",
                "冲突类型": _infer_conflict_type(content),
                "冲突层级": level,
                "冲突内容": content,
                "矛盾双方": "主角阵营 vs 阻力/反派阵营",
                "情绪触发点": "抉择压力、身份危机、关系撕裂",
                "升级逻辑": "局部冲突 -> 结构冲突 -> 终局对抗",
                "示例原文": _clip(content, 160),
                "应用场景": "章节中段推进与高潮前冲突升级",
                "来源书名": work.get("作品名称", ""),
                "质量评分": "中",
                "使用效果": "好用",
            }
            available = client.get_table_fields(table_ids["冲突设计库"])
            meta = client.get_table_field_meta(table_ids["冲突设计库"])
            if "来源书名" in available:
                ftype = (meta.get("来源书名") or {}).get("type")
                if ftype in (18, 21) and main_record_id:
                    fields["来源书名"] = [main_record_id]
            if "拆解记录表（主表）" in available and main_record_id:
                fields["拆解记录表（主表）"] = [main_record_id]
            fields = {k: v for k, v in fields.items() if k in available}
            missing = validate_required("冲突设计库", fields, available_fields=available)
            if missing:
                raise RuntimeError(f"冲突设计库缺必填字段: {missing}")
            unique_keys = ["冲突层级", "冲突内容"]
            if "来源书名" in fields:
                unique_keys.append("来源书名")
            if "拆解记录表（主表）" in fields:
                unique_keys.append("拆解记录表（主表）")
            rid = _upsert_record(client, table_ids["冲突设计库"], fields, unique_keys)
            results["冲突设计库"].append(rid)

        # 情绪触发库
        emotions = []
        seen_emotion = set()
        for it in analysis.get("情绪触发", []):
            e = str(it or "").strip()
            if not e:
                continue
            t = _normalize_emotion_type(e)
            if t in seen_emotion:
                continue
            seen_emotion.add(t)
            emotions.append(e)
        for item in emotions:
            fields = {
                "情绪类型": _normalize_emotion_type(item),
                "触发词": item,
                "触发场景": _clip(analysis.get("冲突设计", {}).get("第一层", ""), 80),
                "描写技巧": "动作细节+心理独白+场景反差",
                "示例原文": _clip(analysis.get("冲突设计", {}).get("第二层", ""), 120),
                "示例金句": _clip((analysis.get("金句", []) or [""])[0], 80),
                "应用场景": "情绪节点强化与读者共鸣触发",
                "来源书名": work.get("作品名称", ""),
                "质量评分": "中",
                "使用效果": "好用",
            }
            available = client.get_table_fields(table_ids["情绪触发库"])
            meta = client.get_table_field_meta(table_ids["情绪触发库"])
            if "来源书名" in available:
                ftype = (meta.get("来源书名") or {}).get("type")
                if ftype in (18, 21) and main_record_id:
                    fields["来源书名"] = [main_record_id]
            if "拆解记录表（主表）" in available and main_record_id:
                fields["拆解记录表（主表）"] = [main_record_id]
            fields = {k: v for k, v in fields.items() if k in available}
            missing = validate_required("情绪触发库", fields, available_fields=available)
            if missing:
                raise RuntimeError(f"情绪触发库缺必填字段: {missing}")
            unique_keys = ["情绪类型", "触发词", "触发场景"]
            if "来源书名" in fields:
                unique_keys.append("来源书名")
            if "拆解记录表（主表）" in fields:
                unique_keys.append("拆解记录表（主表）")
            rid = _upsert_record(client, table_ids["情绪触发库"], fields, unique_keys)
            results["情绪触发库"].append(rid)

        # 金句库
        sentences = []
        seen_sentence = set()
        for it in analysis.get("金句", []):
            s = str(it or "").strip()
            if not s or s in seen_sentence:
                continue
            seen_sentence.add(s)
            sentences.append(s)
        for item in sentences:
            fields = {
                "金句类型": _infer_sentence_type(item),
                "金句内容": item,
                "适用场景": "章节结尾升温、评论区二创引用",
                "写作技巧": "对比句式+节奏断点+关键词重复",
                "改造模板": "把[角色困境]替换进句式，保留价值判断钩子",
                "应用示例": f"示例：{_clip(item, 60)}",
                "示例原文": _clip(item, 120),
                "来源书名": work.get("作品名称", ""),
                "质量评分": "中",
                "使用效果": "好用",
                "拆解记录表（主表）": [main_record_id],
            }
            available = client.get_table_fields(table_ids["金句库"])
            fields = {k: v for k, v in fields.items() if k in available}
            missing = validate_required("金句库", fields, available_fields=available)
            if missing:
                raise RuntimeError(f"金句库缺必填字段: {missing}")
            rid = _upsert_record(client, table_ids["金句库"], fields, ["金句内容"])
            results["金句库"].append(rid)

    except Exception as e:
        _safe_append_error({"error": str(e), "main_record_id": main_record_id})

    return results


def update_main_links(main_record_id, related_ids):
    client = FeishuClient()
    if not client.is_configured():
        return False

    try:
        main_meta = client.get_table_field_meta(client.table_id)
        fields = {}
        if related_ids.get("开篇套路库") and (main_meta.get("开篇套路类型") or {}).get("type") == 21:
            fields["开篇套路类型"] = related_ids["开篇套路库"]
        # 人物设定库：女主/男主各取第一个
        if related_ids.get("人物设定库"):
            if len(related_ids["人物设定库"]) >= 1:
                if (main_meta.get("女主设定") or {}).get("type") == 21:
                    fields["女主设定"] = [related_ids["人物设定库"][0]]
            if len(related_ids["人物设定库"]) >= 2:
                if (main_meta.get("男主设定") or {}).get("type") == 21:
                    fields["男主设定"] = [related_ids["人物设定库"][1]]
        # 冲突设计库
        if related_ids.get("冲突设计库"):
            if len(related_ids["冲突设计库"]) >= 1 and (main_meta.get("第一层冲突") or {}).get("type") == 21:
                fields["第一层冲突"] = [related_ids["冲突设计库"][0]]
            if len(related_ids["冲突设计库"]) >= 2 and (main_meta.get("第二层冲突") or {}).get("type") == 21:
                fields["第二层冲突"] = [related_ids["冲突设计库"][1]]
            if len(related_ids["冲突设计库"]) >= 3 and (main_meta.get("第三层冲突") or {}).get("type") == 21:
                fields["第三层冲突"] = [related_ids["冲突设计库"][2]]
        if related_ids.get("情绪触发库") and (main_meta.get("情绪分析摘要") or {}).get("type") == 21:
            fields["情绪分析摘要"] = related_ids["情绪触发库"]
        if related_ids.get("金句库") and (main_meta.get("金句（Top5）") or {}).get("type") == 21:
            fields["金句（Top5）"] = related_ids["金句库"][:5]

        if fields:
            client.update_record(main_record_id, fields)
        return True
    except Exception as e:
        _safe_append_error({"error": str(e), "main_record_id": main_record_id})
        return False
