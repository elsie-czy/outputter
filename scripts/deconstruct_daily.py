import json
import os
import sys
import re
import time
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.config import PATHS, ensure_dirs, get_run_date
from scripts.select_work_from_topic_library import select_work
from scripts.search import search_work_info
from scripts.model_adapter import analyze_work
from scripts.feishu_client import FeishuClient
from scripts.feishu_reader import select_work_from_topic_library, mark_work_deconstructed
from scripts.utils import append_jsonl, now_ts
from scripts.related_sync import sync_related, update_main_links
from scripts.validator import validate_required
from scripts.dedupe import find_by_title_author
from scripts.image_generator import generate_images_from_prompt, is_image_generation_enabled
from scripts.source_cleaner import clean_source_synopsis
from scripts.account_strategy import get_account_strategy
from scripts.xhs_note_humanizer import apply_xhs_humanize_note_skill
from scripts.material_evidence import public_fact_texts


def _extract_name_hint(text):
    if not text:
        return ""
    m = re.search(r"([\u4e00-\u9fa5]{2,4})", str(text))
    return m.group(1) if m else ""


def _brief(text, max_len=22):
    if not text:
        return ""
    t = re.sub(r"\s+", "", str(text))
    t = re.sub(r"[“”\"'（）()]", "", t)
    return t[:max_len]


def _clip(text, n=120):
    return str(text or "").strip()[:n]


def _extract_lead_name_from_intro(intro):
    s = str(intro or "")
    # Common pattern: “XXX因/在/被...”
    m = re.search(r"([\u4e00-\u9fa5]{2,4})因", s)
    if m:
        name = m.group(1)
        for prefix in ["情感博主", "博主", "女主", "主角"]:
            if name.startswith(prefix):
                name = name.replace(prefix, "")
        if len(name) > 3:
            name = name[-2:]
        return name
    m = re.search(r"([\u4e00-\u9fa5]{2,4})[在被从向入]", s)
    if m:
        name = m.group(1)
        if len(name) > 3:
            name = name[-2:]
        return name
    return ""


def _compact_mobile(text, max_len=56):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s[:max_len]


_PUBLISH_TRACE_PATTERNS = [
    "基于题材推测",
    "基于简介推测",
    "基于题材判断",
    "基于简介判断",
    "基于题材特征",
    "题材推测",
    "简介无线索",
    "若简介无线索",
    "推测：",
    "推测，",
    "推测",
]

_PUBLISH_BANNED_TERMS = [
    "晋江",
    "起点",
    "番茄",
    "耽美文学城",
    "喜马拉雅",
    "微博",
    "围脖",
]


def _publish_clean(text, max_len=120, fallback=""):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return _compact_mobile(fallback, max_len)
    for pattern in _PUBLISH_TRACE_PATTERNS:
        s = s.replace(pattern, "")
    s = re.sub(r"^[，。、：:；;\s]+", "", s)
    s = re.sub(r"([，,；;：:])\s*(可能|可为|包括)", r"\1\2", s)
    s = re.sub(r"\b可能\b", "", s)
    s = re.sub(r"可能为", "偏向", s)
    s = re.sub(r"可能是", "偏向", s)
    s = re.sub(r"可能包括", "看点包括", s)
    s = re.sub(r"可为", "偏向", s)
    s = re.sub(r"，，+", "，", s)
    s = re.sub(r"[，,、]+[。.!！?？]", "。", s)
    s = re.sub(r"[。.!！?？]+[，,、；;]+", "。", s)
    s = re.sub(r"：，", "：", s)
    s = s.strip(" ，,。；;：:")
    return _compact_mobile(s or fallback, max_len)


def _publish_phrase(text, max_len=80, fallback=""):
    s = _publish_clean(text, max_len=max_len, fallback=fallback)
    s = re.sub(r"[。！？!?；;、，,\s]+$", "", s)
    return s


def _note_variant_seed(work):
    raw = f"{work.get('作品名称','')}|{work.get('作者','')}"
    return sum(ord(ch) for ch in raw) % 3


def _clean_publish_note(text):
    s = str(text or "")
    for term in _PUBLISH_BANNED_TERMS:
        s = s.replace(term, "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[，,、]+([。！？!?])", r"\1", s)
    s = re.sub(r"([。！？!?])+[，,、；;]+", r"\1", s)
    s = re.sub(r"如果你最近想找一本([^。！？!?]{1,80})[。！？!?]的文", r"如果你最近想找一本\1的文", s)
    return s.strip()


def _safe_publish_tags(tags):
    out = []
    for tag in tags or []:
        text = str(tag or "").strip().lstrip("#")
        if not text:
            continue
        if any(term in text for term in _PUBLISH_BANNED_TERMS):
            continue
        if text not in out:
            out.append(text)
    return out[:5]


def _strip_emotion_label(text):
    s = _publish_phrase(text, max_len=36)
    s = re.sub(r"^[^：:]{1,8}[：:]", "", s).strip()
    return _publish_phrase(s, max_len=28)


def _is_publish_unsafe_fact(text):
    """Return True for analysis-only or weakly grounded facts."""
    s = str(text or "").strip()
    if not s:
        return True
    unsafe_terms = [
        "可能",
        "推测",
        "无明确",
        "无线索",
        "未明确",
        "无具体",
        "可为",
        "泛化",
        "题材特征",
        "判断这本",
        "是否值得",
        "读者收益",
        "感情线是否",
        "爽点是否",
        "避免踩雷",
    ]
    return any(term in s for term in unsafe_terms)


def _publish_fact_list(items, limit=3, max_len=52):
    out = []
    for item in items or []:
        text = _publish_phrase(item, max_len=max_len)
        if not text or _is_publish_unsafe_fact(text):
            continue
        if text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _evidence_points_for_note(work, analysis):
    """Use only synopsis-backed evidence for public notes."""
    intro = str(work.get("简介", "") or "")
    grounded = []
    fact_check = work.get("素材证据卡") or (work.get("素材厚度", {}) or {}).get("fact_check")
    fact_texts = public_fact_texts(fact_check, limit=4)
    if fact_texts:
        return fact_texts[:4]
    if fact_check and fact_check.get("generation_mode") == "insufficient":
        return []
    rich_evidence = []
    for key in ["正文片段", "试读内容", "章节摘要", "目录", "书评摘录", "读者评论", "热评", "高赞评论"]:
        value = work.get(key)
        if isinstance(value, list):
            for item in value[:6]:
                text = _publish_phrase(item, max_len=58)
                if text and not _is_publish_unsafe_fact(text):
                    rich_evidence.append(text)
        elif value:
            rich_evidence.extend(_mobile_lines(str(value), max_len=58, max_lines=3))
    if all(key in intro for key in ["明鹰", "吃货", "城主"]):
        grounded.append("明鹰想当吃货，却被推成了城主，这个反差挺抓人")
    if any(key in intro for key in ["清理废墟", "规划城区", "修复设施", "建立卫队", "恢复生产"]):
        grounded.append("清废墟、修设施、建卫队，基建线不是空喊口号")
    if "丧尸" in intro and "变异兽" in intro:
        grounded.append("丧尸和变异兽把末世压力先压出来了")
    elif "丧尸" in intro:
        grounded.append("丧尸爆发先把末世压力压出来了")
    elif "变异兽" in intro:
        grounded.append("变异兽把末世压力先压出来了")
    if "无限复活" in intro or "复活" in intro:
        grounded.append("无限复活不是爽文免死金牌，而是每次死完都要重新醒来")
    if "24小时" in intro or "二十四小时" in intro:
        grounded.append("规则很清楚：死后回到24小时前，循环有明确时间边界")
    if "安全屋" in intro:
        grounded.append("复活点落在安全屋，天然适合写囤物资、复盘路线和反复试错")
    if "惨烈" in intro or "噩梦" in intro or "死亡" in intro:
        grounded.append("雷点也很明确：反复死亡会带压迫感，不是轻松开挂")
    if "圣母系统" in intro:
        grounded.append("圣母系统这个设定很损：女主想活命，就得硬着头皮演圣母")
    if "重生" in intro and any(key in intro for key in ["男主", "陆行迟"]):
        grounded.append("男主带着上一世记忆回来，一开局就想把她丢进丧尸群")
    if "穿进" in intro or "穿书" in intro:
        grounded.append("穿书开局不是躺赢，而是先背上一个人人嫌的女配身份")
    if "希望" in intro and "幸存者" in intro:
        grounded.append("新城最后成了幸存者的希望，情绪落点比较稳")
    if rich_evidence:
        grounded.extend(rich_evidence)
    if grounded:
        return grounded[:4]

    content_brief = analysis.get("内容简报", {}) if isinstance(analysis, dict) else {}
    evidence = []
    if isinstance(content_brief, dict):
        raw = content_brief.get("证据素材", [])
        if not isinstance(raw, list):
            raw = [raw] if raw else []
        evidence.extend(raw)
    if not evidence:
        evidence.extend(_mobile_lines(work.get("简介", ""), max_len=42, max_lines=4))
    return _publish_fact_list(evidence, limit=4, max_len=58)


def _value_checklist_for_note(work, analysis, evidence, topic_hook):
    intro = str(work.get("简介", "") or "")
    text = " ".join([intro, " ".join(evidence or []), topic_hook])
    if any(k in text for k in ["无限复活", "复活", "循环", "24小时"]):
        return [
            "规则够不够硬：这本给了“死后回到24小时前”，不是随口说能重来",
            "代价够不够痛：反复死亡如果只当外挂，就会很水；简介里至少写到噩梦感",
            "目标够不够清楚：她不是为了刷爽点死来死去，而是在找破局办法、救在乎的人",
        ]
    if any(k in text for k in ["圣母系统", "穿书", "重生男主"]):
        return [
            "人设有没有反差：表面圣母和实际求生必须同时成立",
            "男主压力够不够强：重生男主想杀她，冲突不能只停在嘴上",
            "系统任务会不会重复：如果每章只刷数值，就容易疲",
        ]
    if evidence:
        return [f"看点{i}：{item}" for i, item in enumerate(evidence[:3], 1)]
    return []


def _emoji_for_note(work, analysis):
    text = " ".join([
        str(work.get("作品名称", "")),
        str(work.get("分类", "")),
        str(work.get("简介", "")),
        " ".join(str(t) for t in analysis.get("情绪触发", [])[:3]),
    ])
    if any(key in text for key in ["末世", "废土", "丧尸", "变异"]):
        return ["🏚️", "🧱", "🔥", "🍲", "📌"]
    if any(key in text for key in ["修仙", "仙侠", "宗门", "师尊"]):
        return ["⚔️", "🌙", "✨", "📌", "💬"]
    if any(key in text for key in ["星际", "机甲", "未来"]):
        return ["🚀", "🛡️", "🌌", "📌", "💬"]
    return ["📚", "✨", "📝", "📌", "💬"]


def _reader_verdict_line(work, analysis, evidence):
    name = work.get("作品名称", "") or "这本"
    category = _category_title_signal(work, analysis)
    joined = " ".join(evidence) + " " + str(work.get("简介", ""))
    if "基建" in joined or "建城" in joined or "城市建设" in joined:
        return f"{category}书荒可以先码住，《{name}》卖点是末世里从零建城"
    if "囤货" in joined:
        return f"{category}书荒可以先码住，《{name}》吃的是囤货和生存爽点"
    if "穿书" in joined or "炮灰" in joined:
        return f"{category}书荒可以先码住，《{name}》主打穿书后的反转感"
    return f"{category}书荒可以先码住，《{name}》先看这几个真实看点"


def _grounded_angle_points(work):
    intro = str(work.get("简介", "") or "")
    points = []
    if any(key in intro for key in ["丧尸", "变异兽", "末世", "废土"]):
        points.append("末世环境：丧尸与变异兽横行，生存压力先立住")
    if any(key in intro for key in ["清理废墟", "规划城区", "修复设施", "建立卫队", "恢复生产"]):
        points.append("基建线：清废墟、修设施、建卫队、恢复生产，爽点很具体")
    if any(key in intro for key in ["吃货", "烹煮", "城主"]):
        points.append("反差点：明鹰本来想当吃货，最后却成了城主")
    if any(key in intro for key in ["希望", "幸存者"]):
        points.append("情绪落点：新城成了幸存者的希望，不只是打怪升级")
    return points[:4]


def _grounded_emotion_points(work):
    intro = str(work.get("简介", "") or "")
    points = []
    if "末世" in intro:
        points.append("末世生存压力")
    if any(key in intro for key in ["清理废墟", "规划城区", "修复设施", "建立卫队", "恢复生产"]):
        points.append("从零建城的成就感")
    if any(key in intro for key in ["吃货", "烹煮", "城主"]):
        points.append("吃货城主的反差感")
    return points[:3]


def _grounded_story_take(work):
    """Write a human-sounding, synopsis-grounded recommendation paragraph."""
    intro = str(work.get("简介", "") or "")
    name = work.get("作品名称", "") or "这本"
    if all(key in intro for key in ["末世", "明鹰", "城主"]) and any(key in intro for key in ["清理废墟", "规划城区", "修复设施", "建立卫队"]):
        return [
            "🍲 最有意思的地方，不是又来一套末世打怪升级。",
            "明鹰重生回来，心愿其实很离谱：当个简单粗暴的吃货，把前世那些变异兽都端上桌。结果命运没让他闲着，直接把人推到城主的位置上。",
            "🧱 所以它更像“安全感慢慢搭起来”的文：清废墟、规划城区、修设施、建卫队、恢复生产。喜欢看基地从零到一的人，应该会比较吃这一口。",
        ]
    if "囤货" in intro:
        return [
            f"🍲 《{name}》不是只靠末世两个字撑场面。",
            "它好看的点在于，危机压下来之前，主角已经开始做准备。那种“别人还没反应过来，我已经把安全感攒起来了”的爽感，会很适合囤货文爱好者。",
        ]
    if "穿书" in intro or "炮灰" in intro:
        return [
            f"✨ 《{name}》吃的是开局身份差和反转感。",
            "主角不是站在舒服的位置上开挂，而是先被扔进一个麻烦身份里，再一点点把局面扳回来。喜欢看逆风翻盘的人，可以先码住。",
        ]
    if "无限复活" in intro or ("复活" in intro and "24小时" in intro):
        return [
            f"✨ 《{name}》的卖点不该只看“能复活”。",
            "重点是复活有没有规则、有代价、有破局目标。简介里写到死后回到24小时前、在安全屋醒来、反复经历惨烈死亡，这几个信息比单纯开挂更有判断价值。",
        ]
    return [
        f"📚 《{name}》不是那种一眼能夸满的简介，但核心设定是清楚的。",
        "它更适合先试读几章，看你吃不吃这个人设和冲突；没写出来的感情线、隐藏设定，这里就不替它脑补了。",
    ]


def _grounded_save_value_line(work):
    intro = str(work.get("简介", "") or "")
    if any(key in intro for key in ["清理废墟", "规划城区", "修复设施", "建立卫队", "恢复生产"]):
        return "你要是吃“末世基建一步步变强”这条线，可以先放进书单。"
    if "囤货" in intro:
        return "你要是吃“提前准备，把安全感攒满”这类爽点，可以先放进书单。"
    if "无限复活" in intro or ("复活" in intro and "24小时" in intro):
        return "这类文最怕把复活写成无成本外挂，所以前几章重点看：死亡代价、回档规则、每次试错有没有新信息。"
    return "你要是吃人设反差和明确冲突，可以先试读；只想看纯轻松甜爽的，先别闭眼冲。"


def _split_packaging_lines(text, max_lines=3, max_len=38):
    s = str(text or "").strip()
    if not s:
        return []
    raw_lines = []
    for chunk in re.split(r"[\n\r]+", s):
        raw_lines.extend([x.strip() for x in re.split(r"[。；;！!？?]", chunk) if x.strip()])
    lines = []
    for line in raw_lines:
        if not line:
            continue
        lines.append(_compact_mobile(line, max_len))
        if len(lines) >= max_lines:
            break
    return lines


def _sharp_fallback_lead(content_brief, cover_hook, work, p):
    name = work.get("作品名称", "") or "这本书"
    category = _compact_mobile(work.get("分类", ""), 18) or "网文"
    pain = _compact_mobile(content_brief.get("核心痛点", ""), 34)
    benefit = _compact_mobile(content_brief.get("读者收益", ""), 34)
    cover_title = _compact_mobile(cover_hook.get("主标题", ""), 18)
    if pain and benefit:
        return [f"先说结论：{name}适合书荒党", pain, benefit]
    if cover_title:
        return [f"先说结论：{cover_title}", f"{category}读者可以冲", f"看完能判断{name}合不合胃口"]
    opening = _compact_mobile(p.get("正文开头模板", ""), 34)
    return [f"先说结论：{name}值得放进书单", opening or f"{category}看点很集中", "先看这3个点再决定追不追"]


_NON_STORY_INTRO_PATTERNS = [
    "实体书",
    "出版",
    "开售",
    "签名",
    "围脖",
    "微博",
    "有声剧",
    "喜马拉雅",
    "详情关注",
    "限时",
    "预售",
    "番外",
    "作话",
]


def _looks_like_story_intro_line(text):
    s = str(text or "").strip()
    if not s:
        return False
    if any(p in s for p in _NON_STORY_INTRO_PATTERNS):
        return False
    # Avoid list/announcement fragments that carry dates or sales info instead of plot.
    if re.search(r"\d{4}年|\d+月\d+号|\d+点|第[一二三四五六七八九十\d]+册", s):
        return False
    return True


def _mobile_lines(text, max_len=36, max_lines=3):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return []
    parts = [x.strip() for x in re.split(r"[。；;！!？?]", s) if x.strip()]
    out = []
    for p in parts:
        if not _looks_like_story_intro_line(p):
            continue
        while p and len(p) > max_len and len(out) < max_lines:
            out.append(p[:max_len])
            p = p[max_len:]
        if p and len(out) < max_lines:
            out.append(p)
        if len(out) >= max_lines:
            break
    return out[:max_lines]


def _sanitize_image_prompt_for_jimeng(text):
    s = str(text or "")
    s = re.sub(r"《[^》]{1,40}》", "this story", s)
    risk_map = {
        "death": "danger",
        "kill": "confront",
        "blood": "red glow",
        "sacrifice": "cost",
        "prison": "restricted",
        "mad": "intense",
        "villain": "opponent",
        "weak": "calm",
    }
    low = s.lower()
    for k, v in risk_map.items():
        low = low.replace(k, v)
    s = low
    s = re.sub(r"\s+", " ", s).strip()
    return s[:380]


def _is_image_gen_async():
    return os.getenv("IMAGE_GEN_ASYNC", "false").strip().lower() in ["1", "true", "yes"]


def _enqueue_image_job(payload):
    os.makedirs(PATHS["logs"], exist_ok=True)
    payload = dict(payload or {})
    # Stable id for idempotency/observability (not used for security).
    try:
        import hashlib

        h = hashlib.sha256()
        h.update(str(payload.get("xhs_record_id", "")).encode("utf-8"))
        h.update(b"\n")
        h.update(str(payload.get("per_field_images", 2)).encode("utf-8"))
        h.update(b"\n")
        for p in (payload.get("prompts") or [])[:5]:
            h.update(str(p or "").encode("utf-8"))
            h.update(b"\n")
        payload.setdefault("job_id", h.hexdigest()[:24])
    except Exception:
        pass
    append_jsonl(os.path.join(PATHS["logs"], "image_jobs.jsonl"), payload)


def _extract_keywords(texts, limit=8):
    stop = {
        "作品",
        "作者",
        "平台",
        "分类",
        "主角",
        "女主",
        "男主",
        "配角",
        "冲突",
        "第一层",
        "第二层",
        "第三层",
        "开篇",
        "剧情",
        "读者",
        "情绪",
        "场景",
        "角色",
        "内容",
        "建议",
        "模板",
    }
    words = []
    for t in texts:
        for w in re.findall(r"[\u4e00-\u9fa5]{2,8}", str(t or "")):
            if w not in stop and len(w) >= 2:
                words.append(w)
    out = []
    seen = set()
    for w in words:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _visual_terms_from_text(text, limit=8):
    """把中文作品事实转成英文视觉锚点，避免把中文原文直接送进图片模型。"""
    raw = str(text or "")
    rules = [
        ("快穿", "quick transmigration arcs"),
        ("系统", "glowing mission interface"),
        ("纯爱", "boys love romance"),
        ("虎牙", "small fang smile"),
        ("糖", "candy motif"),
        ("投喂", "gentle feeding gesture"),
        ("亲亲", "tender near-kiss tension"),
        ("情感障碍", "reserved protagonist learning affection"),
        ("错过", "bittersweet missed-years mood"),
        ("十年", "long regret atmosphere"),
        ("技术", "clean tech workspace"),
        ("大佬", "confident genius aura"),
        ("计划", "strategic mastermind feeling"),
        ("现实", "real world bedroom"),
        ("虚拟", "virtual world glow"),
        ("小说", "story-world portal"),
        ("重生", "second chance turning point"),
        ("穿越", "time travel portal"),
        ("无限流", "survival game arena"),
        ("惊悚", "eerie suspense lighting"),
        ("克系", "cosmic horror atmosphere"),
        ("游戏", "dangerous game space"),
        ("仙侠", "ancient fantasy cultivation world"),
        ("修真", "cultivation sect courtyard"),
        ("古言", "ancient palace courtyard"),
        ("宫廷", "palace intrigue setting"),
        ("侯门", "noble household setting"),
        ("江湖", "martial arts riverside inn"),
        ("科幻", "futuristic sci-fi city"),
        ("星际", "space academy hangar"),
        ("机甲", "mecha cockpit"),
        ("末世", "post-apocalyptic street"),
        ("囤货", "survival supply warehouse with stacked food, water bottles, medical kits"),
        ("屯货", "survival supply warehouse with stacked food, water bottles, medical kits"),
        ("安全屋", "fortified safe house base with reinforced doors and storage shelves"),
        ("物资", "organized survival supplies and emergency boxes"),
        ("物品改造", "enchanted everyday objects transforming into helpful companions"),
        ("物品成精", "cute anthropomorphic household objects with lively expressions"),
        ("拟人化", "cute anthropomorphic objects with expressive faces"),
        ("洁癖花洒", "clean freak shower head character spraying sparkling water"),
        ("花洒", "animated shower head companion spraying sparkling water"),
        ("小刀", "small knife companion refusing to become a weapon"),
        ("手电筒", "flashlight companion glowing warmly with hopeful light"),
        ("奶妈", "support healer heroine protecting teammates with warm defensive aura"),
        ("辅助", "support role heroine protecting allies from behind the front line"),
        ("丧尸", "distant zombie silhouettes outside barricaded windows"),
        ("甜宠", "warm romantic sweetness"),
        ("虐心", "bittersweet emotional tension"),
        ("治愈", "soft healing atmosphere"),
        ("爽文", "high-energy triumph mood"),
        ("群像", "ensemble cast composition"),
        ("女主", "determined female protagonist"),
        ("男主", "male protagonist"),
        ("无女主", "no female lead"),
        ("无（纯爱", "no female lead"),
    ]
    terms = []
    for key, value in rules:
        if key in raw and value not in terms:
            terms.append(value)
        if len(terms) >= limit:
            break
    return terms


def _join_visual_terms(*texts, fallback="", limit=8):
    terms = []
    for text in texts:
        for term in _visual_terms_from_text(text, limit=limit):
            if term not in terms:
                terms.append(term)
            if len(terms) >= limit:
                break
        if len(terms) >= limit:
            break
    if not terms and fallback:
        return fallback
    return ", ".join(terms)


def _story_visual_anchors(work, analysis, limit=12):
    packaging = analysis.get("小红书包装", {}) if isinstance(analysis.get("小红书包装"), dict) else {}
    brief = analysis.get("内容简报", {}) if isinstance(analysis.get("内容简报"), dict) else {}
    characters = analysis.get("人物设定", {}) if isinstance(analysis.get("人物设定"), dict) else {}
    conflict = analysis.get("冲突设计", {}) if isinstance(analysis.get("冲突设计"), dict) else {}
    texts = [
        work.get("作品名称", ""),
        work.get("分类", ""),
        _ensure_required_synopsis(work),
        packaging.get("小红书标题模板", ""),
        packaging.get("封面图描述建议", ""),
        packaging.get("正文开头模板", ""),
        packaging.get("视觉风格建议", ""),
        packaging.get("热门标签推荐", ""),
        brief.get("核心痛点", "") if isinstance(brief, dict) else "",
        brief.get("读者收益", "") if isinstance(brief, dict) else "",
        brief.get("证据素材", "") if isinstance(brief, dict) else "",
        characters,
        conflict,
    ]
    anchors = []
    for text in texts:
        for term in _visual_terms_from_text(text, limit=limit):
            if term not in anchors:
                anchors.append(term)
            if len(anchors) >= limit:
                break
    if any("safe house" in a or "warehouse" in a or "survival supplies" in a for a in anchors):
        noisy = {"futuristic sci-fi city", "glowing mission interface"}
        anchors = [a for a in anchors if a not in noisy]
    return anchors[:limit]


def _pick_anchor(anchors, keywords, fallback):
    for keyword in keywords:
        for anchor in anchors:
            if keyword.lower() in anchor.lower():
                return anchor
    return fallback


def _is_no_female_lead(work, analysis):
    text = " ".join([
        str(work.get("分类", "") or ""),
        str(work.get("取向", "") or ""),
        str((analysis.get("人物设定") or {}).get("女主", "") or ""),
    ])
    return any(k in text for k in ["纯爱", "无女主", "无（纯爱", "BL", "bl"])


def _character_desc_for_image(work, analysis):
    if _is_no_female_lead(work, analysis):
        return "two male leads, one reserved protagonist, one warm strategic genius"
    characters = analysis.get("人物设定", {}) if isinstance(analysis.get("人物设定"), dict) else {}
    male_text = str(characters.get("男主", "") or "")
    if not male_text or "推测" in male_text or "可能" in male_text:
        return "determined female survival protagonist, cute anthropomorphic object companions, supportive allies"
    return "determined female protagonist and restrained male lead"


def _style_bible_for_image_prompts(scene_text, visual_source):
    """按作品调性生成整组图片共享的画风说明。"""
    text = " ".join([str(scene_text or ""), str(visual_source or "")])
    if any(k in text for k in ["末世", "无限流", "惊悚", "克系", "悬疑", "生存"]):
        tone = (
            "Style bible: cinematic dark anime, deep indigo and cold teal palette, "
            "sharp rim light, tense atmosphere, clean detailed linework, dramatic shadows"
        )
    elif any(k in text for k in ["纯爱", "甜宠", "治愈", "糖", "虎牙"]):
        tone = (
            "Style bible: warm pastel anime romance, soft peach and lavender palette, "
            "gentle glow, clean rounded linework, cozy emotional atmosphere"
        )
    elif any(k in text for k in ["仙侠", "修真", "古言", "宫廷", "侯门", "江湖"]):
        tone = (
            "Style bible: soft historical fantasy anime, jade green and moonlit gold palette, "
            "flowing robes, elegant linework, misty lantern lighting"
        )
    elif any(k in text for k in ["科幻", "星际", "机甲", "未来"]):
        tone = (
            "Style bible: sleek sci-fi anime, electric blue and silver palette, "
            "holographic glow, precise mechanical linework, high-tech lighting"
        )
    else:
        tone = (
            "Style bible: polished editorial anime illustration, cohesive soft color palette, "
            "clean linework, gentle cinematic lighting, emotionally readable faces"
        )
    return (
        f"{tone}. Keep the same art style, color palette, character facial features, "
        "hair shapes, clothing language, line thickness, shading method, and rendering quality "
        "across all images in this carousel."
    )


def _strip_all_cjk(text):
    """彻底移除文本中所有CJK字符（中日韩），只保留英文/数字/标点"""
    p = str(text or "")
    p = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', '', p)
    p = re.sub(r'[\u3040-\u309f\u30a0-\u30ff]', '', p)
    p = re.sub(r'[\uac00-\ud7af]', '', p)
    p = re.sub(r'\s+', ' ', p).strip()
    return p


def _sanitize_prompt_for_image_gen(prompt):
    """发送给图片生成API前强制净化：
    1. 彻底清除所有CJK字符（核心修复：之前只截断长句，现在全删）
    2. 强制统一 anime/manga 插画风格
    3. 末尾追加强制无文字指令
    """
    p = str(prompt or "")
    # 第一步：移除引号包裹的内容（用原始字符串避免转义问题）
    quote_pattern = r'["“”「」『』《》][^"“”「」『』《》]{0,80}["“”「」『』《》]'
    p = re.sub(quote_pattern, "", p)
    # 第二步：彻底移除所有CJK字符——这是消除图片上文字的关键
    p = _strip_all_cjk(p)
    # 第三步：清理多余空白
    p = re.sub(r"\s+", " ", p).strip()
    # 第四步：如果prompt被清空太短，用通用视觉描述兜底
    if len(p) < 40:
        p = "anime manga illustration, beautiful character portrait, emotional atmosphere"
    # 第五步：末尾强追加 统一风格 + 禁止文字
    suffix = (
        ". Style: anime manga illustration, 2D cel-shaded art, consistent anime aesthetic. "
        "NOT realistic photo, NOT 3D render, NOT photographic style. "
        "NO text, NO words, NO letters, NO subtitles, NO handwriting, "
        "NO watermark, NO logo, NO calligraphy, completely text-free image."
    )
    if "text-free" not in p.lower():
        p = p + suffix
    return p.strip()


def _normalize_visual_storyboard(value):
    if not isinstance(value, list):
        return []
    shots = []
    for i, item in enumerate(value[:5], 1):
        if isinstance(item, str):
            item = {"英文画面提示词": item, "剧情依据": item}
        if not isinstance(item, dict):
            continue
        prompt_en = (
            item.get("英文画面提示词")
            or item.get("visual_prompt_en")
            or item.get("prompt_en")
            or item.get("prompt")
            or ""
        )
        prompt_en = str(prompt_en or "").strip()
        # A usable storyboard must carry an English visual prompt. Chinese-only
        # fields are kept for traceability but not sent to image generation.
        if len(_strip_all_cjk(prompt_en)) < 40:
            continue
        shot = dict(item)
        shot["页码"] = i
        shot["英文画面提示词"] = prompt_en
        shots.append(shot)
    return shots


def _prompt_from_visual_shot(shot, work, analysis, index, style_bible):
    role = str(shot.get("作用") or "").strip()
    basis = str(shot.get("剧情依据") or "").strip()
    avoid = str(shot.get("避免") or "").strip()
    prompt_en = str(shot.get("英文画面提示词") or "").strip()
    prompt = (
        f"{prompt_en}. {style_bible} "
        f"Carousel page {index + 1}, role: {_strip_all_cjk(role) or 'story beat'}. "
        "Keep the same protagonist design and visual language as other pages. "
    )
    if basis:
        prompt += "This image is based on the provided synopsis, avoid invented relationships. "
    if avoid:
        prompt += "Avoid unsupported story elements. "
    prompt += (
        "No book cover mockup, no UI, no panels, no speech bubbles, no signs, "
        "no text, no words, no letters, completely text-free image."
    )
    return _sanitize_prompt_for_image_gen(prompt)


def _ensure_required_synopsis(work):
    """为飞书主表必填的简介字段提供最小可用兜底。"""
    intro = str(work.get("简介") or work.get("剧情简介") or "").strip()
    if intro:
        return intro

    name = str(work.get("作品名称") or "该作品").strip()
    author = str(work.get("作者") or "").strip()
    category = str(work.get("分类") or "").strip()
    platform = str(work.get("平台") or "").strip()
    parts = [f"《{name}》"]
    if author:
        parts.append(f"作者为{author}")
    if category:
        parts.append(f"分类为{category}")
    if platform:
        parts.append(f"来源平台为{platform}")
    base = "，".join(parts)
    return f"{base}。当前选题池未提供详细简介，先以作品名、作者、分类和平台信息作为拆解基础；后续可补充正式简介以提升内容准确度。"




def _build_image_prompts(work, analysis):
    category = str(work.get("分类", "") or "")
    intro = _ensure_required_synopsis(work)
    characters = analysis.get("人物设定", {}) or {}
    packaging = analysis.get("小红书包装", {}) or {}
    brief = analysis.get("内容简报", {}) or {}
    conflict = analysis.get("冲突设计", {})
    cover_hook = brief.get("封面钩子", {}) if isinstance(brief, dict) else {}

    visual_source = " ".join([
        category,
        intro,
        str(characters),
        str(conflict),
        str(packaging.get("封面图描述建议", "")),
        str(brief.get("图文页结构", "") if isinstance(brief, dict) else ""),
        str(brief.get("证据素材", "") if isinstance(brief, dict) else ""),
        str(cover_hook),
    ])
    style_bible = _style_bible_for_image_prompts(" ".join([category, intro]), visual_source)
    storyboard = _normalize_visual_storyboard(analysis.get("视觉分镜"))
    if len(storyboard) >= 4:
        return [_prompt_from_visual_shot(shot, work, analysis, i, style_bible) for i, shot in enumerate(storyboard[:5])]

    scene_text = " ".join([category, intro])
    is_action_genre = any(k in scene_text for k in ["仙侠", "玄幻", "悬疑", "科幻", "末世", "无限流", "战斗"])
    is_ancient = any(k in scene_text for k in ["仙侠", "修真", "古代", "宫廷", "侯门", "朝堂", "江湖"])
    no_female_lead = _is_no_female_lead(work, analysis)
    era_hint = "ancient fantasy era" if is_ancient else "modern era"
    anchors = _story_visual_anchors(work, analysis)
    world_hint = (
        "ancient architecture, layered silk robes, moonlight and lantern lighting"
        if is_ancient else
        ", ".join(anchors[:5]) or _join_visual_terms(visual_source, fallback="urban interior and night city lighting", limit=5)
    )

    character_desc = _character_desc_for_image(work, analysis)
    story_anchors = ", ".join(anchors[:8]) or _join_visual_terms(visual_source, fallback="story-specific emotional symbols", limit=8)
    safe_house = _pick_anchor(anchors, ["safe house", "warehouse", "supplies"], "fortified safe house base with organized survival supplies")
    object_magic = _pick_anchor(anchors, ["anthropomorphic", "shower", "knife", "flashlight"], "cute anthropomorphic household objects becoming helpful companions")
    support_role = _pick_anchor(anchors, ["support", "healer", "defensive"], "support heroine protecting teammates with a warm defensive aura")
    threat = _pick_anchor(anchors, ["zombie", "post-apocalyptic", "survival"], "distant zombie silhouettes outside barricaded windows")
    c1 = _join_visual_terms(conflict.get("第一层", ""), visual_source, fallback=threat, limit=5)
    c2 = _join_visual_terms(conflict.get("第二层", ""), visual_source, fallback=object_magic, limit=5)
    c3 = _join_visual_terms(conflict.get("第三层", ""), visual_source, fallback=support_role, limit=5)

    # 统一风格前缀：明确的 anime/manga 插画风格，排除写实照片风
    # 关键：所有prompt只包含英文，不含任何CJK字符
    anchor = (
        "anime manga illustration style, 2D cel-shaded art, Japanese anime aesthetic. "
        "Vertical 3:4 composition, vibrant colors, soft shading. "
        f"Era: {era_hint}. "
        f"Main cast: {character_desc}. "
        f"Story anchors: {story_anchors}. "
        f"{style_bible} "
        "Style must be consistent across all images: anime illustration only. "
        "NOT realistic photo, NOT 3D render, NOT photographic, NOT live-action."
    )

    p1 = (
        f"{anchor} Cover shot: confident female survival protagonist in a supply warehouse, half-body portrait, "
        f"she holds a clipboard and stands before stacked water bottles, canned food, medical kits, "
        f"with a fortified safe house mood and subtle cute object companions nearby. Visual symbols: {safe_house}, {object_magic}."
    )
    p2 = (
        f"{anchor} Worldbuilding shot: wide view of the fortified safe house base, storage shelves full of survival supplies, "
        f"reinforced door, barricaded windows, distant danger outside. Atmospheric depth showing {world_hint}."
    )
    if is_action_genre:
        p3 = (
            f"{anchor} Magic-object gag shot: anthropomorphic household objects become companions, "
            f"a clean freak shower head sprays sparkling water, a small knife companion refuses to be a weapon, "
            f"a flashlight glows warmly. Comedic contrast inside the safe house, {object_magic}."
        )
        p4 = (
            f"{anchor} Survival support shot: heroine protects allies from behind the front line with warm defensive aura, "
            f"zombie silhouettes and broken city lights outside the barricade, tense but funny contrast, {support_role}, {threat}."
        )
    else:
        p3 = (
            f"{anchor} Relationship shot: protagonist and love interest together but distant, "
            f"medium shot, warm indoor lighting, quiet daily-life moment hinting {c1}."
        )
        p4 = (
            f"{anchor} Emotional close-up: protagonist alone near window, "
            f"soft bokeh, gentle light on face, inner emotion of {c3}."
        )
    p5 = (
        f"{anchor} Group ending: heroine, allies, and cute anthropomorphic objects gather inside the safe house, "
        "morning light through reinforced windows, supplies neatly stacked, hopeful survival comedy mood."
    )
    return [_sanitize_prompt_for_image_gen(p) for p in [p1, p2, p3, p4, p5]]




def load_selected_work():
    path = os.path.join(PATHS["temp"], "selected_work.json")
    source = os.getenv("TOPIC_SOURCE", "local").strip().lower()
    # In Feishu mode always refresh from server to avoid reusing stale cached topic.
    if source != "feishu" and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        return cached
    if source == "feishu":
        record = select_work_from_topic_library()
        if not record:
            raise RuntimeError("飞书选题库无可拆解记录")
        work = record.get("fields", {})
        work["_topic_record_id"] = record.get("record_id")
        temp_path = os.path.join(PATHS["temp"], "selected_work.json")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(work, f, ensure_ascii=False, indent=2)
        return work
    return select_work()


def build_report(work, search_info, analysis):
    lines = []
    lines.append(f"# 拆解报告：{work.get('作品名称','')} - {work.get('作者','')}")
    lines.append("")
    lines.append("## 基础信息")
    for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态"]:
        v = work.get(k) or search_info.get(k, "")
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## 开篇套路")
    for item in analysis["开篇套路"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 人物设定")
    lines.append(f"- 女主: {analysis['人物设定']['女主']}")
    lines.append(f"- 男主: {analysis['人物设定']['男主']}")
    lines.append(f"- 亮点配角: {analysis['人物设定']['亮点配角']}")
    lines.append("")

    lines.append("## 冲突设计")
    lines.append(f"- 第一层: {analysis['冲突设计']['第一层']}")
    lines.append(f"- 第二层: {analysis['冲突设计']['第二层']}")
    lines.append(f"- 第三层: {analysis['冲突设计']['第三层']}")
    lines.append("")

    lines.append("## 情绪触发")
    for item in analysis["情绪触发"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 金句")
    for item in analysis["金句"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 小红书包装字段")
    for k, v in analysis["小红书包装"].items():
        lines.append(f"- {k}: {v}")

    return "\n".join(lines)


def _format_strategy_template(template, **values):
    class _SafeDict(dict):
        def __missing__(self, key):
            return ""

    try:
        return str(template or "").format_map(_SafeDict(values))
    except Exception:
        return str(template or "")


def generate_title_options(work, analysis, account_strategy=None):
    """生成足量标题选项，混合模型候选、账号公式和网文号补充角度。"""
    account_strategy = account_strategy or get_account_strategy()
    name = work.get("作品名称", "")
    category = work.get("分类", "")
    fact_check = work.get("素材证据卡") or (work.get("素材厚度", {}) or {}).get("fact_check") or {}
    if fact_check.get("generation_mode") == "insufficient":
        topic = _short_topic_hook(work, analysis)
        return _dedupe_titles([
            f"{name}这本先别硬推 素材还不够",
            f"{topic}求反馈｜{name}看过的来聊聊",
            f"{name}能不能追 先蹲真实反馈",
            f"看过{name}的姐妹 报个雷点",
            f"{topic}素材征集 这本到底稳不稳",
            f"{name}先不下结论 求看过的人补充",
            f"{topic}书荒党求投喂 同款也行",
            f"这本{name}我先蹲评论区反馈",
        ], limit=10)
    p = analysis.get("小红书包装", {})
    content_brief = analysis.get("内容简报", {})
    brief_titles = content_brief.get("标题候选", []) if isinstance(content_brief, dict) else []
    if not isinstance(brief_titles, list):
        brief_titles = [str(brief_titles)] if brief_titles else []
    brief_titles = [
        str(t).strip()
        for t in brief_titles
        if str(t).strip() and not any(p in str(t) for p in _BRIEF_UNGROUNDED_PATTERNS)
    ]
    
    # 提取核心卖点（从开篇套路和冲突设计中提取关键词）
    opening = analysis.get("开篇套路", [""])[0] if analysis.get("开篇套路") else ""
    conflict = analysis.get("冲突设计", {}).get("第一层", "")
    emotion = analysis.get("情绪触发", ["爽感"])[0] if analysis.get("情绪触发") else "爽感"
    
    # 提取关键词（去除冗余描述）
    def _extract_keyword(text, max_len=8):
        s = re.split(r"[/、,，;；：:。！？?]", str(text or ""))[0]
        s = re.sub(r"\s+", "", s)
        return s[:max_len] if s else ""
    
    hook = _extract_keyword(opening)
    pain_point = _extract_keyword(conflict)
    
    # 账号策略标题公式优先，避免把某个账号的爆款经验写死在通用流程里。
    titles = []
    for t in brief_titles:
        if t not in titles:
            titles.append(t)

    category_signal = _category_title_signal(work, analysis)
    formula_values = {
        "name": name,
        "category": category_signal,
        "hook": hook or name or category or "这个设定",
        "pain_point": f"追{category_signal}总踩雷",
        "emotion": emotion,
    }
    formulas = account_strategy.get("title_formulas") or []
    if formulas:
        for formula in formulas:
            template = formula.get("template") if isinstance(formula, dict) else str(formula)
            title = _format_strategy_template(template, **formula_values).strip()
            if title:
                titles.append(title)
    else:
        titles.extend([
            f"{formula_values['pain_point']}？先看这本",
            f"这本{formula_values['category']}爽点太密了",
            f"{formula_values['hook']}，结果更上头",
            f"{formula_values['category']}新手必看",
            f"{formula_values['category']}你更想看哪种",
        ])

    hook_signal = _title_signal(hook or name, "这本书")
    pain_signal = f"追{category_signal}总踩雷"
    supplemental_titles = [
        f"书荒别急，{name}先看这几个点" if name else f"书荒别急，这本{category_signal}先看这几个点",
        f"{category_signal}值不值得追？先看爽点",
        f"{category_signal}避雷：适合谁先说清",
        f"{hook_signal}，这设定有点上头",
        f"喜欢{category_signal}的可以试试这本",
        f"{category_signal}党求投喂同款",
        f"这本{category_signal}我会为爽点收藏",
        f"{pain_signal}？这本先帮你试了",
        f"想看{category_signal}，这本有反差",
        f"{name}到底香不香？我先拆完了" if name else f"这本{category_signal}到底香不香",
        f"{category_signal}书荒党可以冲吗",
        f"这本{category_signal}反差点很会抓人",
    ]
    for title in supplemental_titles:
        if title:
            titles.append(title)
    
    # 使用原有标题模板（如果有）
    original_title = p.get("小红书标题模板", "")
    if original_title and original_title not in titles:
        insert_at = len(brief_titles)
        titles.insert(insert_at, original_title)
    
    return _dedupe_titles([_compact_mobile(t, 26) for t in titles], limit=12)


def _title_signal(text, fallback, max_len=8):
    s = re.sub(r"[《》【】\[\]\s]+", "", str(text or ""))
    s = re.split(r"[/、,，;；：:。！？?]", s)[0].strip()
    return s[:max_len] if s else fallback


def _category_title_signal(work, analysis):
    candidates = []
    packaging = analysis.get("小红书包装", {}) if isinstance(analysis, dict) else {}
    if isinstance(packaging, dict):
        tags = packaging.get("热门标签推荐") or []
        if not isinstance(tags, list):
            tags = [tags]
        candidates.extend(tags)
    category = work.get("分类", "") if isinstance(work, dict) else ""
    candidates.append(category)
    for raw in candidates:
        text = str(raw or "").strip().lstrip("#")
        if not text:
            continue
        if "/" in text:
            continue
        if any(key in text for key in ["文", "书", "安全屋", "囤货", "末世"]):
            return _title_signal(text, "网文", max_len=6)
    return _title_signal(category, "网文", max_len=6)


def _dedupe_titles(titles, limit=None):
    seen = set()
    out = []
    for title in titles:
        t = str(title or "").strip()
        if not t:
            continue
        if "/" in t or " / " in t:
            continue
        if re.search(r"[到成是把在了的]，", t):
            continue
        if "推荐推荐" in t:
            continue
        key = re.sub(r"[\s，。！？!?：:、,.]+", "", t).lower()
        near_key = key[:16]
        if key in seen:
            continue
        if near_key and near_key in seen:
            continue
        seen.add(key)
        seen.add(near_key)
        out.append(t)
        if limit and len(out) >= limit:
            break
    return out


_BRIEF_UNGROUNDED_PATTERNS = [
    "认知脚手架",
    "反套路写作技巧",
    "底层逻辑",
    "新领域",
    "安静努力",
    "大声内卷",
    "可复用",
    "努力方向感",
    "错误赛道",
    "换引擎",
]


def _grounded_brief_value(text, fallback, max_len=120):
    s = _compact_mobile(text, max_len)
    if not s:
        return fallback
    if any(p in s for p in _BRIEF_UNGROUNDED_PATTERNS):
        return fallback
    return s


def _safe_content_brief_for_note(work, analysis):
    content_brief = analysis.get("内容简报", {})
    if not isinstance(content_brief, dict):
        content_brief = {}

    name = work.get("作品名称", "") or "这本书"
    category = work.get("分类", "") or "这个题材"
    fallback_pain = f"想判断《{name}》值不值得追，但只看标签很难抓住真正看点"
    fallback_benefit = f"快速看懂《{name}》的人设、冲突和爽点，判断是否适合加入书单"

    safe = dict(content_brief)
    safe["核心痛点"] = _grounded_brief_value(content_brief.get("核心痛点", ""), fallback_pain)
    safe["读者收益"] = _grounded_brief_value(content_brief.get("读者收益", ""), fallback_benefit)

    cover_hook = content_brief.get("封面钩子", {})
    if not isinstance(cover_hook, dict):
        cover_hook = {}
    safe_hook = dict(cover_hook)
    safe_hook["主标题"] = _grounded_brief_value(
        cover_hook.get("主标题", ""),
        f"{name}值不值得追",
        max_len=16,
    )
    safe_hook["副标题"] = _grounded_brief_value(
        cover_hook.get("副标题", ""),
        f"{category}看点速览",
        max_len=24,
    )
    safe_hook["点击理由"] = _grounded_brief_value(
        cover_hook.get("点击理由", ""),
        f"用作品设定和核心冲突判断《{name}》是否合口味",
        max_len=100,
    )
    safe["封面钩子"] = safe_hook
    return safe


def _select_best_title(titles, work):
    """选择最佳标题：优先短、具体、带作品或题材信号。"""
    name = work.get("作品名称", "")
    category = work.get("分类", "")
    cleaned = [_compact_mobile(t, 24) for t in titles if str(t).strip()]
    for t in cleaned:
        if name and name in t and len(t) <= 24:
            return t
    for t in cleaned:
        if category and category in t and len(t) <= 22:
            return t
    for t in cleaned:
        if len(t) <= 20:
            return t
    return cleaned[0] if cleaned else ""


def get_title_options(work, analysis, account_strategy=None):
    """返回备选标题列表（不含最佳标题），供前端选择器使用"""
    try:
        title_options = generate_title_options(work, analysis, account_strategy=account_strategy)
        best_title = _select_best_title(title_options, work)
        return _dedupe_titles([t for t in title_options if t != best_title], limit=10)
    except Exception:
        return []


def _pick_opening_type(note_type, opening_type=None, work=None, analysis=None, recent_context=None):
    opening_type = str(opening_type or "").strip()
    if opening_type and opening_type != "auto":
        return opening_type
    if note_type == "warning_review":
        return "warning_reversal"
    if note_type == "comment_experiment":
        return "book_shortage_rescue"
    seed = _note_variant_seed(work or {})
    return ["audience_filter", "strong_recommend", "rant_entry"][seed % 3]


def _frontstage_hooks(work, analysis, content_brief, evidence):
    category = _publish_phrase(work.get("分类", ""), 18, "网文")
    genre = category or "这个题材"
    core_sell = _publish_phrase((analysis.get("卖点分析") or {}).get("核心卖点", "") if isinstance(analysis.get("卖点分析"), dict) else "", 34)
    if _is_publish_unsafe_fact(core_sell):
        core_sell = ""
    first_evidence = core_sell or (evidence[0] if evidence else _publish_phrase(content_brief.get("读者收益", ""), 34, "设定够具体"))
    second_evidence = evidence[1] if len(evidence) > 1 else _publish_phrase(analysis.get("卖点分析", {}).get("核心卖点", ""), 34, "节奏比较稳")
    if _is_publish_unsafe_fact(second_evidence):
        second_evidence = _publish_phrase(content_brief.get("读者收益", ""), 34, "阅读判断很清楚")
    return {
        "genre": genre,
        "genre_hook": genre,
        "specific_hook": _publish_phrase(first_evidence, 26, "设定能落地"),
        "common_thunder": "只堆设定不推进",
        "apparent_risk": "简介看起来有点套路",
        "reversal_hook": _publish_phrase(first_evidence, 26, "核心看点很明确"),
        "real_threshold": "铺垫和题材门槛",
        "search_keyword": genre,
        "preference_a": _publish_phrase(genre, 18, "设定明确的文"),
        "risk_b": "只有标签没有具体冲突",
        "specific_strength": _publish_phrase(second_evidence, 26, "卖点比较清楚"),
        "anti_thunder_hook": _publish_phrase(first_evidence, 26, "不是只靠标签硬夸"),
        "specific_behavior": "有清晰行动线",
    }


def _build_opening_lines(work, analysis, account_strategy, note_type, opening_type, content_brief, evidence):
    opening_type = _pick_opening_type(note_type, opening_type, work, analysis)
    templates = (account_strategy or {}).get("opening_templates") or {}
    selected = templates.get(opening_type) if isinstance(templates, dict) else None
    hooks = _frontstage_hooks(work, analysis, content_brief, evidence)
    if selected:
        out = []
        for line in selected[:3]:
            try:
                text = str(line).format(**hooks)
            except Exception:
                text = str(line)
            out.append(_publish_clean(text, 56))
        return out, opening_type
    return [
        _publish_clean(_reader_verdict_line(work, analysis, evidence), 54),
        _publish_clean(_frontstage_hooks(work, analysis, content_brief, evidence).get("specific_hook"), 54),
        "先试前几章就够了，节奏稳不稳很快能看出来。",
    ], opening_type


def _build_cover_brief(work, analysis, account_strategy, note_type, cover_template, content_brief):
    cover_templates = (account_strategy or {}).get("cover_templates") or {}
    template = cover_templates.get(cover_template or note_type, {}) if isinstance(cover_templates, dict) else {}
    max_main = int(template.get("main_title_max_len") or 8)
    max_sub = int(template.get("subtitle_max_len") or 12)
    hook = content_brief.get("封面钩子", {}) if isinstance(content_brief, dict) else {}
    category = _publish_phrase(work.get("分类", ""), 8, "网文")
    topic_hook = _short_topic_hook(work, analysis)
    if note_type == "warning_review":
        main = f"{topic_hook}避雷"
        sub = "但这本能看"
    elif note_type == "comment_experiment":
        main = "求投喂"
        sub = f"{topic_hook}同款"
    else:
        main = f"{topic_hook}能追"
        sub = _publish_phrase(hook.get("主标题") or hook.get("副标题"), 18, "这本先码")
    return {
        "template": cover_template or note_type,
        "main_title": _compact_mobile(main, max_main),
        "subtitle": _compact_mobile(sub, max_sub),
        "examples": template.get("examples", []),
    }


def _short_topic_hook(work, analysis):
    text = " ".join([
        str(work.get("作品名称", "")),
        str(work.get("分类", "")),
        str(work.get("简介", "")),
        str((analysis.get("卖点分析") or {}).get("核心卖点", "") if isinstance(analysis.get("卖点分析"), dict) else ""),
    ])
    rules = [
        ("无限复活", "无限复活"),
        ("死亡循环", "死亡循环"),
        ("时间循环", "时间循环"),
        ("循环", "循环末世"),
        ("基建", "末世基建"),
        ("建城", "末世基建"),
        ("囤货", "末世囤货"),
        ("不圣母", "女主清醒"),
        ("丧尸", "末世文"),
        ("末世", "末世文"),
    ]
    for key, value in rules:
        if key in text:
            return value
    category = _publish_phrase(work.get("分类", ""), 8, "网文")
    return category or "网文"


def _first_safe_line(items, fallback="", max_len=54):
    for item in items or []:
        text = _publish_phrase(item, max_len=max_len)
        if text and not _is_publish_unsafe_fact(text):
            return text
    return _publish_phrase(fallback, max_len=max_len)


def _reading_boundary_line(read_status):
    if read_status == "full_read":
        return "我这版按全文体验说，夸和雷都会直接写。"
    if read_status == "read_to_chapter":
        return "我只看到前 N 章，所以后面会不会崩先不乱保票。"
    return "先说明一下：这篇只按简介里写明的内容判断，没脑补感情线。"


def _build_body_sections(work, analysis, note_type, content_brief, evidence, read_status):
    name = work.get("作品名称", "") or "这本"
    category = _compact_mobile(work.get("分类", ""), 18) or "网文"
    lines = []
    meta = [f"书名：《{name}》", f"作者：{work.get('作者','')}"]
    words = str(work.get("字数（万）") or work.get("字数") or "").strip()
    finish = str(work.get("完结状态", "")).strip()
    if words:
        meta.append(f"字数：{words}")
    if finish:
        meta.append(f"状态：{finish}")
    lines.extend(meta)
    lines.append("")
    if read_status == "synopsis_only":
        lines.append("先说边界：这篇只按简介和可验证信息判断，不把没出现的感情线/人设硬补上。")
        lines.append("")
    if evidence:
        lines.append("我会先看这几个点：")
        for item in evidence[:3]:
            lines.append(f"- {_publish_clean(item, 58)}")
        lines.append("")
    if note_type == "warning_review":
        lines.append("避雷角度看，它不是完全无门槛。")
        lines.append(_grounded_save_value_line(work))
    elif note_type == "comment_experiment":
        lines.append(f"我想继续找这种{category}，尤其是设定能落地、别只靠标签硬撑的。")
        lines.append("评论区可以直接报书名，我会优先挑同款来拆。")
    else:
        lines.extend(_grounded_story_take(work)[:2])
        lines.append(_grounded_save_value_line(work))
    lines.append("")
    return lines


def _build_frontstage_sections(work, analysis, note_type, content_brief, evidence, read_status):
    name = work.get("作品名称", "") or "这本"
    category = _compact_mobile(work.get("分类", ""), 18) or "网文"
    topic_hook = _short_topic_hook(work, analysis)
    material_quality = work.get("素材厚度") if isinstance(work.get("素材厚度"), dict) else {}
    material_level = material_quality.get("level", "")
    fact_check = work.get("素材证据卡") or material_quality.get("fact_check") or {}
    generation_mode = fact_check.get("generation_mode", "")
    core_sell = _publish_phrase((analysis.get("卖点分析") or {}).get("核心卖点", "") if isinstance(analysis.get("卖点分析"), dict) else "", 58)
    if _is_publish_unsafe_fact(core_sell):
        core_sell = ""
    strongest = core_sell or _first_safe_line(evidence, "", 58)
    checklist = _value_checklist_for_note(work, analysis, evidence, topic_hook)
    story_take = _grounded_story_take(work)
    lines = [
        f"书名：《{name}》",
        f"作者：{work.get('作者','')}",
        "",
    ]
    if note_type == "warning_review":
        lines.extend([
            f"⚠️ 这本不是无脑冲，但也没到一眼劝退。",
            f"主要看你吃不吃「{topic_hook}」这口。",
        ])
    elif note_type == "comment_experiment":
        lines.extend([
            f"💬 这篇我更想拿它当「{topic_hook}」同款入口。",
            "你手里有类似设定的话，直接报书名，我会优先拆。",
        ])
    else:
        lines.extend([
            (
                f"📌 这篇先按“简介快筛”写，不冒充全文拆解；目前能确认的是「{topic_hook}」这个钩子有得写。"
                if material_level in ("thin", "usable") or generation_mode != "grounded_note" else
                f"📌 这本不是闭眼神作，但「{topic_hook}」这个钩子有得写。"
            ),
            story_take[1] if len(story_take) > 1 else "简介里能看到具体冲突，不是只靠题材硬撑。",
        ])
    lines.append("")
    lines.append(f"✨ 最值得看的不是标签，是这个点：{strongest or topic_hook}")
    if checklist:
        lines.append("")
        lines.append("📌 收藏时可以直接按这几条筛：")
        for item in checklist[:3]:
            lines.append(f"- {_publish_clean(item, 64)}")
    lines.append("")
    lines.append(f"✅ 适合：{_audience_line(work, analysis, topic_hook)}")
    lines.append("")
    lines.append(f"🫷 不太适合：{_risk_line(work, analysis)}")
    lines.append("")
    if note_type == "warning_review":
        lines.append(f"所以它更像是：能吃「{topic_hook}」和一点压迫感的人可以试，只想看轻松爽文的先观望。")
    else:
        lines.append(_grounded_save_value_line(work))
    if read_status == "synopsis_only":
        if material_quality.get("gaps"):
            lines.append("资料边界：" + "；".join(material_quality.get("gaps")[:2]) + "。")
        lines.append("这篇只按简介里写明的信息说，后续反转不提前替它贷款。")
    lines.append("")
    return lines


def _boundary_warning(work, analysis, read_status):
    text = " ".join([str(work.get("简介", "")), str((analysis.get("卖点分析") or {}).get("核心卖点", ""))])
    if any(k in text for k in ["死亡", "虐", "痛苦", "绝望"]):
        return "死亡循环/压迫感会比较重，怕虐的先试读"
    if any(k in text for k in ["基建", "建城", "恢复生产"]):
        return "更吃慢慢建设的爽感，不一定是开局连环爆点"
    if read_status == "synopsis_only":
        return "目前只按简介判断，感情线和后续反转先不下结论"
    return "节奏和后续反转仍建议用前几章确认"


def _audience_line(work, analysis, topic_hook):
    audience = ((analysis.get("小红书包装") or {}).get("受众画像关键词", []) if isinstance(analysis.get("小红书包装"), dict) else [])
    if not isinstance(audience, list):
        audience = [str(audience)] if audience else []
    base = "、".join(str(a) for a in audience[:3] if str(a).strip())
    if base:
        return f"{base}，尤其是想找「{topic_hook}」明确看点的读者。"
    return f"喜欢{topic_hook}、想先判断值不值得追的书荒读者。"


def _risk_line(work, analysis):
    text = " ".join([str(work.get("简介", "")), str((analysis.get("卖点分析") or {}).get("核心卖点", ""))])
    if any(k in text for k in ["死亡", "虐", "痛苦", "绝望"]):
        return "只想看轻松治愈、低压无虐的人，可能会觉得累。"
    if any(k in text for k in ["基建", "建城"]):
        return "只想看一路打怪升级的人，可能会嫌建设线慢。"
    return "只想看强刺激爽点的人，建议先试读前几章。"


def _build_comment_hook(work, analysis, note_type, account_strategy=None):
    category = _compact_mobile(work.get("分类", ""), 16) or "同款"
    topic_hook = _short_topic_hook(work, analysis)
    intro = str(work.get("简介", "") or "")
    if note_type == "comment_experiment":
        return f"求投喂：{topic_hook}同款你最近看完还想安利的是哪本？"
    if note_type == "warning_review":
        return f"你看{topic_hook}最介意什么雷点？我下篇按这个标准拆。"
    if note_type == "booklist":
        return f"{category}书单你想看哪一类？报关键词我来补。"
    if "无限复活" in intro or ("复活" in intro and "24小时" in intro):
        return "无限复活文里，你更吃“越死越强”还是“越死越绝望”？有书名直接报。"
    if "圣母系统" in intro or ("穿书" in intro and "重生" in intro):
        return "末世穿书里，你更吃系统任务还是重生男主？有同款直接报书名。"
    return f"报一本你看过的{topic_hook}同款，我下篇就按这个标准拆。"


def _build_publish_tags(work, analysis, raw_tags):
    tags = _safe_publish_tags(raw_tags)
    topic = _short_topic_hook(work, analysis)
    text = " ".join([
        str(work.get("作品名称", "")),
        str(work.get("分类", "")),
        str(work.get("简介", "")),
    ])
    derived = []
    if topic:
        derived.append(topic)
    if "穿书" in text:
        derived.append("穿书文")
    if any(k in text for k in ["女配", "炮灰"]):
        derived.append("女配逆袭")
    if "末世" in text:
        derived.append("末世文")
    for tag in derived + ["网文推荐", "书荒推荐"]:
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:5]


def _humanized_title(work, analysis):
    intro = str(work.get("简介", "") or "")
    name = work.get("作品名称", "") or "这本"
    fact_check = work.get("素材证据卡") or (work.get("素材厚度", {}) or {}).get("fact_check") or {}
    if fact_check.get("generation_mode") == "insufficient":
        return f"{name}这本先别硬推 素材还不够"
    if "无限复活" in intro or ("复活" in intro and "死亡" in intro):
        return "死了又复活 复活了又死 这本末世文把我看精神了"
    if "圣母系统" in intro:
        return "系统逼她当圣母 男主还想杀她 这本有点损"
    if "穿书" in intro or "炮灰" in intro:
        return f"《{name}》这个开局身份真的不算友好"
    if any(k in intro for k in ["硬核丧尸", "囚车", "死刑犯", "行尸走肉"]):
        return f"《{name}》这种硬核丧尸开局我会想试"
    if any(k in intro for k in ["姜羊", "类人小怪物", "母子", "种植食物"]):
        return f"《{name}》这种末世种田温情线我会想试"
    if any(k in intro for k in ["锦鲤", "幸运值", "平地摔", "红通通苹果", "变异兔"]):
        return f"《{name}》这种末世锦鲤设定有点离谱"
    if any(k in intro for k in ["早死女配", "女配", "送金手指", "空间", "不是人"]):
        return f"《{name}》这个女配觉醒开局有点爽"
    return f"{name}这本我有点想聊聊"


def _humanized_body_lines(work, analysis, evidence, read_status="synopsis_only", manual_generation_brief=""):
    intro = str(work.get("简介", "") or "")
    name = work.get("作品名称", "") or "这本"
    author = work.get("作者", "")
    fact_check = work.get("素材证据卡") or (work.get("素材厚度", {}) or {}).get("fact_check") or {}
    can_write_personal = fact_check.get("read_scope") in ("public_trial_or_rich_material", "full_read")

    if fact_check.get("generation_mode") == "insufficient":
        return [
            f"《{name}》这条我先不硬拆。👀",
            f"作者：{author}",
            "",
            "目前系统没有拿到可追溯的官方简介、试读章节或读者评论。",
            "这种情况下如果继续写“它哪里好看、哪里雷”，本质就是在猜。",
            "",
            "所以这篇更适合当素材补全提醒：",
            "先补官方简介，再看有没有公开试读/目录/书评反馈。",
            "至少有两三条能对上的信息后，再写推荐会稳很多。⚠️",
            "",
            "你们如果看过这本，可以直接告诉我：开局抓不抓人、雷点在哪。",
            "我会按能查到的素材重新拆，不拿空话硬凑。📚",
        ]

    if "无限复活" in intro or ("复活" in intro and "死亡" in intro):
        opening = "家人们 我又挖到一本末世文。🫠" if can_write_personal else "家人们 这本末世文我先按可查素材看。🫠"
        return [
            opening,
            "",
            "说实话，最近末世文我已经有点看麻了。",
            "十本里有八本都在堆设定，丧尸、异能、安全屋，听起来很热闹，翻几章又像在看同一篇。",
            "",
            f"但《{name}》这个设定，我第一眼还是停住了。👀",
            f"作者：{author}",
            "",
            "女主沈秋会无限复活。",
            "每次死掉，她都会在安全屋的床上醒过来，时间倒回死亡前24小时。",
            "",
            "听起来像开挂，对吧。",
            "我一开始也这么想。",
            "",
            "但这个设定真正抓人的地方，不是“她能重来”。",
            "是她每一次重来之前，都真的死过一次。",
            "简介里写得很直白：惨烈的死亡、不断重复、像噩梦一样。",
            "",
            "所以我看到这里，脑子里一直冒三个问题：",
            "1. 她到底能复活几次？",
            "2. 每次回到24小时前，她能带回多少信息？",
            "3. 她最后是想活下去，还是想找到一种不用再死的办法？",
            "",
            "就这几个问题，已经比“女主有个无敌异能”好看多了。",
            "",
            "我比较吃这种设定的原因也在这儿：",
            "它不是把复活当奖励，而是把复活写成惩罚。",
            "别人末世求生是怕死，她是死了还得爬起来继续想办法。",
            "这个压力感如果写稳，会很上头。🔥",
            "",
            "但我也先说实话。⚠️",
            "如果你看文就是为了轻松解压，这本大概率不适合你。",
            "它不是甜爽挂，也不是那种一路开大清怪的末世文。",
            "它更像是：前面明知道是坑，但你还是想看她下一次怎么活。",
            "",
            "我会先把它放进“末世循环文待看”。",
            "不是因为它一定封神，而是因为这个复活规则有记忆点，有代价，也有破局目标。",
            "",
            "你们看过类似的吗？",
            "就是主角反复死亡、反复回档那种。",
            "我个人更吃“越死越绝望但越死越清醒”的，评论区报书名，我想去蹲几本。📚",
        ]

    if "圣母系统" in intro:
        return [
            "这本开局我看着就替女主头疼。😵",
            "",
            f"《{name}》",
            f"作者：{author}",
            "",
            "女主不是想当圣母，她是被系统逼着演圣母。",
            "更损的是，男主重生回来还想杀她。👀",
            "",
            "这种设定好看的点，不是“女主善良”，而是她明明在求生，还得把戏演完整。",
            "如果后面能写出那种表面温柔、心里疯狂盘算的反差，我会很吃。🔥",
            "",
            "但如果只是每章刷系统数值，那就容易疲。⚠️",
            "",
            "你们更吃这种被迫演戏的女主，还是一上来就掀桌子的女主？评论区给我投喂书名。📚",
        ]

    if any(k in intro for k in ["硬核丧尸", "囚车", "死刑犯", "行尸走肉"]):
        boundary = "我先按简介写，不冒充已看完全书。" if read_status == "synopsis_only" else ""
        brief_line = _publish_clean(manual_generation_brief, 72) if manual_generation_brief else ""
        return [
            "这本我会放进硬核末世待看。👀",
            "",
            f"《{name}》",
            f"作者：{author}",
            "",
            "它不是那种一上来就开金手指囤货的末世文。",
            "简介里的开局很具体：高速公路堵车，押送死刑犯的囚车被困，警官和司机先后遇难。",
            "",
            "这个设定最抓我的地方，是主角团的身份先天就不“干净”。",
            "丧尸在外面，囚犯在车里，文明规则又已经开始失效。",
            "这种开局如果写稳，会比单纯打怪更有压迫感。🔥",
            "",
            "我会盯这三件事：",
            "1. 囚犯之间会不会互相背刺",
            "2. 丧尸危机是不是只当背景板",
            "3. 人性挣扎有没有写实，而不是只靠血腥刺激",
            "",
            "适合想看硬核丧尸、生存压迫、无CP群像的人。",
            "如果你只想看轻松爽文、恋爱线很重的末世文，这本可能不是第一选择。⚠️",
            "",
            brief_line if brief_line else boundary,
            "",
            "你们更怕末世里的丧尸，还是更怕身边的活人？",
            "我先投活人一票。📚",
        ]

    if any(k in intro for k in ["姜羊", "类人小怪物", "母子", "种植食物"]):
        boundary = "我先按简介写，不冒充已看完全书。" if read_status == "synopsis_only" else ""
        brief_line = _publish_clean(manual_generation_brief, 72) if manual_generation_brief else ""
        return [
            "这本不是常见的末世爽文路子。👀",
            "",
            f"《{name}》",
            f"作者：{author}",
            "",
            "简介里最抓我的不是丧尸，也不是打怪升级。",
            "而是末世第十年，姜苓一个人在残破世界里活着，突然生下了一个类人小怪物姜羊。",
            "",
            "这个钩子很奇怪，但也很有记忆点。",
            "它把末世文常见的“活下去”，写成了另一种问题：",
            "当世界已经坏掉了，人还能不能重新养出一点关系、日常和牵挂。🔥",
            "",
            "我会盯这三件事：",
            "1. 母子线是细腻，还是只拿怪物孩子当噱头",
            "2. 种田日常有没有生活细节，而不是只喊治愈",
            "3. 末世背景够不够冷，能不能衬出那点温情",
            "",
            "适合想看慢热、末世种田、温情治愈的人。",
            "如果你只想看一路杀丧尸、升级爆爽，这本可能不是第一选择。⚠️",
            "",
            brief_line if brief_line else boundary,
            "",
            "末世文里你更吃哪种？",
            "废墟里种田过日子，还是开局一路打怪升级？📚",
        ]

    if any(k in intro for k in ["锦鲤", "幸运值", "平地摔", "红通通苹果", "变异兔"]):
        boundary = "我先按简介写，不冒充已看完全书。" if read_status == "synopsis_only" else ""
        brief_line = _publish_clean(manual_generation_brief, 72) if manual_generation_brief else ""
        return [
            "这本末世文的路子有点反着来。👀",
            "",
            f"《{name}》",
            f"作者：{author}",
            "",
            "别人写末世，是丧尸追着人跑。",
            "这本的钩子是：苏酥以为自己没觉醒异能，结果发现自己像把幸运值点满了。",
            "",
            "队友觉得丧尸难打，她看到的是丧尸集体平地摔。",
            "别人愁物资，她面前能掉苹果，变异兔还能自己撞晕。",
            "这种“末世很惨，但女主运气过分好”的反差，确实有笑点。🔥",
            "",
            "我会盯这三件事：",
            "1. 锦鲤异能是一直有梗，还是几章后就重复",
            "2. 轻松甜爽能不能压住末世背景的危险感",
            "3. 女主是单纯躺赢，还是会主动做选择",
            "",
            "适合想看轻松末世、甜爽反差、女主好运流的人。",
            "如果你想看硬核生存、资源博弈、刀口舔血，这本可能不是第一选择。⚠️",
            "",
            brief_line if brief_line else boundary,
            "",
            "末世文里你更吃哪种？",
            "女主靠实力一路打，还是靠离谱好运躺着赢？📚",
        ]

    if any(k in intro for k in ["早死女配", "女配", "送金手指", "空间", "不是人"]):
        boundary = "我先按简介写，不冒充已看完全书。" if read_status == "synopsis_only" else ""
        brief_line = _publish_clean(manual_generation_brief, 72) if manual_generation_brief else ""
        return [
            "这本的开局我会想先试几章。👀",
            "",
            f"《{name}》",
            f"作者：{author}",
            "",
            "苏涵被烟灰缸砸破头后觉醒，发现自己是末世小说里的早死女配。",
            "更惨的是，她原本存在的意义，就是开场送金手指给主角。",
            "",
            "这个设定爽点很明确：",
            "她这次没死，金手指还在自己手里，于是从“工具人女配”变成了自己求生的人。",
            "后面还埋了一个身份钩子：她好像不是人。🔥",
            "",
            "我会盯这三件事：",
            "1. 女主觉醒后够不够清醒，不要又回去给别人铺路",
            "2. 空间和金手指强度会不会失控",
            "3. 身份反转是不是有铺垫，而不是硬拐",
            "",
            "适合想看末世女配觉醒、空间求生、女主成长型的人。",
            "如果你只想看大女主开局碾压，这本可能要先看它成长线稳不稳。⚠️",
            "",
            brief_line if brief_line else boundary,
            "",
            "末世女配文你们更吃哪种？",
            "清醒搞事业，还是带空间慢慢攒安全感？📚",
        ]

    return [
        f"《{name}》我先按可查素材看了一眼。👀",
        f"作者：{author}",
        "",
        "目前能确定的信息不算多，所以我不想硬夸。",
        "但它至少有一个能继续往下看的钩子：",
        _first_safe_line(evidence, "核心冲突是清楚的", 64),
        "",
        "这种书我一般不会直接冲，会先看前几章是不是有具体情节在推进。⚠️",
        "",
        "你们看过的话，可以直接告诉我它后面稳不稳。📚",
    ]


def _build_humanized_note(
    work,
    analysis,
    tags,
    use_formula=True,
    account_strategy=None,
    note_type="normal_recommendation",
    opening_type=None,
    read_status="synopsis_only",
    cover_template=None,
    source_confidence="synopsis",
    manual_generation_brief="",
):
    title = _humanized_title(work, analysis)
    evidence = _evidence_points_for_note(work, analysis)
    lines = [f"【标题】{title}", ""]
    lines.extend(_humanized_body_lines(work, analysis, evidence, read_status=read_status, manual_generation_brief=manual_generation_brief))
    if tags:
        lines.append("")
        lines.append(" ".join(f"#{str(t).strip().lstrip('#')}" for t in tags[:5] if str(t).strip()))
    note = _clean_publish_note("\n".join(lines))
    note = apply_xhs_humanize_note_skill(note, work=work, analysis=analysis, tags=tags)
    analysis["frontstage_note"] = note
    analysis["backstage_analysis"] = analysis.get("内容简报") or {}
    analysis["generation_params"] = {
        "note_type": note_type,
        "opening_type": opening_type or "human_story",
        "cover_template": cover_template or "normal_recommendation",
        "read_status": read_status,
        "source_confidence": source_confidence,
        "manual_generation_brief": manual_generation_brief,
        "cover_brief": _build_cover_brief(work, analysis, account_strategy or get_account_strategy(), note_type, cover_template or "normal_recommendation", _safe_content_brief_for_note(work, analysis)),
    }
    return note


def build_xhs_note(
    work,
    analysis,
    use_formula=True,
    account_strategy=None,
    note_type="normal_recommendation",
    opening_type=None,
    read_status="synopsis_only",
    cover_template=None,
    source_confidence="synopsis",
    manual_generation_brief="",
):
    account_strategy = account_strategy or get_account_strategy()
    p = analysis["小红书包装"]
    content_brief = _safe_content_brief_for_note(work, analysis)
    tags = p.get("热门标签推荐", [])
    if not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    tags = _build_publish_tags(work, analysis, tags)
    if note_type == "normal_recommendation":
        return _build_humanized_note(
            work,
            analysis,
            tags,
            use_formula=use_formula,
            account_strategy=account_strategy,
            note_type=note_type,
            opening_type=opening_type,
            read_status=read_status,
            cover_template=cover_template,
            source_confidence=source_confidence,
            manual_generation_brief=manual_generation_brief,
        )
    intro_lines = _mobile_lines(work.get("简介", ""), max_len=96, max_lines=2)
    words = str(work.get("字数（万）") or work.get("字数") or "").strip()
    score = str(work.get("评分", "")).strip()
    finish = str(work.get("完结状态", "")).strip()
    evidence = _evidence_points_for_note(work, analysis)
    note_emoji = _emoji_for_note(work, analysis)
    lines = []

    if use_formula:
        title_options = generate_title_options(work, analysis, account_strategy=account_strategy)
        best_title = _select_best_title(title_options, work)
        lines.append(f"【标题】{best_title}")
    else:
        lines.append(f"【标题】{p.get('小红书标题模板', '')}")
    lines.append("")

    opening_lines, selected_opening = _build_opening_lines(
        work, analysis, account_strategy, note_type, opening_type, content_brief, evidence
    )
    for marker, text in zip(note_emoji[:3], opening_lines):
        if text:
            lines.append(f"{marker} {_publish_clean(text, 52)}")
    lines.append("")

    cover_brief = _build_cover_brief(work, analysis, account_strategy, note_type, cover_template or note_type, content_brief)

    lines.extend(_build_frontstage_sections(work, analysis, note_type, content_brief, evidence, read_status))

    cta = _build_comment_hook(work, analysis, note_type, account_strategy)
    lines.append(f"💬 {cta}")
    lines.append("我会从评论区挑一本继续拆。")
    lines.append("")

    topic_hook = _short_topic_hook(work, analysis)
    lines.append(f"📌 先收藏，下次想找「{topic_hook}」时不用从书海里重新翻。")
    lines.append("")

    lines.append("🏷️ 标签")
    lines.append(" ".join(tags))
    note = _clean_publish_note("\n".join(lines))
    note = apply_xhs_humanize_note_skill(note, work=work, analysis=analysis, tags=tags)
    analysis["frontstage_note"] = note
    analysis["backstage_analysis"] = analysis.get("内容简报") or {}
    analysis["generation_params"] = {
        "note_type": note_type,
        "opening_type": selected_opening,
        "cover_template": cover_template or note_type,
        "read_status": read_status,
        "source_confidence": source_confidence,
        "cover_brief": cover_brief,
    }
    return note


def build_experiment_log(work, analysis):
    lines = []
    lines.append(f"日期: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"作品: {work.get('作品名称','')} - {work.get('作者','')}")
    lines.append("观察:")
    lines.append("- 生成流程正常")
    lines.append(f"- 模型来源: {analysis['元信息']['来源']}")
    return "\n".join(lines)


def sync_to_feishu(work, search_info, analysis):
    client = FeishuClient()
    if not client.is_configured():
        return None

    def _normalize_multi(value):
        if value is None:
            return []
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                out = []
                for it in value:
                    if not isinstance(it, dict):
                        out.append(str(it))
                        continue
                    raw = it.get("id") or it.get("option_id") or it.get("value") or it.get("name") or it.get("text")
                    if raw:
                        out.append(str(raw))
                return out
            return value
        if isinstance(value, str):
            # split common separators
            parts = [p.strip() for p in re.split(r"[/、,，;；]", value) if p.strip()]
            return parts if parts else [value.strip()]
        return [str(value)]

    def _looks_like_opt_id(text):
        s = str(text or "").strip()
        return bool(re.fullmatch(r"opt[0-9A-Za-z]+", s))

    def _normalize_word_count_wan(value):
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return 0.0
        s = str(value).strip().replace(",", "")
        if not s or s in ["未明确提供", "未知", "暂无", "无"]:
            return 0.0
        match = re.search(r"(\d+(?:\.\d+)?)", s)
        if not match:
            return 0.0
        num = float(match.group(1))
        if "万" in s:
            return num
        if "字" in s and num >= 1000:
            return round(num / 10000, 2)
        return num

    def _extract_number(value):
        if isinstance(value, (int, float)):
            return float(value)
        if value is None:
            return None
        s = str(value).strip().replace(",", "")
        if not s:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)", s)
        if not match:
            return None
        return float(match.group(1))

    fields = {
        "作品名称": work.get("作品名称", ""),
        "作者": work.get("作者", ""),
        "平台": work.get("平台", ""),
        "分类": work.get("分类", ""),
        "评分": work.get("评分", ""),
        "字数（万）": _normalize_word_count_wan(
            work.get("字数（万）")
            or work.get("字数")
            or work.get("字数（万字）")
            or work.get("字数_万_")
            or search_info.get("字数（万）")
            or search_info.get("字数")
            or search_info.get("字数（万字）")
        ),
        "完结状态": work.get("完结状态", ""),
        "简介": work.get("简介", ""),
        "取向": work.get("取向", ""),
        "核心冲突": " / ".join(
            [
                analysis.get("冲突设计", {}).get("第一层", ""),
                analysis.get("冲突设计", {}).get("第二层", ""),
                analysis.get("冲突设计", {}).get("第三层", ""),
            ]
        ).strip(" /"),
        "情绪分析摘要": "、".join(analysis["情绪触发"]),
        "情绪钩子": "、".join(analysis["情绪触发"][:3]),
        "情节节点摘要": "；".join(analysis["开篇套路"][:3]),
        "金句（Top5）": "\n".join(analysis["金句"][:5]),
    }
    field_meta = client.get_table_field_meta(client.table_id)
    available_fields = set(field_meta.keys())
    fields = {k: v for k, v in fields.items() if k in available_fields}

    # Normalize values by actual field types from Feishu.
    # type=2 number, type=3 single select, type=4 multi select
    for key, val in list(fields.items()):
        ftype = (field_meta.get(key) or {}).get("type")
        if ftype == 21:
            fields.pop(key, None)
            continue
        if ftype == 4:
            vals = _normalize_multi(val)
            # Resolve to option ids when possible to avoid unreadable option tokens.
            opts = (field_meta.get(key) or {}).get("property", {}).get("options") or []
            name_to_id = {str(o.get("name")).strip(): (o.get("id") or o.get("option_id") or o.get("value")) for o in opts if o.get("name")}
            id_set = {str(o.get("id") or o.get("option_id") or o.get("value")) for o in opts if (o.get("id") or o.get("option_id") or o.get("value"))}
            resolved = []
            for v in vals:
                s = str(v).strip()
                if s in id_set:
                    resolved.append(s)
                elif s in name_to_id:
                    resolved.append(str(name_to_id[s]))
            fields[key] = resolved
        elif ftype == 3:
            if isinstance(val, list):
                fields[key] = val[0] if val else ""
            elif val is None:
                fields[key] = ""
            else:
                # Prefer option id when options exist; fall back to raw string.
                s = str(val).strip()
                if s:
                    opts = (field_meta.get(key) or {}).get("property", {}).get("options") or []
                    name_to_id = {
                        str(o.get("name")).strip(): (o.get("id") or o.get("option_id") or o.get("value"))
                        for o in opts
                        if o.get("name")
                    }
                    id_set = {
                        str(o.get("id") or o.get("option_id") or o.get("value"))
                        for o in opts
                        if (o.get("id") or o.get("option_id") or o.get("value"))
                    }
                    if s in id_set:
                        fields[key] = s
                    elif s in name_to_id:
                        fields[key] = str(name_to_id[s])
                    else:
                        fields[key] = ""
                else:
                    fields[key] = ""
        elif ftype == 2:
            if key == "字数（万）":
                fields[key] = _normalize_word_count_wan(val)
            else:
                fields[key] = _extract_number(val)
    missing = validate_required("主表", fields, available_fields=available_fields)
    if missing:
        raise RuntimeError(f"主表缺必填字段: {missing}")

    record_id = find_by_title_author(work.get("作品名称", ""), work.get("作者", ""))
    if record_id:
        work["_existing_main_record"] = True
        if os.getenv("SKIP_EXISTING", "false").strip().lower() in ["1", "true", "yes"]:
            return record_id
        client.update_record(record_id, fields)
        return record_id

    record_id = client.create_record(fields)
    return record_id


def sync_xhs_note_table(main_record_id, work, analysis, xhs_path):
    client = FeishuClient()
    if not client.is_configured():
        return None
    table_id = client.config.get("related_table_ids", {}).get("小红书笔记库")
    if not table_id:
        return None

    xhs_pack = analysis.get("小红书包装", {})
    fields = {
        "作品名称": work.get("作品名称", ""),
        "作者": work.get("作者", ""),
        "主表记录ID": main_record_id,
        "记录表ID": main_record_id,
        "小红书标题模板": xhs_pack.get("小红书标题模板", ""),
        "封面图描述建议": xhs_pack.get("封面图描述建议", ""),
        "热门标签推荐": xhs_pack.get("热门标签推荐", []),
        "正文开头模板": xhs_pack.get("正文开头模板", ""),
        "正文结构建议": xhs_pack.get("正文结构建议", ""),
        "互动话术模板": xhs_pack.get("互动话术模板", ""),
        "受众画像关键词": xhs_pack.get("受众画像关键词", []),
        "内容类型标签": xhs_pack.get("内容类型标签", ""),
        "更新时间": datetime.now().strftime("%Y-%m-%d"),
    }
    prompts = analysis.get("配图提示词", [])
    if not isinstance(prompts, list):
        prompts = []
    for i in range(5):
        fields[f"生成配图提示词{i+1}"] = prompts[i] if i < len(prompts) else ""

    field_meta = client.get_table_field_meta(table_id)
    available_fields = set(field_meta.keys())
    fields = {k: v for k, v in fields.items() if k in available_fields}

    def _normalize_multi(value):
        if value is None:
            return []
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                out = []
                for it in value:
                    if not isinstance(it, dict):
                        out.append(str(it))
                        continue
                    raw = it.get("id") or it.get("option_id") or it.get("value") or it.get("name") or it.get("text")
                    if raw:
                        out.append(str(raw))
                return out
            return value
        if isinstance(value, str):
            parts = [p.strip() for p in re.split(r"[/、,，;；]", value) if p.strip()]
            return parts if parts else [value.strip()]
        return [str(value)]

    def _looks_like_opt_id(text):
        s = str(text or "").strip()
        return bool(re.fullmatch(r"opt[0-9A-Za-z]+", s))

    for key, val in list(fields.items()):
        ftype = (field_meta.get(key) or {}).get("type")
        if ftype == 4:
            vals = _normalize_multi(val)
            opts = (field_meta.get(key) or {}).get("property", {}).get("options") or []
            name_to_id = {str(o.get("name")).strip(): (o.get("id") or o.get("option_id") or o.get("value")) for o in opts if o.get("name")}
            id_set = {str(o.get("id") or o.get("option_id") or o.get("value")) for o in opts if (o.get("id") or o.get("option_id") or o.get("value"))}
            resolved = []
            for v in vals:
                s = str(v).strip()
                if s in id_set:
                    resolved.append(s)
                elif s in name_to_id:
                    resolved.append(str(name_to_id[s]))
                elif s and (not _looks_like_opt_id(s)):
                    resolved.append(s)
            fields[key] = resolved
        elif ftype == 3:
            if isinstance(val, list):
                fields[key] = val[0] if val else ""
            else:
                s = str(val or "").strip()
                if s:
                    opts = (field_meta.get(key) or {}).get("property", {}).get("options") or []
                    name_to_id = {
                        str(o.get("name")).strip(): (o.get("id") or o.get("option_id") or o.get("value"))
                        for o in opts
                        if o.get("name")
                    }
                    id_set = {
                        str(o.get("id") or o.get("option_id") or o.get("value"))
                        for o in opts
                        if (o.get("id") or o.get("option_id") or o.get("value"))
                    }
                    if s in id_set:
                        fields[key] = s
                    elif s in name_to_id:
                        fields[key] = str(name_to_id[s])
                    else:
                        fields[key] = ""
                else:
                    fields[key] = ""
        elif ftype == 5:
            if isinstance(val, str):
                fields[key] = int(datetime.now().timestamp() * 1000)
        elif ftype in [17, 15]:
            fields.pop(key, None)

    existing_record = None
    existing_id = None
    if "主表记录ID" in available_fields and main_record_id:
        existing_record = client.find_first_record_by_fields(table_id, {"主表记录ID": main_record_id})
    elif "记录表ID" in available_fields and main_record_id:
        existing_record = client.find_first_record_by_fields(table_id, {"记录表ID": main_record_id})
    else:
        match_fields = {"作品名称": work.get("作品名称", ""), "作者": work.get("作者", "")}
        existing_record = client.find_first_record_by_fields(table_id, match_fields)

    if existing_record:
        existing_id = existing_record.get("record_id")

    # Maintain xhs table field: 是否发布笔记 (default 否, but never overwrite user-set value).
    if "是否发布笔记" in available_fields:
        existing_val = None
        if existing_record:
            existing_val = (existing_record.get("fields", {}) or {}).get("是否发布笔记")
        has_existing = False
        if existing_val is None:
            has_existing = False
        elif isinstance(existing_val, str):
            has_existing = bool(existing_val.strip())
        else:
            # Some API responses may use dict payloads; treat as present.
            has_existing = True

        if not has_existing:
            opt_id = client.resolve_single_select_option_id(table_id, "是否发布笔记", "否")
            fields["是否发布笔记"] = opt_id or "否"

    if existing_id:
        client.update_record_in_table(table_id, existing_id, fields)
        target_id = existing_id
    else:
        target_id = client.create_record_in_table(table_id, fields)

    # Optional attachment sync if target table has this field
    if xhs_path and "小红书笔记初稿" in available_fields:
        file_token = client.upload_file_to_bitable(xhs_path)
        client.update_record_in_table(
            table_id, target_id, {"小红书笔记初稿": [{"file_token": file_token}]}
        )

    # Optional image generation + attachment sync
    if is_image_generation_enabled():
        if _is_image_gen_async():
            _enqueue_image_job(
                {
                    "ts": now_ts(),
                    "provider": "jimeng",
                    "table": "小红书笔记库",
                    "table_id": table_id,
                    "xhs_record_id": target_id,
                    "main_record_id": main_record_id,
                    "work_name": work.get("作品名称", ""),
                    "author": work.get("作者", ""),
                    "prompts": [str(x).strip() for x in (analysis.get("配图提示词", []) or []) if str(x).strip()][
                        :5
                    ],
                    "target_fields": [f"即梦生图{i}" for i in range(1, 6)],
                    "per_field_images": 2,
                }
            )
            return target_id

        prompts = analysis.get("配图提示词", [])
        if not isinstance(prompts, list):
            prompts = []
        prompts = [str(x).strip() for x in prompts if str(x).strip()][:5]
        # 净化所有prompt：强制去除可能引导出文字的内容，末尾追加禁止文字指令
        prompts = [_sanitize_prompt_for_image_gen(p) for p in prompts]
        if prompts:
            prompt_images = []
            for p in prompts:
                try:
                    paths = generate_images_from_prompt(p, n=2)
                except Exception as e:
                    if "50413" in str(e) or "Post Text Risk Not Pass" in str(e):
                        safe_p = _sanitize_image_prompt_for_jimeng(p)
                        safe_p = _sanitize_prompt_for_image_gen(safe_p)  # 二次净化
                        paths = generate_images_from_prompt(safe_p, n=2)
                    else:
                        raise
                # Ensure each prompt has 2 candidates.
                if len(paths) < 2:
                    try:
                        extra_p = _sanitize_prompt_for_image_gen(p)
                        extra = generate_images_from_prompt(extra_p, n=2 - len(paths))
                    except Exception:
                        extra = []
                    paths = (paths + extra)[:2]
                prompt_images.append(paths)

            # Mode A1: per-prompt fields (即梦生图1..即梦生图5), each stores 2 attachments
            jm_prompt_names = [f"即梦生图{i}" for i in range(1, 6)]
            has_jm_per_prompt = all(name in available_fields for name in jm_prompt_names[: len(prompt_images)])

            if has_jm_per_prompt:
                patch = {}
                for idx, paths in enumerate(prompt_images, start=1):
                    tokens = []
                    for pth in paths:
                        token = client.upload_file_to_bitable(pth)
                        tokens.append({"file_token": token})
                    patch[f"即梦生图{idx}"] = tokens
                if patch:
                    client.update_record_in_table(table_id, target_id, patch)
            else:
                # Mode A2: legacy per-prompt fields (生成图片1..生成图片5), each stores 2 attachments
                per_prompt_names = [f"生成图片{i}" for i in range(1, 6)]
                has_per_prompt = all(name in available_fields for name in per_prompt_names[: len(prompt_images)])

            if (not has_jm_per_prompt) and has_per_prompt:
                patch = {}
                for idx, paths in enumerate(prompt_images, start=1):
                    tokens = []
                    for pth in paths:
                        token = client.upload_file_to_bitable(pth)
                        tokens.append({"file_token": token})
                    patch[f"生成图片{idx}"] = tokens
                if patch:
                    client.update_record_in_table(table_id, target_id, patch)
            else:
                # Mode B: flat fields (生成图片1..生成图片10), each stores 1 attachment
                flat_names = [f"生成图片{i}" for i in range(1, 11)]
                has_flat = all(name in available_fields for name in flat_names[: len(prompt_images) * 2])
                if has_flat:
                    patch = {}
                    cursor = 1
                    for paths in prompt_images:
                        for pth in paths:
                            token = client.upload_file_to_bitable(pth)
                            patch[f"生成图片{cursor}"] = [{"file_token": token}]
                            cursor += 1
                    if patch:
                        client.update_record_in_table(table_id, target_id, patch)

    return target_id


def run():
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()
    t0 = time.perf_counter()
    summary = {
        "ts": now_ts(),
        "status": "running",
        "run_date": "",
        "work_name": "",
        "author": "",
        "main_record_id": None,
        "xhs_record_id": None,
        "paths": {},
        "durations_sec": {},
        "errors": [],
    }
    run_date = ""
    work = {}
    analysis = {}
    record_id = None
    xhs_record_id = None
    report_path = ""
    xhs_path = ""
    exp_path = ""

    try:
        t = time.perf_counter()
        work = load_selected_work()
        search_info = search_work_info(work)
        summary["durations_sec"]["select_and_search"] = round(time.perf_counter() - t, 3)

        # Merge search info into work if missing; prefer search for 简介 if more detailed
        for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
            if not work.get(k) and search_info.get(k):
                work[k] = search_info.get(k)
        # 简介优先用搜索到的版本（通常更详细准确）
        clean_intro = search_info.get("剧情简介") or clean_source_synopsis(search_info.get("简介", "")).get("剧情简介", "")
        if clean_intro and len(str(clean_intro)) > len(str(work.get("简介", ""))):
            work["简介"] = clean_intro
            work["剧情简介"] = clean_intro
            work["原始简介"] = search_info.get("原始简介") or search_info.get("简介", "")
            work["非剧情信息"] = search_info.get("非剧情信息", [])
            # 同时标记来源
            if search_info.get("搜索来源链接"):
                work["简介来源"] = search_info["搜索来源链接"]

        # Normalize word count from alternate field names
        if not work.get("字数（万）"):
            for alt in ["字数", "字数（万字）", "字数_万_"]:
                if work.get(alt):
                    work["字数（万）"] = work.get(alt)
                    break

        if os.getenv("DEBUG_FIELDS", "false").strip().lower() in ["1", "true", "yes"]:
            debug_path = os.path.join(PATHS["logs"], "last_work.json")
            with open(debug_path, "w", encoding="utf-8") as f:
                json.dump(work, f, ensure_ascii=False, indent=2)

        t = time.perf_counter()
        analysis = analyze_work(work)
        # Abort on model parse fallback to avoid writing meaningless template data.
        source = (analysis.get("元信息", {}) or {}).get("来源", "")
        if "openai_parse_fallback" in str(source):
            raise RuntimeError(f"模型解析失败，已回退模板，拒绝写入：{source}")
        analysis["配图提示词"] = _build_image_prompts(work, analysis)
        summary["durations_sec"]["analyze"] = round(time.perf_counter() - t, 3)

        t = time.perf_counter()
        report = build_report(work, search_info, analysis)
        xhs_note = build_xhs_note(work, analysis)
        experiment_log = build_experiment_log(work, analysis)

        run_date = get_run_date()
        safe_name = f"{work.get('作品名称','未知作品')}_{work.get('作者','未知作者')}"

        report_path = os.path.join(PATHS["outputs"], "拆解报告", f"{run_date}_{safe_name}_拆解报告.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        xhs_dir = os.path.join(PATHS["outputs"], "小红书笔记_v3", safe_name)
        os.makedirs(xhs_dir, exist_ok=True)
        xhs_path = os.path.join(xhs_dir, f"{work.get('作品名称','未知作品')}-小红书笔记初稿.md")
        with open(xhs_path, "w", encoding="utf-8") as f:
            f.write(xhs_note)

        exp_path = os.path.join(PATHS["outputs"], "实验记录", f"{run_date}_实验记录.md")
        with open(exp_path, "w", encoding="utf-8") as f:
            f.write(experiment_log)
        summary["durations_sec"]["write_files"] = round(time.perf_counter() - t, 3)

        t = time.perf_counter()
        record_id = sync_to_feishu(work, search_info, analysis)
        summary["durations_sec"]["sync_main"] = round(time.perf_counter() - t, 3)

        if record_id:
            try:
                t = time.perf_counter()
                xhs_record_id = sync_xhs_note_table(record_id, work, analysis, xhs_path)
                summary["durations_sec"]["sync_xhs_table"] = round(time.perf_counter() - t, 3)
            except Exception as e:
                err = str(e)
                summary["errors"].append({"stage": "sync_xhs_note_table", "error": err})
                append_jsonl(
                    os.path.join(PATHS["logs"], "sync_errors.jsonl"),
                    {"ts": now_ts(), "stage": "sync_xhs_note_table", "record_id": record_id, "error": err},
                )

            # Avoid duplicate related records on update-only runs
            if not work.get("_existing_main_record"):
                t = time.perf_counter()
                related_ids = sync_related(record_id, work, analysis)
                update_main_links(record_id, related_ids)
                summary["durations_sec"]["sync_related"] = round(time.perf_counter() - t, 3)

        if work.get("_topic_record_id"):
            try:
                mark_work_deconstructed(work.get("_topic_record_id"))
            except Exception as e:
                append_jsonl(
                    os.path.join(PATHS["logs"], "sync_errors.jsonl"),
                    {
                        "ts": now_ts(),
                        "stage": "mark_topic_deconstructed",
                        "topic_record_id": work.get("_topic_record_id"),
                        "error": str(e),
                    },
                )

        # Write local record log for web UI
        append_jsonl(
            os.path.join(PATHS["logs"], "records.jsonl"),
            {
                "ts": now_ts(),
                "run_date": run_date,
                "work_name": work.get("作品名称", ""),
                "author": work.get("作者", ""),
                "record_id": record_id,
                "xhs_record_id": xhs_record_id,
                "report_path": report_path,
                "xhs_path": xhs_path,
                "image_prompts": analysis.get("配图提示词", []),
                "published": False,
            },
        )

        print("完成:")
        print("- 拆解报告:", report_path)
        print("- 小红书笔记:", xhs_path)
        print("- 实验记录:", exp_path)
        if record_id:
            print("- 飞书记录ID:", record_id)
            if xhs_record_id:
                print("- 小红书笔记库记录ID:", xhs_record_id)
        else:
            print("- 飞书同步: 跳过（未配置凭证）")

        summary["status"] = "success"
    except Exception as e:
        summary["status"] = "failed"
        summary["errors"].append({"stage": "run", "error": str(e)})
        raise
    finally:
        summary["run_date"] = run_date
        summary["work_name"] = work.get("作品名称", "") if isinstance(work, dict) else ""
        summary["author"] = work.get("作者", "") if isinstance(work, dict) else ""
        summary["main_record_id"] = record_id
        summary["xhs_record_id"] = xhs_record_id
        summary["paths"] = {"report_path": report_path, "xhs_path": xhs_path, "exp_path": exp_path}
        summary["durations_sec"]["total"] = round(time.perf_counter() - t0, 3)
        summary_path = os.path.join(PATHS["logs"], "run_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    run()
