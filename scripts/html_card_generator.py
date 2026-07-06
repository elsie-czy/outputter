"""
HTML 卡片生成模块 —— 替代 AI 生图，用程序化排版输出小红书图文卡片。
策略切换：.env 中 IMAGE_GEN_STRATEGY=html_card 时启用。
"""
import os
import re
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

# Playwright 延迟导入，避免无浏览器环境报错
try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_OK = True
except Exception:
    _PLAYWRIGHT_OK = False

# ── 路径 ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "scripts" / "xhs_card_assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
FONT_ROOT = str((ASSETS_DIR / "fonts").resolve())
OUTPUT_DIR = BASE_DIR / "temp" / "html_cards"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


# ── 公开入口 ──────────────────────────────────────────────────────────
def generate_cards_from_note(
    note_content: dict,
    style: str = "auto",
    n: int = 3,
    output_dir: str = None,
    content_brief: dict = None,
) -> list[str]:
    """
    从拆解笔记内容生成 HTML 卡片并截图。

    :param note_content: 字典，含 title / body / tags / lead
    :param style: warm | anthropic | notion | minimal | morandi | auto
                    auto = 根据笔记内容自动匹配最合适风格
    :param n: 期望生成图片张数（会根据内容自动调整）
    :param output_dir: PNG 输出目录，默认 temp/html_cards/
    :param content_brief: 可选内容简报，优先按 图文页结构 规划卡片
    :return: [png_path, ...]
    """
    # style="auto" → 根据内容自动匹配
    if style == "auto":
        style = auto_match_style(note_content)

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 规划卡片结构
    cards = _plan_cards(note_content, style, n, content_brief=content_brief)
    errors = _validate_cards(cards)
    if errors:
        raise ValueError("card plan invalid: " + "; ".join(errors))
    _write_card_plan(cards, out_dir)

    # 2. 渲染 HTML
    html_paths = []
    for i, card in enumerate(cards):
        html_path = out_dir / f"xhs_card_{i+1:02d}.html"
        _render_html(card, style, html_path, len(cards))
        html_paths.append(str(html_path))

    # 3. Playwright 截图
    png_paths = _screenshot_batch(html_paths, str(out_dir))

    return png_paths


# ── 卡片规划 ─────────────────────────────────────────────────────────
def _plan_cards(note: dict, style: str, n: int, content_brief: dict = None) -> list[dict]:
    """
    将笔记内容拆分为多张卡片数据。
    返回 [{"card_type":"cover", ...}, {"card_type":"content", ...}, ...]
    """
    if isinstance(content_brief, dict) and content_brief.get("图文页结构"):
        brief_cards = _plan_cards_from_brief(note, style, n, content_brief)
        if brief_cards:
            return brief_cards

    title = note.get("title", "小红书笔记")
    body = note.get("body", "")
    tags = note.get("tags", [])
    lead = note.get("lead", "")

    # 清理 body：去掉已有的标签行、话题行
    clean_body = _strip_tags_and_topics(body)
    points = _extract_points(clean_body, max_per_card=3)

    total = 1 + len(points) + 1  # 封面 + 内容卡 + 总结
    cards = []

    # 封面卡
    cards.append({
        "card_type": "cover",
        "title": title,
        "subtitle": lead[:120] if lead else clean_body[:120],
        "category": _pick_category(tags),
        "decoration_emoji": _pick_emoji(tags, style),
        "page_num": "01",
        "total_pages": f"{total:02d}",
    })

    # 内容卡
    for idx, point_group in enumerate(points):
        section_title = str(point_group.get("heading") or "").strip() or f"要点 {idx+1}"
        cards.append({
            "card_type": "content",
            "section_tag": f"第 {idx+1} 点",
            "section_title": section_title,
            "points": point_group.get("items", []),
            "page_num": f"{idx+2:02d}",
            "total_pages": f"{total:02d}",
        })

    # 总结卡
    takeaways = [p.get("heading", "") for p in points if p.get("heading")]
    if not takeaways:
        takeaways = [item["text"] for group in points for item in group.get("items", [])][:3]
    cards.append({
        "card_type": "summary",
        "section_tag": "总结",
        "summary_title": "一文总结",
        "takeaways": takeaways[:3],
        "cta": "你有什么想法？评论区聊聊 →",
        "tags": " ".join(["#" + t for t in tags[:8]]) if tags else "",
        "page_num": f"{total:02d}",
        "total_pages": f"{total:02d}",
    })

    return cards


def _plan_cards_from_brief(note: dict, style: str, n: int, content_brief: dict) -> list[dict]:
    brief_pages = _normalize_brief_pages(content_brief.get("图文页结构", []))
    if not brief_pages:
        return []

    title = str(note.get("title") or "").strip() or _brief_cover_title(content_brief) or "小红书笔记"
    body = note.get("body", "")
    tags = note.get("tags", [])
    lead = note.get("lead", "")
    cover_hook = content_brief.get("封面钩子", {})
    if not isinstance(cover_hook, dict):
        cover_hook = {}

    content_pages = [
        page for page in brief_pages
        if page["role"] not in {"cover", "summary"} and page["title"]
    ]
    if not content_pages:
        content_pages = [page for page in brief_pages if page["title"]]
    target_total = max(3, min(int(n or 3), len(content_pages) + 2, 7))
    content_slots = max(1, target_total - 2)
    selected_pages = content_pages[:content_slots]
    total = 1 + len(selected_pages) + 1
    evidence = _as_clean_list(content_brief.get("证据素材", []))
    fallback_points = _extract_points(_strip_tags_and_topics(body), max_per_card=3)

    cards = [{
        "card_type": "cover",
        "plan_source": "content_brief",
        "title": _brief_cover_title(content_brief) or title,
        "subtitle": (
            cover_hook.get("副标题")
            or content_brief.get("核心痛点")
            or lead
            or _strip_tags_and_topics(body)[:120]
        )[:120],
        "message": _brief_message(content_brief, cover_hook, "cover"),
        "category": _pick_category(tags),
        "decoration_emoji": _pick_emoji(tags, style),
        "page_num": "01",
        "total_pages": f"{total:02d}",
    }]

    for idx, page in enumerate(selected_pages):
        page_title = page["title"]
        if page["role"] in {"problem", "insight", "proof", "summary"}:
            role = page["role"]
        else:
            role = _infer_brief_page_role(page_title, idx, len(selected_pages))
        points = _brief_points_for_role(content_brief, role, page_title, evidence)
        if not points:
            fallback = fallback_points[min(idx, len(fallback_points) - 1)] if fallback_points else {}
            points = fallback.get("items", [])[:3]
        message = _points_to_message(points) or page_title
        cards.append({
            "card_type": "content",
            "plan_source": "content_brief",
            "page_role": role,
            "section_tag": _role_label(role, idx),
            "section_title": page_title[:32],
            "message": message,
            "points": points[:3],
            "page_num": f"{idx+2:02d}",
            "total_pages": f"{total:02d}",
        })

    takeaways = [
        content_brief.get("读者收益", ""),
        cover_hook.get("点击理由", ""),
        "按图文页结构保存，方便复盘和二次改稿。",
    ]
    takeaways = [str(x).strip() for x in takeaways if str(x).strip()]
    if not takeaways:
        takeaways = [page["title"] for page in selected_pages[:3]]
    cards.append({
        "card_type": "summary",
        "plan_source": "content_brief",
        "section_tag": "总结",
        "summary_title": "一文总结",
        "message": " / ".join(takeaways[:3]),
        "takeaways": takeaways[:3],
        "cta": note.get("cta") or "你有什么想法？评论区聊聊 →",
        "tags": " ".join(["#" + str(t).lstrip("#") for t in tags[:8]]) if tags else "",
        "page_num": f"{total:02d}",
        "total_pages": f"{total:02d}",
    })
    return cards


def _normalize_brief_pages(page_structure) -> list[dict]:
    if not isinstance(page_structure, list):
        page_structure = [page_structure] if page_structure else []
    pages = []
    for idx, raw in enumerate(page_structure):
        if isinstance(raw, dict):
            title = str(
                raw.get("title")
                or raw.get("message")
                or raw.get("section_title")
                or raw.get("role")
                or ""
            ).strip()
            role = str(raw.get("role") or "").strip().lower()
        else:
            title = str(raw or "").strip()
            role = ""
        if not title:
            continue
        inferred = role or _infer_brief_page_role(title, idx, len(page_structure))
        if any(k in title for k in ["封面", "主标题", "钩子"]) or inferred == "cover":
            inferred = "cover"
        elif any(k in title for k in ["总结", "收藏", "结尾", "互动"]) or inferred == "summary":
            inferred = "summary"
        pages.append({"title": title, "role": inferred})
    return pages


def _brief_cover_title(content_brief: dict) -> str:
    cover_hook = content_brief.get("封面钩子", {})
    if not isinstance(cover_hook, dict):
        cover_hook = {}
    return str(cover_hook.get("主标题") or "").strip()


def _brief_message(content_brief: dict, cover_hook: dict, role: str) -> str:
    if role == "cover":
        parts = [
            content_brief.get("核心痛点", ""),
            content_brief.get("读者收益", ""),
            cover_hook.get("点击理由", ""),
        ]
        return " / ".join([str(x).strip() for x in parts if str(x).strip()])[:180]
    return ""


def _infer_brief_page_role(page_title: str, idx: int, total: int) -> str:
    text = str(page_title)
    if idx == 0 or any(k in text for k in ["痛点", "问题", "开头", "提问"]):
        return "problem"
    if any(k in text for k in ["洞察", "亮点", "看点", "钩子", "人设", "冲突"]):
        return "insight"
    if any(k in text for k in ["证据", "素材", "案例", "剧情", "速览"]):
        return "proof"
    if idx == total - 1 or any(k in text for k in ["总结", "收藏", "建议"]):
        return "summary"
    return "insight"


def _role_label(role: str, idx: int) -> str:
    labels = {
        "problem": "痛点",
        "insight": "洞察",
        "proof": "证据",
        "summary": "总结",
    }
    return labels.get(role, f"第 {idx+1} 点")


def _brief_points_for_role(content_brief: dict, role: str, page_title: str, evidence: list[str]) -> list[dict]:
    if role == "problem":
        items = [content_brief.get("核心痛点", ""), content_brief.get("读者收益", "")]
        emoji = "🎯"
    elif role == "proof":
        items = evidence[:3]
        emoji = "🔍"
    elif role == "summary":
        items = [content_brief.get("读者收益", ""), "收藏这套拆解结构，下次选书先看钩子和冲突。"]
        emoji = "✅"
    else:
        hook = content_brief.get("封面钩子", {})
        if not isinstance(hook, dict):
            hook = {}
        items = [page_title, hook.get("点击理由", ""), content_brief.get("读者收益", "")]
        emoji = "💡"
    return [{"emoji": emoji, "text": str(x).strip()[:80]} for x in items if str(x).strip()][:3]


def _as_clean_list(value) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value:
        items = [value]
    else:
        items = []
    return [str(x).strip() for x in items if str(x).strip()]


def _points_to_message(points: list[dict]) -> str:
    return " / ".join([str(p.get("text", "")).strip() for p in points if str(p.get("text", "")).strip()])[:180]


def _validate_cards(cards: list[dict]) -> list[str]:
    errors = []
    if not isinstance(cards, list) or not cards:
        return ["card plan is empty"]
    if len(cards) < 2 or len(cards) > 7:
        errors.append(f"页数不合理: {len(cards)}")

    for idx, card in enumerate(cards, 1):
        card_type = card.get("card_type", "")
        title = ""
        if card_type == "cover":
            title = card.get("title", "")
        elif card_type == "summary":
            title = card.get("summary_title", "")
        else:
            title = card.get("section_title", "")
        title = str(title).strip()
        if not title:
            errors.append(f"第{idx}页标题为空")
        if len(title) > 48:
            errors.append(f"第{idx}页标题过长")

        message = str(card.get("message") or card.get("subtitle") or "").strip()
        if card_type == "content" and not message:
            message = _points_to_message(card.get("points", []))
        if card_type == "summary" and not message:
            message = " / ".join([str(x).strip() for x in card.get("takeaways", []) if str(x).strip()])
        if not message:
            errors.append(f"第{idx}页 message 为空")

        points = card.get("points", [])
        if isinstance(points, list) and len(points) > 3:
            errors.append(f"第{idx}页要点超过3个")
    return errors


def _write_card_plan(cards: list[dict], out_dir: Path):
    plan_path = out_dir / "card_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cards": cards,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _extract_points(body: str, max_per_card: int = 3) -> list[dict]:
    """
    从正文提取要点分组，每组对应一张内容卡。
    优先按【】、数字.、emoji 分段落。
    """
    # 按换行分段
    paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
    groups = []
    current_group = {"heading": "", "items": []}

    emoji_leaders = set("🔥💡✅📌💫🌟⭐🎯📍🏷️📝✏️🔖🏆🎉💬👀🔍")

    for para in paragraphs:
        # 如果是标题行（含【】或过长）
        if re.match(r"^[【\[].+[】\]]", para) or (len(para) < 30 and "：" not in para and "。" not in para):
            if current_group["items"]:
                groups.append(current_group)
            current_group = {"heading": para, "items": []}
            continue

        # 普通内容行 → 作为 point
        emoji = ""
        if para and para[0] in emoji_leaders:
            emoji = para[0]
            para = para[1:].strip()
        if not emoji:
            emoji = "🔥"

        text = para[:80]  # 每张卡片内每条最多80字
        current_group["items"].append({"emoji": emoji, "text": text})

        if len(current_group["items"]) >= max_per_card:
            if current_group["items"]:
                groups.append(current_group)
            current_group = {"heading": "", "items": []}

    if current_group["items"]:
        groups.append(current_group)

    # 至少保证有一组
    if not groups:
        groups.append({"heading": "精彩看点", "items": [
            {"emoji": "🔥", "text": body[:80] or "精彩内容即将呈现"},
        ]})

    return groups[:5]  # 最多5组内容卡


def _strip_tags_and_topics(text: str) -> str:
    lines = text.split("\n")
    result = [l for l in lines if not (l.strip().startswith("#") or l.strip().startswith("@"))]
    return "\n".join(result).strip()


def _pick_category(tags: list) -> str:
    mapping = {
        "甜宠": "甜宠推荐", "虐恋": "虐恋情深", "豪门": "豪门世家",
        "校园": "校园甜恋", "穿越": "穿越时空", "宫斗": "宫斗宅斗",
        "职场": "职场成长", "美食": "美食分享", "穿搭": "穿搭灵感",
        "情感": "情感语录", "书评": "书评笔记",
    }
    for tag in tags:
        for k, v in mapping.items():
            if k in tag:
                return v
    return tags[0] if tags else "好书推荐"


def _pick_emoji(tags: list, style: str) -> str:
    if style == "warm":
        return "🧸"
    return "✨"


# ── HTML 渲染 ─────────────────────────────────────────────────────────
def _render_html(card: dict, style: str, out_path: Path, total: int):
    template_name = f"{style}.html"
    if not (TEMPLATES_DIR / template_name).exists():
        template_name = "warm.html"  # fallback

    tpl = _env.get_template(template_name)
    # card dict 已含 total_pages / page_num，无需重复传
    html = tpl.render(font_root=FONT_ROOT, **card)
    out_path.write_text(html, encoding="utf-8")


# ── HTML 截图 ────────────────────────────────────────────────────────
def _screenshot_batch(html_paths: list[str], output_dir: str) -> list[str]:
    if not _PLAYWRIGHT_OK:
        return _screenshot_batch_with_chromium_cli(html_paths, output_dir)

    png_paths = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for html_path in html_paths:
                png_path = _screenshot_one(browser, html_path, output_dir)
                if png_path:
                    png_paths.append(png_path)
            browser.close()
        return png_paths
    except Exception as exc:
        try:
            return _screenshot_batch_with_chromium_cli(html_paths, output_dir)
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Playwright 截图失败: {exc}; Chromium CLI fallback 也失败: {fallback_exc}"
            ) from fallback_exc


def _screenshot_one(browser, html_path: str, output_dir: str) -> str:
    base = Path(html_path).stem
    png_path = str(Path(output_dir) / f"{base}.png")
    page = browser.new_page(viewport={"width": 1080, "height": 1440})
    file_url = Path(html_path).resolve().as_uri()
    page.goto(file_url, wait_until="networkidle", timeout=15000)
    try:
        page.wait_for_function("document.fonts.ready", timeout=5000)
    except Exception:
        pass
    page.screenshot(path=png_path, full_page=False)
    page.close()
    return png_path


def _find_chromium_binary() -> str:
    candidates = [
        os.getenv("CHROMIUM_BIN", "").strip(),
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if os.path.exists(candidate):
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return ""


def _screenshot_batch_with_chromium_cli(html_paths: list[str], output_dir: str) -> list[str]:
    chromium = _find_chromium_binary()
    if not chromium:
        raise RuntimeError("未找到 Chromium。请安装系统 chromium，或安装 playwright/chromium。")

    png_paths = []
    for html_path in html_paths:
        base = Path(html_path).stem
        png_path = str(Path(output_dir) / f"{base}.png")
        cmd = [
            chromium,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            "--window-size=1080,1440",
            f"--screenshot={png_path}",
            Path(html_path).resolve().as_uri(),
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Chromium 截图失败: {exc.stderr.strip() or exc.stdout.strip()}") from exc
        if os.path.exists(png_path):
            png_paths.append(png_path)
    return png_paths


# ── 笔记内容解析 ────────────────────────────────────────────────────
def parse_note_content(raw_note: str) -> dict:
    """
    从 deconstruct_daily.py 输出的笔记正文解析出结构化字段。
    兼容现有 note_content 格式。
    """
    result = {"title": "", "body": "", "tags": [], "lead": ""}

    lines = raw_note.split("\n")
    in_body = False
    body_lines = []

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 标题
        if s.startswith("#") and not in_body:
            result["title"] = s.lstrip("#").strip()
            continue

        # 标签行
        if re.search(r"#[\w\u4e00-\u9fa5]", s):
            tags = re.findall(r"#([\w\u4e00-\u9fa5]+)", s)
            result["tags"].extend(tags)
            continue

        # lead / 导语
        if "导语" in s or "lead" in s.lower():
            result["lead"] = s.replace("导语：", "").replace("导语:", "").strip()
            in_body = True
            continue

        body_lines.append(s)
        in_body = True

    result["body"] = "\n".join(body_lines[:600])  # 限制长度
    if not result["title"]:
        result["title"] = body_lines[0][:40] if body_lines else "推荐好书"
    if not result["tags"]:
        result["tags"] = ["好书推荐", "书评", "小红书读书"]

    return result


# ── 风格自动匹配 ────────────────────────────────────────────────
def auto_match_style(note_content: dict) -> str:
    """
    根据笔记内容自动匹配最合适的卡片风格。
    优先级：关键词命中 → 默认 warm。
    """
    title = note_content.get('title', '')
    body  = note_content.get('body', '')
    tags  = note_content.get('tags', [])
    lead  = note_content.get('lead', '')

    combined = (title + lead + body).lower()
    tag_str  = ' '.join(tags).lower()

    # 优先级从高到低依次判断

    # 1. 科技 / AI / 编程 / 数码 → anthropic（杂志编辑感、专业）
    kw_anthropic = [
        'ai', '人工智能', '大模型', 'gpt', 'claude', '编程', '代码',
        '数码', '手机', '电脑', '产品', '科技', '互联网', '算法', '机器学习',
        '深度学习', '数据分析', '职场干货', '效率工具', 'notion', 'obsidian',
    ]
    if any(kw in combined or kw in tag_str for kw in kw_anthropic):
        return 'anthropic'

    # 2. 穿搭 / 美食 / 家居 / 好物 / 护肤 / 旅行 → morandi（高级感、低饱和）
    kw_morandi = [
        '穿搭', '美食', '家居', '好物', '护肤', '旅行', '探店',
        '装修', '婚礼', '情感', 'OOTD', '穿搭灵感', '日常穿搭',
        '早午餐', '下午茶', '探店', '买手店', '周末去哪儿',
    ]
    if any(kw in combined or kw in tag_str for kw in kw_morandi):
        return 'morandi'

    # 3. 职场 / 成长 / 干货 / 学习 / 书评 → notion（结构化、可读性强）
    kw_notion = [
        '职场', '成长', '干货', '学习', '书评', '读书', '笔记',
        '方法', '技巧', '攻略', '指南', '总结', '复盘', '计划',
        '时间管理', '自律', '提升', '认知', '思维', '习惯',
    ]
    if any(kw in combined or kw in tag_str for kw in kw_notion):
        return 'notion'

    # 4. 豪门 / 虐恋 / 宫斗 / 复仇 / 强取豪夺 → morandi（质感、高级感）
    kw_morandi_drama = [
        '豪门', '虐恋', '宫斗', '复仇', '强取豪夺', '失忆', '替身',
        '浪子回头', '追妻火葬场', '带球跑', '真假千金', '重生之',
        '权谋', '宅斗', '商战',
    ]
    if any(kw in combined or kw in tag_str for kw in kw_morandi_drama):
        return 'morandi'

    # 5. 甜宠 / 校园 / 言情 / 日常 → warm（原生小红书感、暖色生活风）
    kw_warm = [
        '甜宠', '校园', '言情', '日常', '浪子回头', '宠妻',
        '萌宝', '双向奔赴', '青梅竹马', '暗恋', '破镜重圆',
        '先婚后爱', '契约婚姻',
    ]
    if any(kw in combined or kw in tag_str for kw in kw_warm):
        return 'warm'

    # 默认
    return 'warm'


def get_style_description(style: str) -> str:
    """返回风格的中文描述，用于 UI 展示。"""
    desc = {
        'warm':     '暖色生活风 —— 原生小红书感，适合甜宠/言情/日常',
        'notion':   '笔记学习风 —— 结构化条理清晰，适合职场/干货/书评',
        'anthropic': '杂志编辑风 —— 专业高级感，适合科技/AI/产品',
        'minimal':  '极简黑白风 —— 克制高级感，适合极简/设计/艺术',
        'morandi':  '莫兰迪低饱和 —— 温柔质感，适合穿搭/美食/豪门虐恋',
        'auto':     '自动匹配 —— 根据笔记内容智能选择最合适风格',
    }
    return desc.get(style, style)
