import argparse
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.deconstruct_daily import _build_image_prompts, build_xhs_note
from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config


def _mobile_trim(text, n=56):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


def _lead_name_from_intro(intro):
    s = str(intro or "")
    m = re.search(r"([\u4e00-\u9fa5]{2,4})因", s)
    if m:
        name = m.group(1)
        for prefix in ["情感博主", "博主", "女主", "主角"]:
            if name.startswith(prefix):
                name = name.replace(prefix, "")
        if len(name) > 3:
            name = name[-2:]
        return name
    return ""


def _build_grounded_analysis(work):
    intro = str(work.get("简介", "") or "")
    lead = _lead_name_from_intro(intro)
    analysis = {
        "开篇套路": [
            "开局给出高压处境，主角先保命再破局",
            "连续反转，把'恋爱脑剧情'改写成'自救剧情'",
            "群像联动，宗门成员逐个觉醒形成爽点",
        ],
        "人物设定": {
            "女主": f"{lead}，清醒强行动力，目标是改命续命" if lead else "清醒强行动力的大女主",
            "男主": "克制理性，与女主形成价值观对照",
            "亮点配角": "宗门群像：大师兄/二师姐/小师妹各有觉醒线",
        },
        "冲突设计": {
            "第一层": "生存冲突：不完成拯救任务就会被系统惩罚",
            "第二层": "关系冲突：宗门众人深陷情劫，女主逆向拆局",
            "第三层": "命运冲突：女主要打破既定祭天剧本",
        },
        "情绪触发": ["爽感", "反转", "代入", "群像治愈"],
        "金句": [
            "不是修无情道，是先把命运握回手里。",
            "清醒不是冷漠，是不把自己交给错误叙事。",
            "先自救，再谈爱与被爱。",
        ],
        "小红书包装": {
            "小红书标题模板": f"{work.get('作品名称','这本修真文')}：把恋爱脑剧情改写成大女主自救，越看越上头",
            "正文开头模板": "这本修真穿书文的爽点，不是恋爱，而是主角一步步把“祭天剧本”改写成“自救剧本”。",
            "正文结构建议": "钩子-反转-群像高光-命运冲突收束",
            "互动话术模板": "你最吃哪种大女主爽点？反转、群像还是命运改写？",
            "热门标签推荐": ["#修真文", "#穿书", "#大女主", "#群像", "#网文推荐"],
        },
    }
    analysis["配图提示词"] = _build_image_prompts(work, analysis)
    return analysis


def _find_topic_work(client, work_name):
    table_id = (get_feishu_config().get("related_table_ids") or {}).get("选题库")
    if not table_id:
        raise RuntimeError("未配置 选题库 table_id")
    for r in client.iter_records(table_id, page_size=200):
        f = r.get("fields") or {}
        if str(f.get("作品名称", "")).strip() == work_name:
            return {
                "作品名称": str(f.get("作品名称", "")).strip(),
                "作者": str(f.get("作者", "")).strip(),
                "平台": str(f.get("平台", "")).strip(),
                "分类": str(f.get("分类", "")).strip(),
                "简介": str(f.get("简介", "")).strip(),
            }
    return None


def _find_xhs_record(client, work_name):
    table_id = (get_feishu_config().get("related_table_ids") or {}).get("小红书笔记库")
    if not table_id:
        raise RuntimeError("未配置 小红书笔记库 table_id")
    for r in client.iter_records(table_id, page_size=200):
        f = r.get("fields") or {}
        if str(f.get("作品名称", "")).strip() == work_name:
            return table_id, r
    return table_id, None


def _find_xhs_record_by_id(client, rid):
    table_id = (get_feishu_config().get("related_table_ids") or {}).get("小红书笔记库")
    if not table_id:
        raise RuntimeError("未配置 小红书笔记库 table_id")
    rid = (rid or "").strip()
    for r in client.iter_records(table_id, page_size=200):
        if (r.get("record_id") or "").strip() == rid:
            return table_id, r
    return table_id, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work-name", default="")
    p.add_argument("--record-id", default="")
    p.add_argument("--part", choices=["all", "note", "prompts"], default="all")
    args = p.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    ensure_dirs()
    c = FeishuClient()
    if not c.is_configured():
        raise RuntimeError("飞书未配置")

    xhs_table_id = None
    rec = None
    if args.record_id.strip():
        xhs_table_id, rec = _find_xhs_record_by_id(c, args.record_id.strip())
    elif args.work_name.strip():
        xhs_table_id, rec = _find_xhs_record(c, args.work_name.strip())
    else:
        raise RuntimeError("需要提供 --record-id 或 --work-name")
    if not rec:
        raise RuntimeError("小红书笔记库未找到该作品记录")
    rid = rec.get("record_id")
    rec_fields = rec.get("fields", {}) or {}

    # Build work from topic library first, fallback to xhs record fields.
    work_name = str(rec_fields.get("作品名称", "")).strip() or args.work_name.strip()
    work = _find_topic_work(c, work_name) or {
        "作品名称": work_name,
        "作者": str(rec_fields.get("作者", "")).strip(),
        "平台": "",
        "分类": "",
        "简介": "",
    }

    analysis = _build_grounded_analysis(work)
    note = build_xhs_note(work, analysis)
    prompts = analysis.get("配图提示词", [])[:5]

    meta = c.get_table_field_meta(xhs_table_id) or {}
    fields = {}
    if args.part in ["all", "prompts"]:
        for i in range(5):
            k = f"生成配图提示词{i+1}"
            if k in meta:
                fields[k] = prompts[i] if i < len(prompts) else ""
    if args.part in ["all", "note"]:
        if "正文开头模板" in meta:
            fields["正文开头模板"] = _mobile_trim(analysis["小红书包装"]["正文开头模板"], 68)
        if "正文结构建议" in meta:
            fields["正文结构建议"] = _mobile_trim(analysis["小红书包装"]["正文结构建议"], 56)
        if "互动话术模板" in meta:
            fields["互动话术模板"] = _mobile_trim(analysis["小红书包装"]["互动话术模板"], 56)
        if "小红书标题模板" in meta:
            fields["小红书标题模板"] = analysis["小红书包装"]["小红书标题模板"]
        if "热门标签推荐" in meta:
            fields["热门标签推荐"] = analysis["小红书包装"]["热门标签推荐"]
    if "更新时间" in meta and fields:
        fields["更新时间"] = int(datetime.now().timestamp() * 1000)

    # Normalize by target field type to tolerate schema changes.
    for k, v in list(fields.items()):
        ftype = (meta.get(k) or {}).get("type")
        if ftype == 4:
            if k == "小红书标题模板":
                fields[k] = [str(v)] if not isinstance(v, list) else v[:1]
            elif isinstance(v, list):
                fields[k] = v
            elif isinstance(v, str):
                parts = [x.strip() for x in re.split(r"[,，/、;；\\s]+", v) if x.strip()]
                fields[k] = parts if parts else [v]
            else:
                fields[k] = [str(v)]
        elif ftype == 3:
            if isinstance(v, list):
                v = v[0] if v else ""
            s = str(v or "").strip()
            if s:
                fields[k] = c.resolve_single_select_option_id(xhs_table_id, k, s) or s
            else:
                fields[k] = ""
        elif ftype == 5:
            if isinstance(v, int):
                fields[k] = v
            else:
                fields[k] = int(datetime.now().timestamp() * 1000)

    if fields:
        c.update_record_in_table(xhs_table_id, rid, fields)

    # Refresh md attachment with concise mobile-style content.
    md_path = ""
    if args.part in ["all", "note"]:
        out_dir = os.path.join(PATHS["outputs"], "小红书笔记_v3", f"{work['作品名称']}_{work.get('作者','')}")
        os.makedirs(out_dir, exist_ok=True)
        md_path = os.path.join(out_dir, f"{work['作品名称']}-小红书笔记初稿.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(note)
        if "小红书笔记初稿" in meta:
            token = c.upload_file_to_bitable(md_path)
            c.update_record_in_table(xhs_table_id, rid, {"小红书笔记初稿": [{"file_token": token}]})

    print(
        {
            "work_name": work["作品名称"],
            "record_id": rid,
            "part": args.part,
            "md_path": md_path,
            "updated_prompt_count": len(prompts) if args.part in ["all", "prompts"] else 0,
        }
    )


if __name__ == "__main__":
    main()
