import json
import os

from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.web.services.xhs_candidates import load_xhs_note_candidates
from scripts.web.services.xhs_facts import find_xhs_record_by_id
from scripts.web.services.xhs_fields import find_local_xhs_md, xhs_note_from_fields


def load_xhs_preview_data(rid, notice="", is_fact_repairing=False):
    rid = (rid or "").strip()
    if not rid:
        return {"ok": False, "error": "empty_rid"}, 400

    client = FeishuClient()
    if not client.is_configured():
        return {"ok": False, "error": "feishu_not_configured"}, 500

    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
    if not table_id:
        return {"ok": False, "error": "xhs_table_not_configured"}, 500

    _, record = find_xhs_record_by_id(client, rid)
    if not record:
        return {"ok": False, "error": "xhs_record_not_found", "rid": rid}, 404

    f = record.get("fields", {}) or {}
    prompts = []
    for i in range(1, 6):
        p = str(f.get(f"生成配图提示词{i}", "")).strip()
        if p:
            prompts.append(p)
    prompts_text = "\n".join([f"{i+1}. {p}" for i, p in enumerate(prompts)]) or "（无提示词）"

    title = str(f.get("作品名称", "")).strip()
    author = str(f.get("作者", "")).strip()
    local_md = find_local_xhs_md(title, author)
    note_text = ""
    note_source = "飞书字段拼装"
    if local_md and os.path.exists(local_md):
        with open(local_md, "r", encoding="utf-8") as fh:
            note_text = fh.read().strip()
        note_source = local_md
    if not note_text:
        note_text = xhs_note_from_fields(f) or "（未找到本地MD，也无法从字段拼装正文）"

    notice = (notice or "").strip().lower()
    xhs_banner = None
    if notice == "preview_ready":
        xhs_banner = {"kind": "ok", "text": "候选重生版本已生成（请先看“来源”是否为 model），确认后再采纳更新飞书。"}
    elif notice == "adopted":
        xhs_banner = {"kind": "ok", "text": "已采纳候选版本，飞书字段与附件已更新。"}
    elif notice == "fact_repairing":
        xhs_banner = {"kind": "err", "text": "检测到关联事实数据缺失，已自动触发修复任务。请稍后刷新后再重生。"}
    elif notice == "err":
        xhs_banner = {"kind": "err", "text": "操作失败，请稍后重试并检查日志。"}
    if not xhs_banner and is_fact_repairing:
        xhs_banner = {"kind": "err", "text": "关联事实数据正在修复中，请稍后刷新再重生。"}

    cands = load_xhs_note_candidates()
    cand = cands.get(rid) if isinstance(cands, dict) else None
    candidate_note = ""
    candidate_ts = ""
    cand_feedback = ""
    cand_dissatisfaction = ""
    cand_model_provider = ""
    cand_model_name = ""
    cand_gen_source = ""
    cand_gen_error = ""
    cand_allow_fallback = True
    cand_facts_missing = []
    cand_facts_main_record_id = ""
    if isinstance(cand, dict):
        candidate_note = str(cand.get("note", "")).strip()
        candidate_ts = str(cand.get("ts", "")).strip()
        cand_feedback = str(cand.get("feedback", "")).strip()
        cand_dissatisfaction = str(cand.get("dissatisfaction", "")).strip()
        cand_model_provider = str(cand.get("model_provider", "")).strip()
        cand_model_name = str(cand.get("model_name", "")).strip()
        cand_gen_source = str(cand.get("gen_source", "")).strip()
        cand_gen_error = str(cand.get("gen_error", "")).strip()
        cand_allow_fallback = bool(cand.get("allow_fallback", True))
        raw_missing = cand.get("facts_missing", [])
        cand_facts_missing = raw_missing if isinstance(raw_missing, list) else []
        cand_facts_main_record_id = str(cand.get("facts_main_record_id", "")).strip()

    if not cand_model_provider:
        cand_model_provider = os.getenv("MODEL_PROVIDER", "qwen").strip().lower()
    if not cand_model_name:
        if cand_model_provider in {"qwen", "dashscope"}:
            cand_model_name = os.getenv("QWEN_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "qwen-plus").strip()
        else:
            cand_model_name = os.getenv("OPENAI_MODEL", "").strip()

    return (
        {
            "ok": True,
            "rid": rid,
            "title": title,
            "author": author,
            "note_text": note_text,
            "note_source": note_source,
            "prompts_text": prompts_text,
            "xhs_banner": xhs_banner,
            "candidate_note": candidate_note,
            "candidate_ts": candidate_ts,
            "cand_feedback": cand_feedback,
            "cand_dissatisfaction": cand_dissatisfaction,
            "cand_model_provider": cand_model_provider,
            "cand_model_name": cand_model_name,
            "cand_gen_source": cand_gen_source,
            "cand_gen_error": cand_gen_error,
            "cand_allow_fallback": cand_allow_fallback,
            "cand_facts_missing": cand_facts_missing,
            "cand_facts_main_record_id": cand_facts_main_record_id,
            "fields_json": json.dumps(f, ensure_ascii=False, indent=2),
        },
        200,
    )
