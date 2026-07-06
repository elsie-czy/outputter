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


def _is_no_female_lead(work, analysis):
    text = " ".join([
        str(work.get("分类", "") or ""),
        str(work.get("取向", "") or ""),
        str((analysis.get("人物设定") or {}).get("女主", "") or ""),
    ])
    return any(k in text for k in ["纯爱", "无女主", "无（纯爱", "BL", "bl"])


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

    scene_text = " ".join([category, intro])
    is_action_genre = any(k in scene_text for k in ["仙侠", "玄幻", "悬疑", "科幻", "末世", "无限流", "战斗"])
    is_ancient = any(k in scene_text for k in ["仙侠", "修真", "古代", "宫廷", "侯门", "朝堂", "江湖"])
    no_female_lead = _is_no_female_lead(work, analysis)
    era_hint = "ancient fantasy era" if is_ancient else "modern era"
    world_hint = (
        "ancient architecture, layered silk robes, moonlight and lantern lighting"
        if is_ancient else
        _join_visual_terms(visual_source, fallback="urban interior and night city lighting", limit=5)
    )

    character_desc = (
        "two male leads, one reserved protagonist, one warm strategic genius"
        if no_female_lead else
        "determined female protagonist and restrained male lead"
    )
    story_anchors = _join_visual_terms(visual_source, fallback="story-specific emotional symbols", limit=8)
    style_bible = _style_bible_for_image_prompts(scene_text, visual_source)
    c1 = _join_visual_terms(conflict.get("第一层", ""), visual_source, fallback="high stakes conflict", limit=5)
    c2 = _join_visual_terms(conflict.get("第二层", ""), visual_source, fallback="emotional tension", limit=5)
    c3 = _join_visual_terms(conflict.get("第三层", ""), visual_source, fallback="final confrontation", limit=5)

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
        f"{anchor} Cover shot: main character half-body close-up portrait, low angle camera, "
        f"foreground blur, dramatic side-lighting, visual symbols: {c1}."
    )
    p2 = (
        f"{anchor} Worldbuilding shot: wide environmental scene, {world_hint}, "
        f"atmospheric depth showing {c2}, cool color palette with rim light."
    )
    if is_action_genre:
        p3 = (
            f"{anchor} Action shot: protagonist in dynamic pose, love interest in background, "
            f"motion lines, hard split lighting, intense moment of {c1}."
        )
        p4 = (
            f"{anchor} Emotional duel: protagonist and love interest face-to-face, "
            f"eye-level medium shot, rain atmosphere, volumetric light, {c3}."
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
        f"{anchor} Group ending: protagonist with allies, emotional release, "
        "morning warm light, shallow depth of field, particles in air."
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


def generate_title_options(work, analysis):
    """基于xhs-writer-skill的5种标题公式生成标题选项"""
    name = work.get("作品名称", "")
    category = work.get("分类", "")
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
        s = re.sub(r"[\s，。、；]", "", str(text))
        return s[:max_len] if s else ""
    
    hook = _extract_keyword(opening)
    pain_point = _extract_keyword(conflict)
    
    # 5种标题公式（来自xhs-writer-skill）
    titles = []
    for t in brief_titles:
        if t not in titles:
            titles.append(t)
    
    # 公式1：痛点型
    if pain_point:
        titles.append(f"{pain_point}？这本{category}给答案")
    else:
        titles.append(f"追{category}总踩雷？先看这本")
    
    # 公式2：爽点型
    titles.append(f"这本{category}爽点太密了")
    
    # 公式3：反差型
    if hook:
        titles.append(f"{hook}，居然写成了爽文")
    else:
        titles.append(f"{name}不是噱头是真上头")
    
    # 公式4：搜索长尾型
    titles.append(f"书荒必看{category}推荐")
    
    # 公式5：互动求投喂型
    titles.append(f"{category}党求投喂同款")
    
    # 使用原有标题模板（如果有）
    original_title = p.get("小红书标题模板", "")
    if original_title and original_title not in titles:
        insert_at = len(brief_titles)
        titles.insert(insert_at, original_title)
    
    return [_compact_mobile(t, 24) for t in titles]


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


def get_title_options(work, analysis):
    """返回备选标题列表（不含最佳标题），供前端选择器使用"""
    try:
        title_options = generate_title_options(work, analysis)
        best_title = _select_best_title(title_options, work)
        return [t for t in title_options if t != best_title][:5]
    except Exception:
        return []


def build_xhs_note(work, analysis, use_formula=True):
    p = analysis["小红书包装"]
    content_brief = _safe_content_brief_for_note(work, analysis)
    cover_hook = content_brief.get("封面钩子", {})
    if not isinstance(cover_hook, dict):
        cover_hook = {}
    tags = p.get("热门标签推荐", [])
    if not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    intro_lines = _mobile_lines(work.get("简介", ""), max_len=36, max_lines=3)
    words = str(work.get("字数（万）") or work.get("字数") or "").strip()
    score = str(work.get("评分", "")).strip()
    finish = str(work.get("完结状态", "")).strip()
    lines = []
    
    # 使用5种标题公式生成标题
    if use_formula:
        title_options = generate_title_options(work, analysis)
        best_title = _select_best_title(title_options, work)
        lines.append(f"【标题】{best_title}")
    else:
        lines.append(f"【标题】{p.get('小红书标题模板', '')}")
    lines.append("")
    
    # 前三行先给结论，避免先铺剧情导致滑走。
    lines.append("先说结论👇")
    lead_lines = _split_packaging_lines(p.get("正文开头模板", ""), max_lines=3, max_len=38)
    if len(lead_lines) < 3:
        lead_lines = _sharp_fallback_lead(content_brief, cover_hook, work, p)
    for marker, text in zip(["✅", "🔥", "📌"], lead_lines[:3]):
        lines.append(f"{marker} {text}")
    lines.append("")
    
    # 情绪钩子（从 analysis 情绪词动态生成）
    import random
    emotion_words = [e for e in analysis.get("情绪触发", []) if e and str(e).strip()]
    if emotion_words:
        ew = _compact_mobile(emotion_words[0], 20)
        lines.append(f"这本真的{ew}😭 刷到就是缘分")
    else:
        lines.append("刷到就是缘分，这本绝了")
    lines.append("")
    structure = _compact_mobile(p.get('正文结构建议', ''), 80)
    if structure:
        lines.append("这本不是靠设定噱头撑着走的，是真有阅读粘性的那种。")
    else:
        lines.append("这本不是靠设定噱头撑着走的，是真有阅读粘性的那种。")
    lines.append("我本来只想看几章，结果直接连着刷下去。")
    lines.append("")
    lines.append("📚 作品速览")
    lines.append(f"- 书名：{work.get('作品名称','')}")
    lines.append(f"- 作者：{work.get('作者','')}")
    if words:
        lines.append(f"- 字数：{words}")
    if score:
        lines.append(f"- 评分：{score}")
    if finish:
        lines.append(f"- 完结状态：{finish}")
    lines.append(f"- 标签：{_compact_mobile(work.get('分类',''), 48)}")
    lines.append("")
    if intro_lines:
        lines.append("🧾 一句话剧情")
        for t in intro_lines:
            lines.append(f"- {t}")
        lines.append("")

    lines.append("✨ 核心亮点")
    lines.append("")
    
    # 聚焦核心卖点（参考xhs-writer-skill：只讲1-2个最稀缺的功能）
    lines.append("🔹 开篇抓人：先抛生存题，再给反转")
    for i, item in enumerate(analysis["开篇套路"][:3], 1):
        lines.append(f"{i}. {_compact_mobile(item, 120)}")
    lines.append("")

    lines.append("🔹 人设不扁平，关系有拉扯感")
    lines.append(f"- 女主：{_compact_mobile(analysis['人物设定']['女主'], 160)}")
    lines.append(f"- 男主：{_compact_mobile(analysis['人物设定']['男主'], 150)}")
    lines.append(f"- 配角：{_compact_mobile(analysis['人物设定']['亮点配角'], 140)}")
    lines.append("")

    lines.append("🔹 冲突是递进的，不是单点吵架")
    lines.append(f"- 第一层：{_compact_mobile(analysis['冲突设计']['第一层'], 150)}")
    lines.append(f"- 第二层：{_compact_mobile(analysis['冲突设计']['第二层'], 150)}")
    lines.append(f"- 第三层：{_compact_mobile(analysis['冲突设计']['第三层'], 150)}")
    lines.append("")

    lines.append("🔹 情绪反馈稳定，容易追更")
    lines.append(f"- 情绪关键词：{_compact_mobile(' / '.join(analysis['情绪触发']), 160)}")
    lines.append(f"- 结构节奏：{_compact_mobile(p.get('正文结构建议', ''), 120)}")
    lines.append("")
    
    # 个人推荐点（从卖点分析动态生成）
    lines.append("🔹 我个人最吃的一点")
    sell_point = analysis.get("卖点分析", {})
    core_sell = _compact_mobile(sell_point.get("核心卖点", ""), 120)
    if core_sell:
        lines.append(core_sell)
    else:
        lines.append(_compact_mobile(p.get("正文开头模板", ""), 120))
    aux_sells = sell_point.get("辅助卖点", [])
    if isinstance(aux_sells, list) and aux_sells:
        lines.append(f"辅助亮点：{_compact_mobile('、'.join(str(s) for s in aux_sells[:2]), 100)}")
    lines.append("")

    lines.append("📝 可抄作业句子（收藏版）")
    for item in analysis["金句"][:3]:
        lines.append(f"- {_compact_mobile(item, 90)}")
    lines.append("")

    lines.append("📖 阅读建议")
    audience = p.get("受众画像关键词", [])
    if not isinstance(audience, list):
        audience = [str(audience)] if audience else []
    audience_str = _compact_mobile("、".join(str(a) for a in audience[:3]), 60)
    category = _compact_mobile(work.get("分类", ""), 20)
    if audience_str:
        lines.append(f"- 适合：{audience_str}")
    else:
        lines.append(f"- 适合：喜欢{category}题材的读者")
    expand = _compact_mobile(p.get("内容扩展方向", ""), 80)
    if expand:
        lines.append(f"- 如果你喜欢{expand}，这本也值得看")
    else:
        lines.append("- 避雷：如果只想看极速爽点，可能会觉得铺垫稍多")
    lines.append("")

    lines.append("💬 我的结论")
    core_sell = _compact_mobile(analysis.get("卖点分析", {}).get("核心卖点", ""), 100)
    potential = _compact_mobile(p.get("爆款潜力评分", ""), 10)
    if core_sell:
        lines.append(f"如果你最近想找一本{core_sell}的文，这本真的可以试。")
    else:
        lines.append("如果你最近书荒想找一本有阅读粘性的文，这本真的可以试。")
    emotion_tail = _compact_mobile('、'.join(analysis.get("情绪触发", [])[:2]), 30)
    if emotion_tail:
        lines.append(f"它不只是爽，更靠{emotion_tail}把人留住。")
    else:
        lines.append("它不是喊口号式的，而是一步步把命运拿回来的过程。")
    lines.append("")
    
    # CTA行动号召（参考xhs-writer-skill：点赞/收藏/关注）
    lines.append("👇 你来选")
    cta = _compact_mobile(p.get("互动话术模板", ""), 46)
    if not cta or any(x in cta for x in ["欢迎评论", "聊聊", "评论区告诉我"]):
        category = _compact_mobile(work.get("分类", ""), 16) or "同款"
        cta = f"你更吃人设拉扯，还是剧情反转？"
        if category:
            cta = f"{category}里你最想被投喂哪本？"
    lines.append(cta)
    lines.append("我会从评论区挑书继续拆。")
    lines.append("")
    
    # 增加收藏引导
    lines.append("📌 觉得有用就收藏一下，下次书荒不迷路！")
    lines.append("")
    
    lines.append("🏷️ 标签")
    lines.append(" ".join(tags))
    # Keep note attachment mobile-friendly; prompts are stored in dedicated Feishu fields.
    return "\n".join(lines)


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
