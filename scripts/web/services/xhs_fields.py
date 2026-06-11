import glob
import os

from scripts.config import PATHS


def compute_xhs_missing(fields):
    prompt_missing_idx = []
    image_missing_idx = []
    for i in range(1, 6):
        if not str(fields.get(f"生成配图提示词{i}", "")).strip():
            prompt_missing_idx.append(i)
    for i in range(1, 6):
        v = fields.get(f"即梦生图{i}", [])
        ok = isinstance(v, list) and len(v) >= 1
        if not ok:
            image_missing_idx.append(i)
    mdv = fields.get("小红书笔记初稿", [])
    md_ok = isinstance(mdv, list) and len(mdv) >= 1
    missing_parts = []
    if prompt_missing_idx:
        missing_parts.append("提示词" + "/".join([str(i) for i in prompt_missing_idx]))
    if image_missing_idx:
        missing_parts.append("图片" + "/".join([str(i) for i in image_missing_idx]))
    if not md_ok:
        missing_parts.append("MD附件")
    return {
        "prompt_ok": 5 - len(prompt_missing_idx),
        "image_ok": 5 - len(image_missing_idx),
        "md_ok": 1 if md_ok else 0,
        "prompt_missing_idx": prompt_missing_idx,
        "image_missing_idx": image_missing_idx,
        "missing_text": ("；".join(missing_parts) if missing_parts else "无"),
    }


def find_local_xhs_md(work_name, author):
    work_name = str(work_name or "").strip()
    author = str(author or "").strip()
    if not work_name:
        return ""
    exact = os.path.join(
        PATHS["outputs"],
        "小红书笔记_v3",
        f"{work_name}_{author}",
        f"{work_name}-小红书笔记初稿.md",
    )
    if os.path.exists(exact):
        return exact
    pattern = os.path.join(
        PATHS["outputs"],
        "小红书笔记_v3",
        f"{work_name}_*",
        f"{work_name}-小红书笔记初稿.md",
    )
    matches = glob.glob(pattern)
    if matches:
        matches.sort(reverse=True)
        return matches[0]
    return ""


def xhs_note_from_fields(fields):
    title = str(fields.get("小红书标题模板", "")).strip()
    opening = str(fields.get("正文开头模板", "")).strip()
    structure = str(fields.get("正文结构建议", "")).strip()
    interact = str(fields.get("互动话术模板", "")).strip()
    tags = fields.get("热门标签推荐", [])
    if not isinstance(tags, list):
        tags = [str(tags)] if str(tags).strip() else []
    lines = []
    if title:
        lines.append(title)
        lines.append("")
    if opening:
        lines.append(opening)
    if structure:
        lines.append("")
        lines.append("结构建议：" + structure)
    if interact:
        lines.append("")
        lines.append("互动话术：" + interact)
    if tags:
        lines.append("")
        lines.append("标签：" + " ".join([str(x).strip() for x in tags if str(x).strip()]))
    return "\n".join(lines).strip()
