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


def _mobile_lines(text, max_len=36, max_lines=3):
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    if not s:
        return []
    parts = [x.strip() for x in re.split(r"[。；;！!？?]", s) if x.strip()]
    out = []
    for p in parts:
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


def _build_image_prompts(work, analysis):
    category = str(work.get("分类", "") or "")
    intro = str(work.get("简介", "") or "")
    lead_name = _extract_lead_name_from_intro(intro)
    # Use source-summary grounding first; avoid over-trusting hallucinated role details.
    heroine_desc = _clip(lead_name or analysis.get("人物设定", {}).get("女主", "") or "female protagonist", 16)
    hero_desc = _clip(analysis.get("人物设定", {}).get("男主", "") or "male lead", 16)
    support_desc = _clip(analysis.get("人物设定", {}).get("亮点配角", "") or "sect members", 14)
    conflict = analysis.get("冲突设计", {})

    scene_text = " ".join([category, intro, heroine_desc, hero_desc, support_desc])
    is_action_genre = any(k in scene_text for k in ["仙侠", "玄幻", "悬疑", "科幻", "末世", "无限流", "战斗"])
    is_ancient = any(k in scene_text for k in ["仙侠", "修真", "古代", "宫廷", "侯门", "朝堂", "江湖"])
    era_hint = "ancient fantasy era" if is_ancient else "modern era"
    world_hint = "ancient architecture, layered robes, moonlight and lantern lighting" if is_ancient else "urban interior and night city lighting, realistic props"

    c1 = _clip(conflict.get("第一层", "high stakes conflict"), 28)
    c2 = _clip(conflict.get("第二层", "relationship conflict"), 28)
    c3 = _clip(conflict.get("第三层", "final confrontation"), 28)

    anchor = (
        "Xiaohongshu visual, vertical 3:4, anime illustration, cinematic lighting, high detail. "
        f"Story era: {era_hint}. "
        f"Fixed roles: female lead (woman, {heroine_desc or 'calm and determined'}), "
        f"male lead (man, {hero_desc or 'cold and restrained'}), "
        f"supporting role ({support_desc or 'key trigger character'}). "
        "Ground only to official synopsis and listed genre; avoid adding new names or settings. "
        "Gender must stay consistent. Wardrobe and props must match one era only. "
        "No text, no Chinese characters, no letters, no subtitle, no logo, no watermark. "
        "Image must be text-free."
    )

    p1 = (
        f"{anchor} Cover shot: female lead half-body close-up, low angle camera, foreground blur, "
        f"high contrast lighting, conflict cue: {c1}, keep top 30 percent clean composition."
    )
    p2 = (
        f"{anchor} Worldbuilding shot: wide shot, environmental storytelling, {world_hint}, "
        f"prop-based tension showing {c2}, cool gray-blue palette with rim light."
    )
    if is_action_genre:
        p3 = (
            f"{anchor} Action shot: female lead in motion, male lead in background opposition, "
            f"dynamic motion lines and debris, hard split lighting, conflict cue: {c1}."
        )
        p4 = (
            f"{anchor} Emotional duel shot: female lead and male lead face-off, eye-level close-up, "
            f"rainy atmosphere and volumetric light, conflict cue: {c3}."
        )
    else:
        p3 = (
            f"{anchor} Relationship shot: female lead and male lead in the same frame but distant, "
            f"medium shot, warm indoor lighting, daily-life props, conflict cue: {c1}."
        )
        p4 = (
            f"{anchor} Emotional shot: single-character close-up of female lead near window light, "
            f"soft focus and low saturation, conflict cue: {c3}."
        )
    p5 = (
        f"{anchor} Ending shot: group composition with female lead and allies, emotional release with residual tension, "
        "morning warm light, shallow depth of field, particles in foreground, suitable as final carousel page."
    )
    return [p1, p2, p3, p4, p5]


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
    
    # 公式1：痛点+解决方案
    if pain_point:
        titles.append(f"{pain_point}？这本{category}把答案写透了")
    else:
        titles.append(f"追{category}总踩雷？这本真的不一样")
    
    # 公式2：提问式
    titles.append(f"有没有那种看完就走不出来的{category}？")
    
    # 公式3：发现式
    if hook:
        titles.append(f"我发现了个宝藏！{hook}的{category}")
    else:
        titles.append(f"我发现了个宝藏！{name}真的绝了")
    
    # 公式4：热点词
    titles.append(f"刷到就是赚到！这本{category}我连刷了三遍")
    
    # 公式5：身份共鸣
    titles.append(f"{category}党必备！{name}把{emotion}拉满了")
    
    # 使用原有标题模板（如果有）
    original_title = p.get("小红书标题模板", "")
    if original_title and original_title not in titles:
        titles.insert(0, original_title)
    
    return titles


def _select_best_title(titles, work):
    """选择最佳标题（优先选择包含作品名的标题）"""
    name = work.get("作品名称", "")
    for t in titles:
        if name and name in t:
            return t
    return titles[0] if titles else ""


def build_xhs_note(work, analysis, use_formula=True):
    p = analysis["小红书包装"]
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
        lines.append(f"【备选标题】")
        for i, t in enumerate(title_options[:5], 1):
            if t != best_title:
                lines.append(f"  {i}. {t}")
    else:
        lines.append(f"【标题】{p.get('小红书标题模板', '')}")
    lines.append("")
    
    # 痛点共鸣开头（参考xhs-writer-skill方法论）
    lines.append("姐妹们我先说结论👇")
    lines.append(f"✨ {_compact_mobile(p.get('正文开头模板', ''), 120)}")
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
        lines.append(structure)
    else:
        lines.append("这本不是靠设定噱头撑着走的，是真有阅读粘性的那种。")
    lines.append("我本来只想看几章，结果直接连着刷下去。")
    lines.append("")
    lines.append("📚 作品速览")
    lines.append(f"- 书名：{work.get('作品名称','')}")
    lines.append(f"- 作者：{work.get('作者','')}")
    lines.append(f"- 平台：{work.get('平台','')}")
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
    lines.append(_compact_mobile(p.get("互动话术模板", "你最吃哪类开篇？评论区告诉我"), 120))
    lines.append("我也想抄你们的书单，评论区互相投喂！")
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
        if prompts:
            prompt_images = []
            for p in prompts:
                try:
                    paths = generate_images_from_prompt(p, n=2)
                except Exception as e:
                    if "50413" in str(e) or "Post Text Risk Not Pass" in str(e):
                        safe_p = _sanitize_image_prompt_for_jimeng(p)
                        paths = generate_images_from_prompt(safe_p, n=2)
                    else:
                        raise
                # Ensure each prompt has 2 candidates.
                if len(paths) < 2:
                    try:
                        extra = generate_images_from_prompt(p, n=2 - len(paths))
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

        # Merge search info into work if missing
        for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
            if not work.get(k) and search_info.get(k):
                work[k] = search_info.get(k)

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
