"""
HTML 卡片生成模块 —— 替代 AI 生图，用程序化排版输出小红书图文卡片。
策略切换：.env 中 IMAGE_GEN_STRATEGY=html_card 时启用。
"""
import os
import re
import json
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
    style: str = "warm",
    n: int = 3,
    output_dir: str = None,
) -> list[str]:
    """
    从拆解笔记内容生成 HTML 卡片并截图。

    :param note_content: 字典，含 title / body / tags / lead
    :param style: warm | anthropic | notion | minimal | morandi
    :param n: 期望生成图片张数（会根据内容自动调整）
    :param output_dir: PNG 输出目录，默认 temp/html_cards/
    :return: [png_path, ...]
    """
    if not _PLAYWRIGHT_OK:
        raise RuntimeError("playwright 未安装，请运行：python -m playwright install chromium")

    out_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. 规划卡片结构
    cards = _plan_cards(note_content, style, n)

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
def _plan_cards(note: dict, style: str, n: int) -> list[dict]:
    """
    将笔记内容拆分为多张卡片数据。
    返回 [{"card_type":"cover", ...}, {"card_type":"content", ...}, ...]
    """
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
        cards.append({
            "card_type": "content",
            "section_tag": f"第 {idx+1} 点",
            "section_title": point_group.get("heading", f"要点 {idx+1}"),
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


# ── Playwright 截图 ──────────────────────────────────────────────────
def _screenshot_batch(html_paths: list[str], output_dir: str) -> list[str]:
    png_paths = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for html_path in html_paths:
            png_path = _screenshot_one(browser, html_path, output_dir)
            if png_path:
                png_paths.append(png_path)
        browser.close()
    return png_paths


def _screenshot_one(browser, html_path: str, output_dir: str) -> str:
    base = Path(html_path).stem
    png_path = str(Path(output_dir) / f"{base}.png")
    page = browser.new_page(viewport={"width": 1080, "height": 1440})
    file_url = "file://" + html_path
    page.goto(file_url, wait_until="networkidle", timeout=15000)
    try:
        page.wait_for_function("document.fonts.ready", timeout=5000)
    except Exception:
        pass
    page.screenshot(path=png_path, full_page=False)
    page.close()
    return png_path


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
