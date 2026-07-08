from datetime import datetime
import os as _os
import re

from flask import Blueprint, jsonify, render_template, request

from scripts.queue_manager import (
    QUEUE_FILE,
    get_queue,
    get_task_progress,
    is_task_truly_done,
    read_jsonl,
    update_status,
    update_task_fields,
    write_jsonl,
)
from scripts.data_normalizer import normalize_feishu_record, normalize_for_frontend
from scripts.deconstruct_daily import build_xhs_note, get_title_options
from scripts.generation_context import build_generation_context, context_counts
from scripts.model_adapter import analyze_work
from scripts.quality_scorer import score_note
from scripts.account_strategy import get_account_strategy, load_account_strategies, save_current_account_strategy
from scripts.search import search_work_info
from scripts.source_cleaner import clean_source_synopsis

bp = Blueprint("web_task_detail", __name__)


def _has_story_source(work, search_info=None):
    search_info = search_info or {}
    intro = str(work.get("剧情简介") or work.get("简介") or "").strip()
    source = str(work.get("简介来源") or search_info.get("搜索来源链接") or search_info.get("搜索模式") or "").strip()
    if not intro or len(intro) < 30:
        return False
    if source == "fallback_required_field":
        return False
    return "当前选题池未提供详细简介" not in intro


def _build_verified_work(task):
    work = {
        "作品名称": task.get("work_name", ""),
        "作者": task.get("author", ""),
        "平台": task.get("platform", ""),
        "分类": task.get("category", ""),
        "简介": task.get("synopsis", ""),
        "取向": task.get("orientation", ""),
    }
    search_info = search_work_info(work)
    for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
        if not work.get(k) and search_info.get(k):
            work[k] = search_info.get(k)
    clean_intro = search_info.get("剧情简介") or clean_source_synopsis(search_info.get("简介", "")).get("剧情简介", "")
    if clean_intro and len(str(clean_intro)) > len(str(work.get("简介", ""))):
        work["简介"] = clean_intro
        work["剧情简介"] = clean_intro
        work["原始简介"] = search_info.get("原始简介") or search_info.get("简介", "")
        work["非剧情信息"] = search_info.get("非剧情信息", [])
        work["简介来源"] = search_info.get("搜索来源链接") or search_info.get("搜索模式", "")
    return work, search_info


@bp.get("/task/<task_id>")
def task_detail_page(task_id):
    """任务详情页面"""
    return render_template(
        "task_detail.html",
        task_id=task_id,
        page_title="任务详情",
        header_back_href="/production-center",
        header_back_text="返回生产中心",
        header_badge="ID: " + task_id,
    )


@bp.get("/api/task/<task_id>")
def task_detail_api(task_id):
    """获取任务详情"""
    try:
        items = get_queue(per_page=9999).get("items", [])
        task = None
        for i in items:
            if i.get("record_id") == task_id:
                task = i
                break
        
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        
        # 添加阶段信息
        from scripts.queue_manager import STAGE_PROGRESS, STAGE_LABELS
        status = task.get("status", "")
        if status == "pending":
            status = "waiting"
        
        task["stage_label"] = STAGE_LABELS.get(status, status or "未知")
        task["stage_progress"] = get_task_progress(task)
        task["progress_percent"] = round(get_task_progress(task) / 6 * 100)
        task["display_status"] = status
        task["truly_done"] = is_task_truly_done(task)
        task["has_images"] = bool(task.get("images", {}).get("cover"))
        
        # 步骤时间
        task["step_times"] = task.get("step_times", {})
        
        # 处理拆文结果
        deconstruct_result = task.get("deconstruct_result")
        task["generation_strategy"] = _extract_generation_strategy(task, deconstruct_result)
        if not deconstruct_result:
            task["deconstruct_result"] = None
        elif deconstruct_result.get("缓存") and not deconstruct_result.get("开篇套路"):
            task["deconstruct_result"] = None
        else:
            task["deconstruct_result"] = normalize_for_frontend(
                normalize_feishu_record(deconstruct_result, source="main")
            )
        
        # 处理笔记内容
        note_content = task.get("note_content", "")
        title_options = _ensure_title_options(task, deconstruct_result)
        if not note_content or note_content.startswith("（缓存") or len(str(note_content).strip()) < 10:
            # 从拆文结果中提取笔记内容
            dr = task.get("deconstruct_result") or {}
            xhs = dr.get("小红书包装") or {}
            title = xhs.get("小红书标题模板", "") or ""
            body = xhs.get("正文开头模板", "") or ""
            if not title and not body:
                title = task.get('work_name', '') + ' 拆解笔记'
                body = "请运行拆文任务获取笔记内容"
            task["note_content"] = {
                "title": title,
                "content": body,
                "tags": [],
                "score": _format_score(task.get("quality_score")),
                "title_options": title_options if title_options else [],
            }
        else:
            # 笔记内容是 markdown 字符串
            note_text = str(note_content)
            task["note_content"] = {
                "title": _extract_title(note_text),
                "content": _extract_body(note_text),
                "tags": _extract_tags(note_text),
                "score": _format_score(task.get("quality_score")),
                "title_options": title_options if title_options else _extract_title_options(note_text),
            }
        task["modification_log"] = task.get("modification_log", "")
        
        return jsonify({"ok": True, "data": task})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _extract_generation_strategy(task, deconstruct_result):
    quality_score = task.get("quality_score") if isinstance(task.get("quality_score"), dict) else {}
    score_trace = quality_score.get("strategy_trace") if isinstance(quality_score, dict) else {}
    basis = {}
    if isinstance(deconstruct_result, dict):
        basis = deconstruct_result.get("生成依据") or deconstruct_result.get("generation_basis") or {}
    if not isinstance(basis, dict):
        basis = {}
    strategy = basis.get("账号策略") or basis.get("account_strategy") or score_trace or {}
    if not isinstance(strategy, dict):
        strategy = {}
    current_strategy = get_account_strategy(task.get("account_strategy_id") or strategy.get("id"))
    return {
        "id": strategy.get("id") or current_strategy.get("id", ""),
        "name": strategy.get("name") or current_strategy.get("name", ""),
        "positioning": strategy.get("positioning") or current_strategy.get("positioning", ""),
        "benchmark_accounts": strategy.get("benchmark_accounts") or current_strategy.get("benchmark_accounts", []),
        "quality_focus": strategy.get("quality_focus") or current_strategy.get("quality_focus", []),
        "platform_rules": basis.get("平台通用规则") or basis.get("platform_rules") or [
            "标题具体",
            "封面一眼可读",
            "前三行先给结论",
            "评论钩子低门槛",
        ],
        "content_fact_first": bool(basis.get("内容事实优先", basis.get("content_fact_first", True))),
    }


def _ensure_title_options(task, deconstruct_result):
    saved_options = task.get("title_options", [])
    if not isinstance(saved_options, list):
        saved_options = [str(saved_options)] if saved_options else []
    saved_options = [str(t).strip() for t in saved_options if str(t).strip()]
    if not isinstance(deconstruct_result, dict):
        return saved_options[:10]
    try:
        work = {
            "作品名称": task.get("work_name", ""),
            "作者": task.get("author", ""),
            "平台": task.get("platform", ""),
            "分类": task.get("category", ""),
            "简介": task.get("synopsis", ""),
            "取向": task.get("orientation", ""),
        }
        account_strategy = get_account_strategy(task.get("account_strategy_id"))
        generated = get_title_options(work, deconstruct_result, account_strategy=account_strategy)
        options = []
        for title in generated:
            _append_clean_title(options, title)
        if len(options) < 8:
            for title in saved_options:
                _append_clean_title(options, title)
        options = options[:10]
        if options and options != saved_options[:10]:
            update_task_fields(task.get("record_id"), title_options=options)
    except Exception:
        return saved_options[:10]
    return options[:10]


def _append_clean_title(options, title):
    title = str(title or "").strip()
    if not title or "/" in title:
        return
    key = re.sub(r"[\s，。！？!?：:、,.]+", "", title).lower()
    near_key = key[:16]
    for existing in options:
        existing_key = re.sub(r"[\s，。！？!?：:、,.]+", "", str(existing)).lower()
        if key == existing_key or (near_key and existing_key.startswith(near_key)):
            return
    options.append(title)


def _extract_title(note_content):
    """从笔记内容提取标题"""
    if not note_content:
        return ""
    lines = note_content.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("【标题】"):
            return line.replace("【标题】", "", 1).strip()
        if line.startswith("标题："):
            return line.replace("标题：", "", 1).strip()
        if line.startswith("标题:"):
            return line.replace("标题:", "", 1).strip()
        if line and not line.startswith("#"):
            return line[:50]
    return ""


def _extract_body(note_content):
    """去掉【标题】行和【备选标题】区块，避免正文编辑框重复出现。"""
    if not note_content:
        return ""
    lines = str(note_content).splitlines()
    result = []
    skip_titles = False
    for line in lines:
        stripped = line.strip()
        # 跳过【标题】行
        if not result and (stripped.startswith("# ") or stripped.startswith("【标题】") or stripped.startswith("标题：") or stripped.startswith("标题:")):
            continue
        # 跳过【备选标题】区块
        if stripped.startswith("【备选标题】"):
            skip_titles = True
            continue
        if skip_titles and (stripped.startswith("  ") or re.match(r'^\d+\.\s', stripped)):
            continue
        skip_titles = False
        result.append(line)
    return "\n".join(result).lstrip()


def _extract_title_options(note_content):
    """从笔记内容提取备选标题列表（向后兼容旧数据）"""
    if not note_content:
        return []
    lines = str(note_content).splitlines()
    titles = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("【备选标题】"):
            in_section = True
            continue
        if in_section:
            if not stripped or stripped.startswith("【") or (not re.match(r'^\d+\.\s', stripped) and not stripped.startswith("  ")):
                break
            # 去除编号前缀
            title = re.sub(r'^\d+\.\s*', '', stripped.lstrip())
            if title:
                titles.append(title)
    return titles


def _extract_tags(note_content):
    """从笔记内容提取标签"""
    if not note_content:
        return []
    tags = []
    # 查找 # 标签
    matches = re.findall(r'#(\w+)', note_content)
    tags.extend(matches[:5])
    return tags


def _find_task(task_id):
    items = read_jsonl(QUEUE_FILE)
    for item in items:
        if item.get("record_id") == task_id:
            return item
    return None


def _format_score(score):
    if not isinstance(score, dict):
        return None
    suggestion = score.get("suggestion", "")
    suggestions = score.get("suggestions", [])
    if not isinstance(suggestions, list):
        suggestions = []
    if not suggestions and suggestion:
        suggestions = [suggestion]
    return {
        "total": score.get("total", 0),
        "title_attract": score.get("title_appeal", 0),
        "emotion": score.get("emotion_density", 0),
        "collect_value": score.get("collection_value", 0),
        "interaction": score.get("interaction_guide", 0),
        "style_match": score.get("xhs_style_match", 0),
        "ai_trace": score.get("ai_trace", 0),
        "grade": score.get("grade", ""),
        "suggestions": suggestions,
    }


def _compose_note(title, content, tags):
    title = str(title or "").strip()
    content = str(content or "").strip()
    clean_tags = [str(t).strip().lstrip("#") for t in (tags or []) if str(t).strip()]
    parts = []
    if title:
        parts.append(f"# {title}")
    if content:
        parts.append(content)
    if clean_tags:
        parts.append("标签：" + " ".join(f"#{tag}" for tag in clean_tags))
    return "\n\n".join(parts).strip()


def _build_modification_log(task, new_note, quality_score):
    old_note = str(task.get("note_content") or "")
    changed = []
    if _extract_title(old_note) != _extract_title(new_note):
        changed.append("标题")
    if old_note.strip() != new_note.strip():
        changed.append("正文")
    if _extract_tags(old_note) != _extract_tags(new_note):
        changed.append("标签")
    if not changed:
        changed.append("草稿")
    total = 0
    if isinstance(quality_score, dict):
        total = quality_score.get("total", 0)
    return (
        f"{datetime.now().strftime('%Y%m%d %H:%M')} | "
        f"字段: {'/'.join(changed)} | 说明: 人工修改 | 评分:{total}"
    )


def _append_local_modification_log(task, log_line):
    current = str(task.get("modification_log") or "").strip()
    return log_line if not current else f"{current}\n{log_line}"


def _save_to_feishu_note(task, title, content, tags, log_line, score):
    xhs_record_id = task.get("xhs_record_id")
    if not xhs_record_id:
        return {"attempted": False, "ok": False, "error": "missing xhs_record_id"}
    try:
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config

        client = FeishuClient()
        cfg = get_feishu_config()
        xhs_table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not xhs_table_id or not client.is_configured():
            return {"attempted": False, "ok": False, "error": "feishu not configured"}

        patch = {}
        if title:
            patch["小红书标题模板"] = title
        if content:
            patch["正文开头模板"] = content
        if tags:
            patch["热门标签推荐"] = tags
        if patch:
            client.update_record_in_table(xhs_table_id, xhs_record_id, patch)
        log_ok = client.save_modification_log(
            xhs_table_id,
            xhs_record_id,
            _diff_log_for_feishu(log_line),
            score.get("total", 0) if isinstance(score, dict) else 0,
        )
        return {"attempted": True, "ok": bool(log_ok), "error": None if log_ok else "log write failed"}
    except Exception as e:
        return {"attempted": True, "ok": False, "error": str(e)}


def _select_value(client, table_id, field_name, names, fallback=""):
    for name in names:
        opt_id = client.resolve_single_select_option_id(table_id, field_name, name)
        if opt_id:
            return opt_id
    return fallback or (names[0] if names else "")


def _coerce_feishu_fields(client, table_id, fields, select_names=None):
    select_names = select_names or {}
    meta = client.get_table_field_meta(table_id)
    available = set(meta.keys())
    patch = {k: v for k, v in fields.items() if k in available and v is not None}
    for key, val in list(patch.items()):
        ftype = (meta.get(key) or {}).get("type")
        if ftype == 3:
            names = select_names.get(key) or ([val] if val else [])
            patch[key] = _select_value(client, table_id, key, names, str(val or ""))
            if not patch[key]:
                patch.pop(key, None)
        elif ftype == 4:
            raw = val if isinstance(val, list) else [val]
            opts = (meta.get(key) or {}).get("property", {}).get("options") or []
            name_to_id = {
                str(o.get("name")).strip(): (o.get("id") or o.get("option_id") or o.get("value"))
                for o in opts
                if o.get("name")
            }
            resolved = []
            for item in raw:
                s = str(item or "").strip().lstrip("#")
                if not s:
                    continue
                resolved.append(str(name_to_id.get(s) or s))
            patch[key] = resolved
        elif ftype == 5:
            patch[key] = int(datetime.now().timestamp() * 1000)
        elif ftype in (7,):
            patch[key] = bool(val)
    return patch


def _upsert_feishu_note_record(task, title, content, tags, log_line, score):
    try:
        from scripts.feishu_client import FeishuClient
        from scripts.feishu_config import get_feishu_config

        client = FeishuClient()
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not table_id or not client.is_configured():
            return {"attempted": False, "ok": False, "error": "feishu not configured"}

        main_record_id = task.get("main_record_id") or ""
        fields = {
            "作品名称": task.get("work_name", ""),
            "作者": task.get("author", ""),
            "主表记录ID": main_record_id,
            "记录表ID": main_record_id,
            "小红书标题模板": title,
            "正文开头模板": content,
            "热门标签推荐": tags,
            "审核状态": "已通过",
            "状态": "已通过",
            "更新时间": datetime.now().strftime("%Y-%m-%d"),
        }
        patch = _coerce_feishu_fields(
            client,
            table_id,
            fields,
            select_names={
                "审核状态": ["已通过", "通过", "已审核", "完成"],
                "状态": ["已通过", "通过", "已完成", "完成"],
            },
        )

        record_id = task.get("xhs_record_id")
        if not record_id and main_record_id:
            for key in ["主表记录ID", "记录表ID"]:
                if key in client.get_table_fields(table_id):
                    rec = client.find_first_record_by_fields(table_id, {key: main_record_id})
                    if rec:
                        record_id = rec.get("record_id")
                        break
        if not record_id:
            record_id = client.create_record_in_table(table_id, patch)
        else:
            client.update_record_in_table(table_id, record_id, patch)

        client.save_modification_log(
            table_id,
            record_id,
            _diff_log_for_feishu(log_line),
            score.get("total", 0) if isinstance(score, dict) else 0,
        )
        return {"attempted": True, "ok": True, "record_id": record_id, "error": None}
    except Exception as e:
        return {"attempted": True, "ok": False, "error": str(e)}


def _update_feishu_main_approval(task, title, content, tags):
    try:
        from scripts.feishu_client import FeishuClient
        from scripts.dedupe import find_by_title_author

        client = FeishuClient()
        if not client.is_configured():
            return {"attempted": False, "ok": False, "error": "feishu not configured"}

        record_id = task.get("main_record_id") or find_by_title_author(task.get("work_name", ""), task.get("author", ""))
        if not record_id:
            return {"attempted": False, "ok": False, "error": "missing main_record_id"}

        fields = {
            "小红书标题模板": title,
            "正文开头模板": content,
            "热门标签推荐": tags,
            "是否发布笔记": "已审核",
            "审核状态": "已通过",
            "状态": "已通过",
            "任务状态": "已完成",
            "更新时间": datetime.now().strftime("%Y-%m-%d"),
            "审核时间": datetime.now().strftime("%Y-%m-%d"),
            "通过审核时间": datetime.now().strftime("%Y-%m-%d"),
        }
        patch = _coerce_feishu_fields(
            client,
            client.table_id,
            fields,
            select_names={
                "审核状态": ["已通过", "通过", "已审核", "完成"],
                "状态": ["已通过", "通过", "已完成", "完成"],
                "任务状态": ["已完成", "完成", "已通过", "通过"],
                "是否发布笔记": ["已审核"],
            },
        )
        if not patch:
            return {"attempted": True, "ok": False, "record_id": record_id, "error": "no matching fields"}
        if "是否发布笔记" not in patch:
            return {
                "attempted": True,
                "ok": False,
                "record_id": record_id,
                "fields": list(patch.keys()),
                "error": "主表缺少「是否发布笔记」字段，或该单选字段缺少「已审核」选项",
            }
        approved_option_id = client.resolve_single_select_option_id(client.table_id, "是否发布笔记", "已审核")
        if not approved_option_id:
            return {
                "attempted": True,
                "ok": False,
                "record_id": record_id,
                "fields": list(patch.keys()),
                "error": "主表「是否发布笔记」单选字段缺少「已审核」选项，请先在飞书表中添加该选项",
            }
        client.update_record(record_id, patch)
        return {"attempted": True, "ok": True, "record_id": record_id, "fields": list(patch.keys()), "error": None}
    except Exception as e:
        return {"attempted": True, "ok": False, "error": str(e)}


def _diff_log_for_feishu(log_line):
    parts = [p.strip() for p in str(log_line or "").split("|")]
    if len(parts) >= 3:
        return " | ".join(parts[1:-1])
    return str(log_line or "").strip()


@bp.post("/api/task/<task_id>/regenerate-note")
def regenerate_note(task_id):
    """重新生成笔记"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        work, search_info = _build_verified_work(task)
        if not _has_story_source(work, search_info):
            return jsonify({
                "ok": False,
                "error": "缺少可验证的剧情简介，已停止重新生成。请先在选题/任务中补充作品简介，或确认能搜索到真实作品简介。"
            }), 400
        generation_context = build_generation_context(task)
        account_strategy = get_account_strategy(task.get("account_strategy_id"))
        analysis = analyze_work(work, account_strategy=account_strategy, **generation_context)
        note_text = build_xhs_note(work, analysis, account_strategy=account_strategy)
        score = score_note(note_text, account_strategy=account_strategy)
        title_options = get_title_options(work, analysis, account_strategy=account_strategy)
        updated = update_task_fields(
            task_id,
            deconstruct_result=analysis,
            note_content=note_text,
            quality_score=score,
            title_options=title_options,
        )
        if not updated:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        saved_task = _find_task(task_id) or {}
        saved_note = str(saved_task.get("note_content") or "")
        if saved_note.strip() != str(note_text).strip():
            return jsonify({"ok": False, "error": "重新生成结果未成功保存，请重试"}), 500
        return jsonify({
            "ok": True,
            "data": {
                "note_content": note_text,
                "quality_score": score,
                "title": _extract_title(note_text),
                "title_options": title_options,
                "generation_context": context_counts(generation_context),
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _with_image_provider(provider, func, force_enabled=True):
    provider = str(provider or "").strip().lower()
    old_provider = _os.getenv("IMAGE_PROVIDER")
    old_enabled = _os.getenv("IMAGE_GEN_ENABLED")
    if provider:
        _os.environ["IMAGE_PROVIDER"] = provider
    if force_enabled:
        _os.environ["IMAGE_GEN_ENABLED"] = "true"
    try:
        return func()
    finally:
        if old_enabled is None:
            _os.environ.pop("IMAGE_GEN_ENABLED", None)
        else:
            _os.environ["IMAGE_GEN_ENABLED"] = old_enabled
        if old_provider is None:
            _os.environ.pop("IMAGE_PROVIDER", None)
        else:
            _os.environ["IMAGE_PROVIDER"] = old_provider


def _note_for_image_cards(task):
    note_text = str(task.get("note_content") or "")
    analysis = task.get("deconstruct_result") if isinstance(task.get("deconstruct_result"), dict) else {}
    packaging = analysis.get("小红书包装") if isinstance(analysis, dict) else {}
    if not isinstance(packaging, dict):
        packaging = {}
    return {
        "title": _extract_title(note_text) or packaging.get("小红书标题模板", "") or task.get("work_name", ""),
        "body": _extract_body(note_text) or packaging.get("正文开头模板", ""),
        "cta": packaging.get("互动话术模板", ""),
        "tags": _extract_tags(note_text) or packaging.get("热门标签推荐", []) or [],
        "lead": "",
    }


@bp.post("/api/task/<task_id>/regenerate-images")
def regenerate_images(task_id):
    """基于当前拆文结果重新生成封面和配图。"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        analysis = task.get("deconstruct_result")
        if not isinstance(analysis, dict):
            return jsonify({"ok": False, "error": "缺少拆文结果，无法生成配图"}), 400

        config = _read_strategy_config()
        provider = task.get("image_provider") or config.get("provider") or _os.getenv("IMAGE_PROVIDER", "jimeng")
        style = config.get("style") or "warm"
        count = int(config.get("count") or 3)

        from scripts.image_provider import generate_images_for_task
        result = _with_image_provider(provider, lambda: generate_images_for_task(analysis), force_enabled=True)
        if not result.get("ok"):
            return jsonify({"ok": False, "error": result.get("error") or "图片生成失败"}), 500

        images = result.get("images") or {}
        overlay_error = None
        try:
            from scripts.html_card_generator import generate_cards_on_images
            out_dir = _os.path.join("temp", "generated_images", task_id, "ai_overlay")
            images = generate_cards_on_images(
                _note_for_image_cards(task),
                images,
                style=style,
                n=max(count, len(images)),
                output_dir=out_dir,
                content_brief=analysis.get("内容简报") if isinstance(analysis, dict) else None,
                work_info={
                    "作品名称": task.get("work_name", ""),
                    "作者": task.get("author", ""),
                    "平台": task.get("platform", ""),
                    "分类": task.get("category", ""),
                },
                analysis=analysis,
            )
        except Exception as e:
            overlay_error = str(e)

        update_task_fields(task_id, images=images)
        return jsonify({
            "ok": True,
            "data": {
                "images": images,
                "provider": provider,
                "overlay_error": overlay_error,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/rescore")
def rescore_note(task_id):
    """重新评分"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        note_text = str((request.get_json(silent=True) or {}).get("note_content") or task.get("note_content") or "")
        if not note_text.strip():
            return jsonify({"ok": False, "error": "笔记内容为空"}), 400
        account_strategy = get_account_strategy(task.get("account_strategy_id"))
        score = score_note(note_text, account_strategy=account_strategy)
        update_task_fields(task_id, quality_score=score)
        return jsonify({"ok": True, "data": {"quality_score": score, "score": _format_score(score)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/save-draft")
def save_draft(task_id):
    """保存草稿"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        data = request.get_json(force=True) or {}
        title = data.get("title", "")
        content = data.get("content", "")
        tags = data.get("tags", [])
        note_text = _compose_note(title, content, tags)
        if not note_text:
            return jsonify({"ok": False, "error": "草稿内容为空"}), 400

        score = task.get("quality_score") if isinstance(task.get("quality_score"), dict) else {}
        log_line = _build_modification_log(task, note_text, score)
        local_log = _append_local_modification_log(task, log_line)
        feishu_result = _save_to_feishu_note(task, title, content, tags, log_line, score)
        update_task_fields(
            task_id,
            note_content=note_text,
            modification_log=local_log,
        )
        return jsonify({
            "ok": True,
            "data": {
                "saved": True,
                "modification_log": log_line,
                "feishu": feishu_result,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/approve")
def approve_task(task_id):
    """保存并通过审核"""
    try:
        task = _find_task(task_id)
        if not task:
            return jsonify({"ok": False, "error": "任务不存在"}), 404
        data = request.get_json(silent=True) or {}
        title = data.get("title")
        content = data.get("content")
        tags = data.get("tags")
        if title is None:
            title = _extract_title(str(task.get("note_content") or ""))
        if content is None:
            content = _extract_body(str(task.get("note_content") or ""))
        if tags is None:
            tags = _extract_tags(str(task.get("note_content") or ""))

        note_text = _compose_note(title, content, tags)
        score = task.get("quality_score") if isinstance(task.get("quality_score"), dict) else {}
        log_line = (
            f"{datetime.now().strftime('%Y%m%d %H:%M')} | "
            "字段: 审核状态/最终稿 | 说明: 通过审核 | "
            f"评分:{score.get('total', 0) if isinstance(score, dict) else 0}"
        )
        local_log = _append_local_modification_log(task, log_line)

        main_result = _update_feishu_main_approval(task, title, content, tags)
        note_result = _upsert_feishu_note_record(task, title, content, tags, log_line, score)
        write_errors = []
        if main_result.get("attempted") and not main_result.get("ok"):
            write_errors.append(f"主表写回失败: {main_result.get('error')}")
        if note_result.get("attempted") and not note_result.get("ok"):
            write_errors.append(f"小红书笔记库写回失败: {note_result.get('error')}")
        sync_status = "failed" if write_errors else "ok"
        sync_error = "；".join(write_errors)
        update_task_fields(
            task_id,
            note_content=note_text,
            modification_log=local_log,
            xhs_record_id=(note_result.get("record_id") if note_result.get("ok") else task.get("xhs_record_id")),
            feishu_sync_status=sync_status,
            feishu_sync_error=sync_error,
        )
        update_status(task_id, "done")
        return jsonify({
            "ok": True,
            "message": "已通过审核" if not write_errors else "本地已审核，飞书同步失败",
            "warning": sync_error,
            "data": {
                "main": main_result,
                "xhs_note": note_result,
                "modification_log": log_line,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/task/<task_id>/retry")
def retry_task_api(task_id):
    """重试任务——重置为 pending 强制重新拆文"""
    try:
        # queue_manager.retry_task 只处理 failed，这里强制重置
        items = read_jsonl(QUEUE_FILE)
        for i in items:
            if i.get("record_id") == task_id:
                i["status"] = "pending"
                i["error"] = None
                i["retry_count"] = i.get("retry_count", 0) + 1
                i["deconstruct_result"] = None
                i["note_content"] = None
                i["quality_score"] = None
                i["images"] = {}
                write_jsonl(QUEUE_FILE, items)
                return jsonify({"ok": True, "data": {"retried": True, "message": "已重置，worker 将重新拆文"}})
        return jsonify({"ok": False, "error": "任务未找到"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 图片生成策略 API ────────────────────────────────────────────────────
import os as _os
from pathlib import Path as _Path

_STRATEGY_CONFIG_DIR = _Path(__file__).resolve().parent.parent.parent.parent / "data" / "config"
_STRATEGY_CONFIG_FILE = _STRATEGY_CONFIG_DIR / "image_strategy.json"

def _read_strategy_config():
    if not _STRATEGY_CONFIG_FILE.exists():
        return {"strategy": "ai", "style": "warm", "count": 3, "provider": _os.getenv("IMAGE_PROVIDER", "jimeng")}
    import json as _json
    with open(_STRATEGY_CONFIG_FILE, "r", encoding="utf-8") as _f:
        config = _json.load(_f)
    config.setdefault("strategy", "ai")
    config.setdefault("style", "warm")
    config.setdefault("count", 3)
    config.setdefault("provider", _os.getenv("IMAGE_PROVIDER", "jimeng"))
    return config

def _write_strategy_config(data: dict):
    _STRATEGY_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(_STRATEGY_CONFIG_FILE, "w", encoding="utf-8") as _f:
        _json.dump(data, _f, ensure_ascii=False, indent=2)


@bp.get("/api/config/image_strategy")
def get_image_strategy():
    """获取当前图片生成策略"""
    try:
        return jsonify(_read_strategy_config())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.get("/api/config/account_strategies")
def get_account_strategies():
    """获取账号策略列表和当前默认策略。"""
    try:
        data = load_account_strategies()
        return jsonify({
            "ok": True,
            "current": data["current"],
            "strategies": list(data["strategies"].values()),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/config/account_strategies/current")
def set_current_account_strategy():
    """设置当前工作台服务的账号对象。"""
    try:
        data = request.get_json(force=True) or {}
        strategy = save_current_account_strategy(data.get("strategy_id"))
        return jsonify({"ok": True, "current": strategy.get("id"), "data": strategy})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/api/config/image_strategy")
def set_image_strategy():
    """更新图片生成策略（需重启 worker 生效）"""
    try:
        data = request.get_json(force=True) or {}
        strategy = data.get("strategy", "ai").strip().lower()
        if strategy not in ("ai", "html_card", "auto"):
            return jsonify({"ok": False, "error": "strategy must be ai, html_card or auto"}), 400
        provider = data.get("provider", _os.getenv("IMAGE_PROVIDER", "jimeng")).strip().lower()
        if provider not in ("jimeng", "siliconflow", "liblib", "mock"):
            return jsonify({"ok": False, "error": "provider must be jimeng, siliconflow, liblib or mock"}), 400
        config = {
            "strategy": strategy,
            "style": data.get("style", "warm").strip(),
            "count": int(data.get("count", 3) or 3),
            "provider": provider,
        }
        _write_strategy_config(config)
        return jsonify({"ok": True, "data": config, "warning": "需重启 jimeng_worker 生效"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
