import json
import os
import sys
import base64
import glob
import threading
from datetime import datetime

from flask import Flask, render_template_string, request, redirect, url_for, abort

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.env_loader import load_dotenv
from scripts.utils import append_jsonl, now_ts
from scripts.repair_xhs_record import _build_grounded_analysis, _find_topic_work
from scripts.model_adapter import analyze_work
from scripts.related_sync import sync_related, update_main_links
from scripts.web.services.local_runs import (
    load_image_queue_status as service_load_image_queue_status,
    load_records as service_load_records,
    load_run_summary as service_load_run_summary,
)
from scripts.web.services.xhs_fields import (
    compute_xhs_missing as service_compute_xhs_missing,
    find_local_xhs_md as service_find_local_xhs_md,
    xhs_note_from_fields as service_xhs_note_from_fields,
)
from scripts.web.services.prescreen_status import (
    fmt_compact_num as service_fmt_compact_num,
    humanize_prescreen_summary as service_humanize_prescreen_summary,
    load_prescreen_jobs_tail as service_load_prescreen_jobs_tail,
    load_prescreen_latest_cached as service_load_prescreen_latest_cached,
    load_prescreen_recent as service_load_prescreen_recent,
)
from scripts.web.services.analysis_status import (
    clear_analysis_report_cache as service_clear_analysis_report_cache,
    load_analysis_jobs_tail as service_load_analysis_jobs_tail,
    load_analysis_recent as service_load_analysis_recent,
    load_latest_analysis_report as service_load_latest_analysis_report,
)
from scripts.web.services.xhs_candidates import (
    load_xhs_note_candidates as service_load_xhs_note_candidates,
    save_xhs_note_candidates as service_save_xhs_note_candidates,
)
from scripts.web.services.xhs_facts import (
    apply_fact_overrides as service_apply_fact_overrides,
    collect_fact_pack as service_collect_fact_pack,
    facts_to_text as service_facts_to_text,
    field_contains_main_record_id as service_field_contains_main_record_id,
    find_main_record_by_id as service_find_main_record_by_id,
    find_xhs_record_by_id as service_find_xhs_record_by_id,
)
from scripts.web.services.xhs_preview_data import (
    load_xhs_preview_data as service_load_xhs_preview_data,
)

app = Flask(__name__)

_XHS_STATS_CACHE = {"ts": 0.0, "data": None, "err": None}
_XHS_STATS_CACHE_SEC = 60
_XHS_FILTER_CACHE = {}  # key -> {"ts": float, "items": list}
_XHS_FILTER_CACHE_SEC = 60
_TOPIC_STATS_CACHE = {}  # name -> {"ts": float, "data": dict|None, "err": str|None}
_TOPIC_STATS_CACHE_SEC = 120
_PRESCREEN_LATEST_CACHE_SEC = 45
_XHS_FACT_REPAIRING = {}  # xhs_record_id -> ts

TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>小红书内容生成工具🔧</title>
  <style>
    :root { --bg:#f2f4f8; --fg:#1f2a37; --muted:#7a8597; --card:#ffffff; --accent:#2f6fed; --line:#e6ebf2; --nav:#f5f7fb; }
    *, *::before, *::after { box-sizing: border-box; }
    body { font-family: "Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif; background: var(--bg); color: var(--fg); margin: 0; }
    .appLayout { max-width: none; margin: 0; padding: 14px 14px 14px 0; display:grid; grid-template-columns: minmax(0,1fr) 320px; gap: 14px; margin-left: 240px; }
    .sideNav { background:var(--nav); border-right:1px solid var(--line); border-radius: 0; padding: 16px 12px; position: fixed; left: 0; top: 0; bottom: 0; width: 226px; overflow-y: auto; z-index: 20; }
    .sideNav h2 { margin: 0 0 10px; font-size: 20px; font-family: "Noto Serif SC","Songti SC",serif; color:#334155; }
    .sideNav .meta { margin-bottom: 10px; }
    .sideNav a { display:flex; align-items:center; gap:8px; padding:10px 10px; border-radius:10px; border:1px solid transparent; color:#4a5668; text-decoration:none; margin-bottom:6px; font-size:13px; transition: all .15s ease; }
    .sideNav a:hover { background:#eef2f8; border-color:#dce4f0; }
    .sideNav a.active { background:#e9f0ff; border-color:#c8d9ff; color:#1d4fd8; font-weight:700; }
    .contentCol, .assistCol { min-width: 0; }
    .assistCol .card { position: sticky; top: 12px; }
    header { padding: 14px 16px; background: #f9fbff; border: 1px solid var(--line); border-radius: 16px; margin-bottom: 12px; box-shadow: 0 8px 24px rgba(50,72,120,.05); }
    h1 { margin: 0 0 6px; font-size: 22px; letter-spacing: .2px; font-family: "Noto Serif SC","Songti SC",serif; }
    /* Wider content area so form fields don't get squeezed on desktop. */
    .wrap { padding: 0; max-width: none; margin: 0; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 12px 14px; margin-bottom: 12px; box-shadow: 0 10px 28px rgba(38,71,137,.06); overflow: hidden; }
    .sectionTitle { font-size: 14px; font-weight: 700; margin-bottom: 8px; color:#2d3f57; }
    .subtle { background:#f8fbff; border:1px dashed #d8e4fb; }
    .meta { color: var(--muted); font-size: 12px; }
    .btn { background: var(--accent); color: #fff; border: 0; padding: 8px 12px; border-radius: 10px; cursor: pointer; font-size: 12px; white-space: nowrap; flex: 0 0 auto; }
    .btn.secondary { background: #fff; color: #2f4e8f; border: 1px solid #cfdcf6; }
    .row { display: flex; gap: 10px; align-items: center; }
    .main { flex: 1; min-width: 0; }
    .actions { display: flex; align-items: center; gap: 8px; margin-left: auto; }
    .actions .btn { padding: 6px 9px; }
    a { color: var(--accent); text-decoration: none; }
    .path { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 760px; display: inline-block; vertical-align: bottom; }
    .toolbar { display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap; }
    .input, .select { padding:6px 8px; border:1px solid #ddd; border-radius:8px; font-size:12px; max-width:100%; }
    .banner { border-radius:10px; padding:8px 10px; margin-bottom:10px; font-size:12px; }
    .banner.ok { background:#eaf6ec; border:1px solid #b7ddbf; color:#235a2f; }
    .banner.err { background:#fdeeee; border:1px solid #f3b5b5; color:#8b1e1e; }
    .grid { display:grid; grid-template-columns: 1.2fr 0.8fr; gap: 10px; }
    .kpi { display:flex; gap:10px; flex-wrap:wrap; }
    .pill { background:#f2f7ff; border:1px solid #d8e6ff; border-radius:999px; padding:4px 8px; font-size:12px; color:#2f4e8f; }
    .list { margin:8px 0 0; padding:0; list-style:none; }
    .list li { display:flex; gap:8px; align-items:center; padding:6px 0; border-top:1px dashed #eee; font-size:12px; }
    .tag { font-size:11px; padding:2px 6px; border-radius:999px; border:1px solid #d9e2f1; background:#fff; color:#2a3950; }
    .tag.ok { border-color:#b7ddbf; color:#235a2f; background:#eaf6ec; }
    .tag.err { border-color:#f3b5b5; color:#8b1e1e; background:#fdeeee; }
    .tag.warn { border-color:#f0d18f; color:#8a5a12; background:#fff6df; }
    .tabs { display:flex; gap:8px; align-items:center; margin-top:10px; flex-wrap:wrap; }
    .tab { display:inline-flex; align-items:center; gap:8px; padding:7px 10px; border-radius:999px; border:1px solid var(--line); color:#3a2a22; background:#fff; font-size:12px; }
    .tab.active { background: #fff3ea; border-color: #f1c7b6; color: #7a2a12; }
    .primaryAction { display:flex; gap:8px; align-items:center; margin-top:8px; }
    .primaryAction .btn { font-weight:700; min-width: 130px; }
    .pager { display:flex; gap:8px; align-items:center; justify-content:center; margin: 12px 0 6px; }
    .formRow { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-top:10px; }
    /* Allow flex children to shrink instead of overflowing (important for inputs). */
    .formRow > * { min-width: 0; }
    /* Prescreen form: keep labels readable and let the keyword input take remaining space. */
    .psQuery { flex: 1 1 420px; min-width: 240px; max-width: 100%; }
    .psLimit { width: 90px; }
    .psBatch { width: 150px; }
    .psCheck { display:inline-flex; align-items:center; gap:6px; white-space: nowrap; flex: 0 0 auto; }
    .psBtn { flex: 0 0 auto; }
    .label { font-size:12px; color: var(--muted); white-space: nowrap; flex: 0 0 auto; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    .table { width:100%; border-collapse: separate; border-spacing: 0; margin-top:10px; font-size:12px; table-layout: fixed; border:1px solid var(--line); border-radius:14px; overflow:hidden; }
    .table th, .table td { text-align:left; padding:9px 10px; border-top:1px solid #eef3fb; vertical-align:top; overflow:hidden; text-overflow: ellipsis; overflow-wrap:anywhere; word-break: break-word; background:#fff; }
    .table th { color:#3d4d66; font-weight:700; background: #f7faff; border-top:0; }
    .table tbody tr:nth-child(even) td { background:#fbfdff; }
    .table .ops { white-space: nowrap; }
    /* Prescreen preview table: keep key columns readable and let long text wrap. */
    .prescreen-table th:nth-child(1), .prescreen-table td:nth-child(1) { width: 30%; white-space: normal; }
    .prescreen-table th:nth-child(2), .prescreen-table td:nth-child(2) { width: 14%; white-space: nowrap; }
    .prescreen-table th:nth-child(3), .prescreen-table td:nth-child(3) { width: 10%; white-space: nowrap; }
    .prescreen-table th:nth-child(4), .prescreen-table td:nth-child(4) { width: 12%; white-space: nowrap; }
    .prescreen-table th:nth-child(5), .prescreen-table td:nth-child(5) { width: 34%; white-space: normal; }
    .prescreen-table td:nth-child(4) { text-align: right; }
    .psList { margin:8px 0 0; padding:0; list-style:none; }
    .psList li { display:block; padding:8px 0; border-top:1px dashed #eee; }
    .psTop { display:flex; gap:8px; align-items:center; }
    .psBottom { margin-top:4px; display:flex; gap:8px; align-items:flex-start; flex-wrap:wrap; }
    .psBottom .meta { line-height: 1.25; }
    .psKey { color: #3a2a22; background:#fff; border:1px solid var(--line); border-radius:999px; padding:2px 6px; font-size:11px; }
    .donutWrap { display:flex; gap:14px; align-items:center; flex-wrap:wrap; margin-top:10px; }
    .donut { width: 110px; height: 110px; border-radius: 50%;
             background: conic-gradient(#3a9c62 calc(var(--p,0)*1%), #f1e8de 0);
             position: relative; border: 1px solid var(--line); }
    .donut::after { content:""; position:absolute; inset: 14px; background: var(--card); border-radius: 50%; border: 1px solid #f3efe9; }
    .donutLabel { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; flex-direction:column; font-size:12px; z-index:2; }
    .legend { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    .dot { width:10px; height:10px; border-radius:50%; display:inline-block; border:1px solid rgba(0,0,0,.08); }
    .dot.pub { background:#3a9c62; }
    .dot.unpub { background:#f1e8de; }
    .dot.warn { background:#f6c254; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 11px; }
    @media (max-width: 1260px) { .appLayout { grid-template-columns: 1fr; margin-left: 0; padding: 10px; } .assistCol .card { position: static; } .sideNav { position: static; width: auto; border:1px solid var(--line); border-radius: 12px; } }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    .workTop { display:flex; gap:10px; align-items:center; margin-top:10px; }
    .searchBox { flex: 1; display:flex; align-items:center; gap:8px; background:#fff; border:1px solid var(--line); border-radius:12px; padding:8px 10px; }
    .searchBox input { border:0; outline:0; width:100%; font-size:12px; color:#334155; background:transparent; }
    .chips { display:flex; gap:8px; flex-wrap:wrap; }
    .chip { font-size:12px; padding:6px 10px; border:1px solid #d8e4fb; border-radius:999px; background:#f6f9ff; color:#2f4e8f; }
    .assistCol .card { background:#f9fbff; }
  </style>
</head>
<body>
  <div class="appLayout">
    <aside class="sideNav">
      <h2>内容中台</h2>
      <div class="meta">小红书内容生成工具🔧</div>
      <a class="{% if tab == 'overview' %}active{% endif %}" href="/legacy?tab=overview"><span>◻</span><span>概览</span></a>
      <a class="{% if tab == 'local' %}active{% endif %}" href="/legacy?tab=local&q={{ q }}&published={{ published }}"><span>◻</span><span>本地执行记录</span></a>
      <a class="{% if tab == 'xhs' %}active{% endif %}" href="/legacy?tab=xhs&q={{ q }}&xhs_published={{ xhs_published }}&xhs_missing={{ xhs_missing }}"><span>◻</span><span>小红书笔记库</span></a>
      <a class="{% if tab == 'prescreen' %}active{% endif %}" href="/legacy?tab=prescreen"><span>◻</span><span>选题库初筛</span></a>
      <a class="{% if tab == 'analysis' %}active{% endif %}" href="/legacy?tab=analysis"><span>◻</span><span>爆款分析</span></a>
      <a href="/deconstruct" style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px;color:var(--color-blue);font-weight:600"><span>🆕</span><span>拆文中心</span></a>
      <a href="/" style="color:var(--color-blue);font-weight:600"><span>🆕</span><span>新版工具</span></a>
    </aside>
    <div class="contentCol">
      <header>
        <h1>{% if tab == 'overview' %}全局概览{% elif tab == 'local' %}本地执行记录{% elif tab == 'xhs' %}小红书笔记库{% elif tab == 'prescreen' %}选题库初筛{% elif tab == 'analysis' %}爆款分析{% else %}小红书内容生成工具{% endif %}</h1>
        <div class="meta">目标：每个页面只完成一个主任务，避免信息堆叠 | build: 2026-03-05-workbench-v1</div>
        <div class="workTop">
          <div class="searchBox">
            <span>🔍</span>
            <input value="{{ q }}" placeholder="Search..." readonly />
          </div>
          <div class="chips">
            <span class="chip">This week</span>
            <span class="chip">Connect</span>
            <span class="chip">Event</span>
          </div>
        </div>
        {% if tab == 'overview' %}
          <div class="primaryAction"><a class="btn" href="/legacy?tab=xhs&xhs_missing=any&xhs_published=no">先处理缺项内容</a><span class="meta">优先补齐缺项并完成发布闭环。</span></div>
        {% elif tab == 'local' %}
          <div class="primaryAction"><a class="btn" href="/legacy?tab=local&published=no">查看未发布任务</a><span class="meta">先完成未发布内容处理。</span></div>
        {% elif tab == 'xhs' %}
          <div class="primaryAction"><a class="btn" href="/legacy?tab=xhs&xhs_missing=any">处理缺项记录</a><span class="meta">从缺项记录进入重生与采纳流程。</span></div>
        {% elif tab == 'prescreen' %}
          <div class="primaryAction"><a class="btn" href="#prescreen-main">开始抓取</a><span class="meta">先配置参数，再提交抓取任务。</span></div>
        {% elif tab == 'analysis' %}
          <div class="primaryAction"><a class="btn" href="#analysis-main">上传统计表</a><span class="meta">先上传数据，再生成周报。</span></div>
        {% endif %}
	      {% if tab != 'overview' and tab != 'prescreen' and tab != 'analysis' %}
	      <form class="toolbar" method="get" action="/">
      <input type="hidden" name="tab" value="{{ tab }}" />
      <input class="input" name="q" value="{{ q }}" placeholder="搜索作品/作者" />
      {% if tab == 'local' %}
      <select class="select" name="published">
        <option value="all" {% if published == 'all' %}selected{% endif %}>全部</option>
        <option value="yes" {% if published == 'yes' %}selected{% endif %}>已发布</option>
        <option value="no" {% if published == 'no' %}selected{% endif %}>未发布</option>
      </select>
      {% elif tab == 'xhs' %}
      <select class="select" name="xhs_published">
        <option value="all" {% if xhs_published == 'all' %}selected{% endif %}>全部</option>
        <option value="yes" {% if xhs_published == 'yes' %}selected{% endif %}>已发布</option>
        <option value="no" {% if xhs_published == 'no' %}selected{% endif %}>未发布</option>
      </select>
      <select class="select" name="xhs_missing">
        <option value="all" {% if xhs_missing == 'all' %}selected{% endif %}>不筛缺项</option>
        <option value="any" {% if xhs_missing == 'any' %}selected{% endif %}>任一缺项</option>
        <option value="prompt" {% if xhs_missing == 'prompt' %}selected{% endif %}>缺提示词</option>
        <option value="image" {% if xhs_missing == 'image' %}selected{% endif %}>缺配图</option>
        <option value="md" {% if xhs_missing == 'md' %}selected{% endif %}>缺MD附件</option>
      </select>
      {% endif %}
      <button class="btn" type="submit">筛选</button>
    </form>
    {% endif %}
      </header>
      <div class="wrap">
    {% if tab == 'xhs' %}
      <div class="card subtle">
        <div class="sectionTitle">操作路径</div>
        <div class="meta">① 先筛选缺项记录 ② 进入预览页重生候选 ③ 对比后采纳并回写飞书</div>
      </div>
    {% elif tab == 'local' %}
      <div class="card subtle">
        <div class="sectionTitle">操作路径</div>
        <div class="meta">① 查看最近失败/未发布 ② 进入预览抽检 ③ 标记发布并追踪回填</div>
      </div>
    {% elif tab == 'prescreen' %}
      <div class="card subtle">
        <div class="sectionTitle">操作路径</div>
        <div class="meta">① 配置抓取参数 ② 提交任务 ③ 查看任务状态 ④ 检查最近写入结果</div>
      </div>
    {% elif tab == 'analysis' %}
      <div class="card subtle">
        <div class="sectionTitle">操作路径</div>
        <div class="meta">① 上传统计表 ② 观察任务结果 ③ 生成周报并同步爆款因子</div>
      </div>
    {% endif %}
    {% if tab == 'xhs' and xhs_banner %}
      <div class="banner {% if xhs_banner.kind == 'ok' %}ok{% else %}err{% endif %}">{{ xhs_banner.text }}</div>
    {% endif %}
    {% if tab == 'prescreen' %}
      {% if prescreen_banner %}
        <div class="banner {% if prescreen_banner.kind == 'ok' %}ok{% else %}err{% endif %}">{{ prescreen_banner.text }}</div>
      {% endif %}
      <div class="grid">
        <div class="card" id="prescreen-main">
          <strong>选题库-初筛 抓取</strong>
          <div class="meta" style="margin-top:6px;">写入飞书“选题库-初筛”。支持：按排行抓取；按类型/关键词搜索（末世、种田等）</div>
          <form method="post" action="/prescreen/fetch" style="margin-top:10px;">
            <div class="formRow">
              <span class="label">模式</span>
              <select class="select" name="mode">
                <option value="rank" {% if ps_mode == 'rank' %}selected{% endif %}>按排行抓取</option>
                <option value="search" {% if ps_mode == 'search' %}selected{% endif %}>按类型搜索</option>
              </select>
              <span class="label">平台</span>
              <select class="select" name="sources">
                <option value="fanqie,jjwxc" {% if ps_sources == 'fanqie,jjwxc' %}selected{% endif %}>番茄 + 晋江</option>
                <option value="fanqie" {% if ps_sources == 'fanqie' %}selected{% endif %}>仅番茄</option>
                <option value="jjwxc" {% if ps_sources == 'jjwxc' %}selected{% endif %}>仅晋江</option>
              </select>
            </div>
	            <div class="formRow">
	              <span class="label">类型/关键词</span>
	              <input class="input psQuery" name="query" value="{{ ps_query }}" placeholder="例：末世 / 种田（仅按类型搜索生效）" />
	              <span class="label">抓取数量</span>
	              <input class="input mono psLimit" name="limit" value="{{ ps_limit }}" />
	              <span class="label">批次标记</span>
	              <input class="input mono psBatch" name="batch" value="{{ ps_batch }}" />
	              <label class="meta psCheck"><input type="checkbox" name="dry_run" value="1" {% if ps_dry_run %}checked{% endif %}/> 仅预演(dry-run)</label>
	              <button class="btn psBtn" type="submit">开始抓取</button>
	            </div>
          </form>
          <div class="meta" style="margin-top:10px;">
            <div><span class="tag">抓取数量</span> 每个平台最多拉取多少条候选（越大越慢）。</div>
            <div><span class="tag">批次标记</span> 会写入飞书字段“抓取批次”，方便你在飞书里筛选/回滚。</div>
            <div><span class="tag">仅预演</span> 不写飞书，只跑抓取与字段填充校验。</div>
            <div style="margin-top:6px;">备注：晋江“按类型搜索”走官方搜索 AJAX；番茄暂用“排行池筛选（标题/简介/标签命中关键词）”兜底。</div>
          </div>
        </div>
        <div class="card" id="analysis-main">
          <strong>任务状态</strong>
          <div class="meta" style="margin-top:6px;">队列：<code>logs/prescreen_web_jobs.jsonl</code> | 结果：<code>logs/prescreen_web_job_results.jsonl</code></div>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">jobs_total: {{ prescreen_jobs.total }}</span>
            <span class="pill">running: {{ prescreen_jobs.running }}</span>
            <span class="pill">queued: {{ prescreen_jobs.queued }}</span>
          </div>
          <ul class="psList">
            {% for j in prescreen_jobs.latest %}
              <li>
                <span class="tag {% if j.status == 'done' and j.ok %}ok{% elif j.status == 'done' and not j.ok %}err{% endif %}">{{ j.status }}</span>
                <div class="psTop">
                  <span class="meta mono">{{ j.ts or '' }}</span>
                </div>
                <div class="psBottom">
                  <span class="psKey">{{ j.mode or '' }}</span>
                  <span class="psKey">{{ j.sources or '' }}</span>
                  {% if j.query %}<span class="psKey">{{ j.query }}</span>{% endif %}
                  <span class="meta">{{ j.summary_cn or j.summary or '' }}</span>
                </div>
              </li>
            {% endfor %}
            {% if not prescreen_jobs.latest %}
              <li><span class="meta">暂无任务记录（点击“开始抓取”后这里会立刻出现 queued/running 状态）</span></li>
            {% endif %}
          </ul>
          <div style="margin-top:10px;"></div>
          <strong>最近抓取结果</strong>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">results_total: {{ prescreen_recent.total }}</span>
            <span class="pill">recent_ok: {{ prescreen_recent.ok }}</span>
            <span class="pill">recent_failed: {{ prescreen_recent.failed }}</span>
          </div>
          <ul class="psList">
            {% for r in prescreen_recent.latest %}
              <li>
                <div class="psTop">
                  <span class="tag {% if r.ok %}ok{% else %}err{% endif %}">{{ 'ok' if r.ok else 'failed' }}</span>
                  <span class="meta mono">{{ r.ts or '' }}</span>
                </div>
                <div class="psBottom">
                  <span class="psKey">{{ r.mode or '' }}</span>
                  <span class="psKey">{{ r.sources or '' }}</span>
                  {% if r.query %}<span class="psKey">{{ r.query }}</span>{% endif %}
                  <span class="meta">{{ r.summary_cn or r.summary or '' }}</span>
                </div>
              </li>
            {% endfor %}
            {% if not prescreen_recent.latest %}
              <li><span class="meta">暂无结果（任务还在跑时这里会为空，优先看上方“任务状态”）</span></li>
            {% endif %}
          </ul>
        </div>
      </div>
      <div class="card">
        <strong>最近写入的初筛作品（示例预览）</strong>
        <div class="meta" style="margin-top:6px;">从飞书“选题库-初筛”读取（缓存 {{ prescreen_latest_cache_sec }}s）</div>
        {% if prescreen_latest_err %}
          <div class="banner err" style="margin-top:10px;">读取失败：{{ prescreen_latest_err }}</div>
        {% endif %}
        {% if prescreen_latest_rows %}
          <table class="table prescreen-table">
            <thead>
              <tr>
                <th>作品</th>
                <th>平台</th>
                <th>完结</th>
                <th>热度</th>
                <th>简介</th>
              </tr>
            </thead>
            <tbody>
              {% for it in prescreen_latest_rows %}
                <tr>
                  <td>
                    <div><strong>{{ it.title }}</strong> <span class="meta">by {{ it.author }}</span></div>
                    {% if it.link %}
                      <div class="meta"><a href="{{ it.link }}" target="_blank">打开作品链接</a></div>
                    {% endif %}
                    {% if it.batch %}
                      <div class="meta">批次：<span class="mono">{{ it.batch }}</span></div>
                    {% endif %}
                  </td>
                  <td><span class="tag">{{ it.platform }}</span> {% if it.type %}<span class="meta">{{ it.type }}</span>{% endif %}</td>
                  <td><span class="tag">{{ it.finish }}</span></td>
                  <td class="mono" title="{{ it.heat_raw }}">{{ it.heat_disp }}</td>
                  <td class="meta">{{ it.desc }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        {% else %}
          <div class="meta" style="margin-top:10px;">暂无数据（通常是飞书表还没写入，或权限/配置未生效）。</div>
        {% endif %}
      </div>
    {% endif %}
    {% if tab == 'analysis' %}
      {% if analysis_banner %}
        <div class="banner {% if analysis_banner.kind == 'ok' %}ok{% else %}err{% endif %}">{{ analysis_banner.text }}</div>
      {% endif %}
      <div class="grid">
        <div class="card">
          <strong>统计表上传（笔记结果库）</strong>
          <div class="meta" style="margin-top:6px;">上传创作者平台导出的 xlsx，自动清洗并写入“笔记结果库”（支持仅预演）</div>
          <form method="post" action="/analysis/upload" enctype="multipart/form-data" style="margin-top:10px;">
            <div class="formRow">
              <span class="label">账号名</span>
              <input class="input" name="account_name" value="{{ analysis_account_name }}" placeholder="例：主账号" />
              <span class="label">恢复日期</span>
              <input class="input mono" name="recovery_date" value="{{ analysis_recovery_date }}" placeholder="YYYY-MM-DD" />
              <span class="label">批次</span>
              <input class="input mono" name="batch" value="{{ analysis_batch }}" />
            </div>
            <div class="formRow">
              <span class="label">实验ID</span>
              <input class="input mono" name="experiment_id" value="{{ analysis_experiment_id }}" placeholder="可选：exp_YYYYMMDD_xx" />
              <span class="label">版本</span>
              <select class="select" name="experiment_version">
                <option value="NA" {% if analysis_experiment_version == 'NA' %}selected{% endif %}>NA</option>
                <option value="A" {% if analysis_experiment_version == 'A' %}selected{% endif %}>A</option>
                <option value="B" {% if analysis_experiment_version == 'B' %}selected{% endif %}>B</option>
              </select>
              <span class="label">实验变量</span>
              <input class="input" name="experiment_variable" value="{{ analysis_experiment_variable }}" placeholder="例：标题钩子" />
            </div>
            <div class="formRow">
              <span class="label">统计表(xlsx)</span>
              <input class="input" type="file" name="xlsx_file" accept=".xlsx" required />
              <label class="meta psCheck"><input type="checkbox" name="dry_run" value="1" {% if analysis_dry_run %}checked{% endif %}/> 仅预演(dry-run)</label>
              <label class="meta psCheck"><input type="checkbox" name="write_feishu" value="1" {% if analysis_write_feishu %}checked{% endif %}/> 写入飞书</label>
              <button class="btn psBtn" type="submit">开始上传</button>
            </div>
          </form>
          <div class="meta" style="margin-top:10px;">
            <div><span class="tag">仅预演</span> 跑解析与字段映射校验，不写飞书。</div>
            <div><span class="tag">写入飞书</span> 写入 `.env` 中配置的 `FEISHU_NOTE_METRICS_TABLE_ID`。</div>
          </div>
          <hr style="border:0; border-top:1px dashed #eee; margin:14px 0;" />
          <strong>7日观看快照上传（账号层）</strong>
          <div class="meta" style="margin-top:6px;">上传“近7日观看数据.xlsx”，写入“账号7日快照”表，用于账号趋势分析</div>
          <form method="post" action="/analysis/account7d_upload" enctype="multipart/form-data" style="margin-top:10px;">
            <div class="formRow">
              <span class="label">账号名</span>
              <input class="input" name="account_name" value="{{ account7d_account_name }}" placeholder="例：主账号" />
              <span class="label">快照日期</span>
              <input class="input mono" name="snapshot_date" value="{{ account7d_snapshot_date }}" placeholder="YYYY-MM-DD" />
              <span class="label">批次</span>
              <input class="input mono" name="batch" value="{{ account7d_batch }}" />
            </div>
            <div class="formRow">
              <span class="label">7日统计表(xlsx)</span>
              <input class="input" type="file" name="xlsx_file" accept=".xlsx" required />
              <label class="meta psCheck"><input type="checkbox" name="dry_run" value="1" {% if account7d_dry_run %}checked{% endif %}/> 仅预演(dry-run)</label>
              <label class="meta psCheck"><input type="checkbox" name="write_feishu" value="1" {% if account7d_write_feishu %}checked{% endif %}/> 写入飞书</label>
              <button class="btn psBtn" type="submit">开始上传</button>
            </div>
          </form>
          <div class="meta" style="margin-top:10px;">
            <div><span class="tag">目标表</span> `.env` 的 `FEISHU_ACCOUNT_7D_TABLE_ID`</div>
          </div>
          <hr style="border:0; border-top:1px dashed #eee; margin:14px 0;" />
          <strong>周报生成（爆款基因）</strong>
          <div class="meta" style="margin-top:6px;">基于“笔记结果库”或本地缓存生成周报，可选同步到“爆款因子库”</div>
          <form method="post" action="/analysis/report" style="margin-top:10px;">
            <div class="formRow">
              <span class="label">统计天数</span>
              <input class="input mono psLimit" name="days" value="{{ report_days }}" />
              <span class="label">最小曝光阈值</span>
              <input class="input mono psLimit" name="min_exposure" value="{{ report_min_exposure }}" />
              <span class="label">实验ID</span>
              <input class="input mono" name="experiment_id" value="{{ report_experiment_id }}" placeholder="留空=全量样本" />
              <label class="meta psCheck"><input type="checkbox" name="sync_factors" value="1" {% if report_sync_factors %}checked{% endif %}/> 同步因子到飞书</label>
              <button class="btn psBtn" type="submit">生成周报</button>
            </div>
          </form>
          <div class="meta" style="margin-top:10px;">
            <div><span class="tag">周报目录</span> <code>{{ analysis_report_dir }}</code></div>
            <div><span class="tag">最新周报</span> {% if latest_report.path %}<code>{{ latest_report.path }}</code>{% else %}暂无{% endif %}</div>
          </div>
        </div>
        <div class="card">
          <strong>分析任务状态</strong>
          <div class="meta" style="margin-top:6px;">队列：<code>logs/analysis_web_jobs.jsonl</code> | 结果：<code>logs/analysis_web_results.jsonl</code></div>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">jobs_total: {{ analysis_jobs.total }}</span>
            <span class="pill">running: {{ analysis_jobs.running }}</span>
            <span class="pill">queued: {{ analysis_jobs.queued }}</span>
          </div>
          <ul class="psList">
            {% for j in analysis_jobs.latest %}
              <li>
                <span class="tag {% if j.status == 'done' and j.ok %}ok{% elif j.status == 'done' and not j.ok %}err{% endif %}">{{ j.status }}</span>
                <div class="psTop"><span class="meta mono">{{ j.ts or '' }}</span></div>
                <div class="psBottom">
                  <span class="psKey">{{ j.kind or '' }}</span>
                  <span class="meta">{{ j.summary or '' }}</span>
                </div>
              </li>
            {% endfor %}
            {% if not analysis_jobs.latest %}
              <li><span class="meta">暂无分析任务记录</span></li>
            {% endif %}
          </ul>
          <div style="margin-top:10px;"></div>
          <strong>最近任务结果</strong>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">results_total: {{ analysis_recent.total }}</span>
            <span class="pill">recent_ok: {{ analysis_recent.ok }}</span>
            <span class="pill">recent_failed: {{ analysis_recent.failed }}</span>
          </div>
          <ul class="psList">
            {% for r in analysis_recent.latest %}
              <li>
                <div class="psTop">
                  <span class="tag {% if r.ok %}ok{% else %}err{% endif %}">{{ 'ok' if r.ok else 'failed' }}</span>
                  <span class="meta mono">{{ r.ts or '' }}</span>
                </div>
                <div class="psBottom">
                  <span class="psKey">{{ r.kind or '' }}</span>
                  <span class="meta">{{ r.summary or '' }}</span>
                </div>
              </li>
            {% endfor %}
            {% if not analysis_recent.latest %}
              <li><span class="meta">暂无结果</span></li>
            {% endif %}
          </ul>
        </div>
      </div>
      <div class="card">
        <strong>周报预览</strong>
        <div class="meta" style="margin-top:6px;">可在这里直接查看最近生成的 Markdown 周报</div>
        {% if latest_report.path %}
          <div class="meta" style="margin-top:8px;">文件：<code>{{ latest_report.path }}</code></div>
          <pre style="white-space: pre-wrap; word-break: break-word; margin-top:10px;">{{ latest_report.content }}</pre>
        {% else %}
          <div class="meta" style="margin-top:10px;">暂无周报，请先点击“生成周报”。</div>
        {% endif %}
      </div>
    {% endif %}
    {% if tab == 'overview' and overview %}
      <div class="grid">
        <div class="card">
          <strong>小红书笔记库发布概览</strong>
          <div class="meta" style="margin-top:6px;">来源：飞书“小红书笔记库”表（缓存 {{ overview.cache_sec }}s）</div>
          <div class="donutWrap">
            <div class="donut" style="--p: {{ overview.xhs_publish_rate_pct }};">
              <div class="donutLabel">
                <div style="font-size:18px; font-weight:700;">{{ overview.xhs_publish_rate_pct }}%</div>
                <div class="meta">已发布</div>
              </div>
            </div>
            <div>
              <div class="kpi">
                <span class="pill">任务总数(飞书): {{ overview.xhs_total }}</span>
                <span class="pill">已发布: {{ overview.xhs_published }}</span>
                <span class="pill">未发布: {{ overview.xhs_unpublished }}</span>
              </div>
              <div class="kpi" style="margin-top:10px;">
                <span class="pill">提示词齐全(5/5): {{ overview.xhs_prompt_complete }}</span>
                <span class="pill">配图齐全(5/5): {{ overview.xhs_image_complete }}</span>
                <span class="pill">缺MD附件: {{ overview.xhs_md_missing }}</span>
              </div>
              <div class="legend" style="margin-top:10px;">
                <span class="meta"><span class="dot pub"></span> 已发布</span>
                <span class="meta"><span class="dot unpub"></span> 未发布</span>
              </div>
              {% if overview.xhs_err %}
                <div class="banner err" style="margin-top:10px;">飞书统计失败：{{ overview.xhs_err }}</div>
              {% endif %}
            </div>
          </div>
        </div>
        <div class="card">
          <strong>选题库概览</strong>
          <div class="meta" style="margin-top:6px;">来源：飞书“选题库”与“选题库-初筛”表（缓存 {{ overview.topic_cache_sec }}s）</div>
          <div class="donutWrap">
            <div>
              <div class="meta">选题库（以“是否拆解/是否入库”等字段计数）</div>
              <div class="donut" style="--p: {{ overview.topic_rate_pct }};">
                <div class="donutLabel">
                  <div style="font-size:18px; font-weight:700;">{{ overview.topic_rate_pct }}%</div>
                  <div class="meta">已处理</div>
                </div>
              </div>
              <div class="kpi" style="margin-top:10px;">
                <span class="pill">总量: {{ overview.topic_total }}</span>
                <span class="pill">已处理: {{ overview.topic_yes }}</span>
                <span class="pill">未处理: {{ overview.topic_no }}</span>
              </div>
              {% if overview.topic_err %}
                <div class="banner err" style="margin-top:10px;">选题库统计失败：{{ overview.topic_err }}</div>
              {% endif %}
            </div>
            <div>
              <div class="meta">选题库-初筛（以“是否入库/是否通过”等字段计数）</div>
              <div class="donut" style="--p: {{ overview.prescreen_rate_pct }};">
                <div class="donutLabel">
                  <div style="font-size:18px; font-weight:700;">{{ overview.prescreen_rate_pct }}%</div>
                  <div class="meta">已入库</div>
                </div>
              </div>
              <div class="kpi" style="margin-top:10px;">
                <span class="pill">总量: {{ overview.prescreen_total }}</span>
                <span class="pill">已入库: {{ overview.prescreen_yes }}</span>
                <span class="pill">未入库: {{ overview.prescreen_no }}</span>
              </div>
              {% if overview.prescreen_err %}
                <div class="banner err" style="margin-top:10px;">初筛统计失败：{{ overview.prescreen_err }}</div>
              {% endif %}
            </div>
          </div>
          <div class="legend" style="margin-top:10px;">
            <span class="meta"><span class="dot pub"></span> 已处理/已入库</span>
            <span class="meta"><span class="dot unpub"></span> 未处理/未入库</span>
          </div>
        </div>
        <div class="card">
          <strong>执行与队列</strong>
          <div class="meta" style="margin-top:6px;">来源：<code>logs/records.jsonl</code> 与队列日志</div>
          <div class="kpi" style="margin-top:10px;">
            <span class="pill">本地执行记录: {{ overview.local_tasks_total }}</span>
            <span class="pill">本地标记发布: {{ overview.local_tasks_published }}</span>
            <span class="pill">生图 jobs_total: {{ overview.queue.jobs_total }}</span>
            <span class="pill">生图 pending_unique: {{ overview.queue.pending_unique }}</span>
          </div>
          <div class="kpi" style="margin-top:10px;">
            <span class="pill">回填成功(近200): {{ overview.queue.recent_ok }}</span>
            <span class="pill">回填失败(近200): {{ overview.queue.recent_failed }}</span>
          </div>
        </div>
      </div>
      <div class="card">
        <strong>建议关注</strong>
        <ul class="list" style="margin-top:8px;">
          <li><span class="tag">待发布</span> <span class="meta">优先处理“未发布”数量高的作品，避免重复生成与重复回填。</span></li>
          <li><span class="tag">队列</span> <span class="meta">若 pending_unique 长期不降，优先检查 worker 是否在跑，以及最近失败原因。</span></li>
          <li><span class="tag">质量</span> <span class="meta">发布前抽检“提示词/笔记初稿/配图一致性”，再手动改为“是”。</span></li>
        </ul>
      </div>
    {% endif %}
    {% if tab == 'local' and queue %}
      <div class="grid">
        <div class="card">
          <strong>生图队列状态</strong>
          <div class="meta" style="margin-top:6px;">从 <code>logs/image_jobs.jsonl</code> 与 <code>logs/image_jobs.cursor</code> 估算</div>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">jobs_total: {{ queue.jobs_total }}</span>
            <span class="pill">pending_unique: {{ queue.pending_unique }}</span>
            <span class="pill">cursor_pos: {{ queue.cursor_pos }}</span>
          </div>
        </div>
        <div class="card">
          <strong>最近回填结果</strong>
          <div class="meta" style="margin-top:6px;">读取 <code>logs/image_job_results.jsonl</code></div>
          <div class="kpi" style="margin-top:8px;">
            <span class="pill">results_total: {{ queue.results_total }}</span>
            <span class="pill">recent_ok: {{ queue.recent_ok }}</span>
            <span class="pill">recent_failed: {{ queue.recent_failed }}</span>
          </div>
          <ul class="list">
            {% for r in queue.latest %}
              <li>
                {% set st = (r.status or '') %}
                <span class="tag {% if 'updated' in st %}ok{% elif 'failed' in st %}err{% endif %}">{{ st or 'unknown' }}</span>
                <span class="meta" style="min-width:140px;">{{ r.ts or '' }}</span>
                <span class="meta" style="min-width:160px;">{{ r.work_name or r.xhs_record_id or '' }}</span>
              </li>
            {% endfor %}
            {% if not queue.latest %}
              <li><span class="meta">暂无回填结果</span></li>
            {% endif %}
          </ul>
        </div>
      </div>
    {% endif %}
    {% if tab == 'local' and summary %}
      {% if summary.status == 'success' %}
        <div class="banner ok">最近一次运行成功：{{ summary.work_name }}（{{ summary.run_date }}） | 耗时 {{ summary.durations_sec.total }}s</div>
      {% else %}
        <div class="banner err">最近一次运行失败：{{ summary.errors[0].error if summary.errors else '未知错误' }}</div>
      {% endif %}
    {% endif %}

    {% if tab == 'local' or tab == 'xhs' %}
    <div class="card subtle">
      <div class="sectionTitle">记录列表（表格视图）</div>
      <div class="meta">{% if tab == 'local' %}按执行记录查看任务状态与发布进度。{% else %}按飞书笔记库查看缺项与发布状态。{% endif %}</div>
    </div>
    <div class="card">
    {% if items %}
      {% if tab == 'local' %}
      <table class="table">
        <thead>
          <tr>
            <th style="width:24%;">作品</th>
            <th style="width:18%;">运行时间</th>
            <th style="width:14%;">状态</th>
            <th style="width:28%;">文件</th>
            <th style="width:16%;">操作</th>
          </tr>
        </thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td><strong>{{ item.work_name }}</strong><div class="meta">{{ item.author }}</div></td>
            <td class="mono">{{ item.run_date }}</td>
            <td>
              <span class="tag {% if item.published %}ok{% else %}warn{% endif %}">{{ '已发布' if item.published else '未发布' }}</span>
              <div class="meta">record_id: {{ item.record_id or '未同步' }}</div>
            </td>
            <td>
              <div class="meta"><a class="path" href="file://{{ item.report_path }}">拆解报告</a></div>
              <div class="meta"><a class="path" href="file://{{ item.xhs_path }}">小红书笔记</a></div>
            </td>
            <td class="ops">
              <a class="btn secondary" href="{{ url_for('preview', idx=item._idx) }}" style="display:inline-block; text-decoration:none;">预览</a>
              <form method="post" action="/publish" style="margin-top:6px;">
                <input type="hidden" name="record_id" value="{{ item.record_id or '' }}" />
                <input type="hidden" name="work_name" value="{{ item.work_name }}" />
                <input type="hidden" name="author" value="{{ item.author }}" />
                <button class="btn" type="submit">标记发布</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <table class="table">
        <thead>
          <tr>
            <th style="width:22%;">作品</th>
            <th style="width:16%;">更新时间</th>
            <th style="width:26%;">完整度</th>
            <th style="width:14%;">发布</th>
            <th style="width:22%;">操作</th>
          </tr>
        </thead>
        <tbody>
          {% for item in items %}
          <tr>
            <td><strong>{{ item.work_name }}</strong><div class="meta">{{ item.author }}</div><div class="meta mono">{{ item.xhs_record_id }}</div></td>
            <td class="mono">{{ item.update_time or '-' }}</td>
            <td>
              <div class="meta">提示词 {{ item.prompt_ok }}/5 · 图片 {{ item.image_ok }}/5 · MD {{ '有' if item.md_ok else '无' }}</div>
              {% if item.prompt_ok < 5 or item.image_ok < 5 or (not item.md_ok) %}
                <span class="tag err">缺项</span> <span class="meta">{{ item.missing_text }}</span>
              {% else %}
                <span class="tag ok">齐全</span>
              {% endif %}
            </td>
            <td><span class="tag {% if item.published %}ok{% else %}warn{% endif %}">{{ '已发布' if item.published else '未发布' }}</span></td>
            <td class="ops">
              <a class="btn secondary" href="{{ url_for('xhs_preview', rid=item.xhs_record_id) }}" style="display:inline-block; text-decoration:none;">预览</a>
              <form method="post" action="/xhs/publish" style="margin-top:6px;">
                <input type="hidden" name="xhs_record_id" value="{{ item.xhs_record_id }}" />
                <input type="hidden" name="published" value="{{ '0' if item.published else '1' }}" />
                <button class="btn" type="submit">{{ '取消发布' if item.published else '标记发布' }}</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% endif %}
      <div class="pager">
        {% if pager.prev_url %}<a class="btn secondary" href="{{ pager.prev_url }}" style="text-decoration:none;">上一页</a>{% endif %}
        <span class="meta">{{ pager.label }}</span>
        {% if pager.next_url %}<a class="btn secondary" href="{{ pager.next_url }}" style="text-decoration:none;">下一页</a>{% endif %}
      </div>
    {% else %}
      <div class="meta">暂无数据</div>
    {% endif %}
    </div>
    {% endif %}
      </div>
    </div>
    <aside class="assistCol">
      <div class="card">
        <strong>辅助信息区</strong>
        <div class="meta" style="margin-top:6px;">当前页面：{{ tab }}</div>
        {% if tab == 'overview' and overview %}
          <div class="meta" style="margin-top:8px;">任务总数：{{ overview.xhs_total }} | 已发布：{{ overview.xhs_published }}</div>
        {% elif tab == 'local' and summary %}
          <div class="meta" style="margin-top:8px;">最近运行：{{ summary.status }} | {{ summary.work_name }}</div>
        {% elif tab == 'xhs' %}
          <div class="meta" style="margin-top:8px;">建议先筛选“缺项=任一缺项”，再进入预览执行重生。</div>
        {% elif tab == 'prescreen' %}
          <div class="meta" style="margin-top:8px;">提交后先看“任务状态”里的 queued/running/done。</div>
        {% elif tab == 'analysis' %}
          <div class="meta" style="margin-top:8px;">上传完成后先看任务状态，再决定是否生成周报。</div>
        {% else %}
          <div class="meta" style="margin-top:8px;">选择左侧导航开始操作。</div>
        {% endif %}
      </div>
    </aside>
  </div>
</body>
</html>
"""

PREVIEW_TEMPLATE = """
<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>图文笔记预览</title>
  <style>
    :root { --bg:#f7f5f2; --fg:#222; --card:#fff; --accent:#c24d2c; }
    body { font-family: "Noto Serif SC", serif; background: var(--bg); color: var(--fg); margin: 0; }
    .wrap { padding: 20px; max-width: 1100px; margin: 0 auto; }
    .card { background: var(--card); border: 1px solid #eee; border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .btn { background: var(--accent); color: #fff; border: 0; padding: 8px 12px; border-radius: 8px; cursor: pointer; }
    pre { white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
    .meta { color: #666; font-size: 12px; margin-bottom: 8px; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"card\">
      <div class=\"meta\">{{ item.work_name }} - {{ item.author }} | {{ item.run_date }}</div>
      <button class=\"btn\" onclick=\"copyNote()\">复制正文</button>
      <button class=\"btn\" onclick=\"copyPrompts()\" style=\"margin-left:8px;\">复制配图提示词</button>
      <button class=\"btn\" onclick=\"copyAll()\" style=\"margin-left:8px;\">一键复制图文</button>
      <a class=\"btn\" href=\"{{ url_for('index') }}\" style=\"text-decoration:none; margin-left:8px;\">返回列表</a>
    </div>
    <div class=\"card\">
      <h3>图文笔记预览</h3>
      <pre id=\"content\">{{ content }}</pre>
      <pre id=\"note\" style=\"display:none;\">{{ note_text }}</pre>
      <pre id=\"prompts\" style=\"display:none;\">{{ prompts_text }}</pre>
    </div>
  </div>
  <script>
    function copyNote() {
      const text = document.getElementById('note').innerText;
      navigator.clipboard.writeText(text).then(() => alert('正文已复制'));
    }
    function copyPrompts() {
      const text = document.getElementById('prompts').innerText;
      navigator.clipboard.writeText(text).then(() => alert('提示词已复制'));
    }
    function copyAll() {
      const text = document.getElementById('content').innerText;
      navigator.clipboard.writeText(text).then(() => alert('已复制'));
    }
  </script>
</body>
</html>
"""

XHS_PREVIEW_TEMPLATE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>小红书笔记库记录</title>
  <style>
    :root { --bg:#f7f5f2; --fg:#222; --card:#fff; --accent:#c24d2c; --line:#e7dfd4; }
    body { font-family: "Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif; background: var(--bg); color: var(--fg); margin: 0; }
    .wrap { padding: 20px; max-width: 1100px; margin: 0 auto; }
    .card { background: var(--card); border: 1px solid #eee; border-radius: 14px; padding: 14px; margin-bottom: 12px; }
    .btn { background: var(--accent); color: #fff; border: 0; padding: 8px 12px; border-radius: 9px; cursor: pointer; }
    .btn.secondary { background:#fff; color:#3a2a22; border:1px solid var(--line); }
    .btn[disabled] { opacity:.65; cursor:not-allowed; }
    .banner { border-radius:10px; padding:8px 10px; margin-bottom:10px; font-size:12px; }
    .banner.ok { background:#eaf6ec; border:1px solid #b7ddbf; color:#235a2f; }
    .banner.err { background:#fdeeee; border:1px solid #f3b5b5; color:#8b1e1e; }
    pre { white-space: pre-wrap; word-break: break-word; line-height: 1.5; font-size: 12px; }
    .meta { color: #666; font-size: 12px; margin-bottom: 8px; }
    .split { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
    .input, .select, .textarea { width:100%; padding:8px 10px; border:1px solid #ddd; border-radius:8px; font-size:12px; }
    .textarea { min-height:84px; resize: vertical; }
    .row { display:flex; gap:8px; align-items:center; }
    .row > * { min-width: 0; }
    .row .col { flex: 1; }
    @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 11px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="meta">{{ title }} - {{ author }} | xhs_record_id: {{ rid }}</div>
      <button class="btn" onclick="copyNote()">复制笔记正文</button>
      <button class="btn" onclick="copyPrompts()" style="margin-left:8px;">复制配图提示词</button>
      <form method="post" action="/xhs/regen_note_preview" class="regen-form" style="display:inline; margin-left:8px;">
        <input type="hidden" name="xhs_record_id" value="{{ rid }}" />
        <button class="btn secondary regen-btn" type="submit" data-loading-text="重生中...">快速重生（默认模型）</button>
      </form>
      <form method="post" action="/xhs/regenerate" style="display:inline; margin-left:8px;">
        <input type="hidden" name="xhs_record_id" value="{{ rid }}" />
        <input type="hidden" name="part" value="prompts" />
        <button class="btn secondary" type="submit">重生提示词</button>
      </form>
      <a class="btn secondary" href="{{ back_url }}" style="text-decoration:none; margin-left:8px;">返回列表</a>
    </div>
    {% if xhs_banner %}
      <div class="banner {% if xhs_banner.kind == 'ok' %}ok{% else %}err{% endif %}">{{ xhs_banner.text }}</div>
    {% endif %}
    <div class="split">
      <div class="card">
        <h3>原始版本（当前生效）</h3>
        <div class="meta">来源：{{ note_source }}</div>
        <pre id="note">{{ note_text }}</pre>
      </div>
      <div class="card">
        <h3>候选重生版本（未写回飞书）</h3>
        <div class="meta">
          {% if candidate_note %}
            生成时间：{{ candidate_ts }} | 来源：{{ cand_gen_source or 'unknown' }}{% if cand_model_provider or cand_model_name %}（{{ cand_model_provider or 'provider' }} / {{ cand_model_name or 'default-model' }}）{% endif %}
            {% if cand_gen_error %}<span style="color:#8b1e1e;"> | 错误：{{ cand_gen_error }}</span>{% endif %}
            {% if cand_facts_main_record_id %} | 主表记录ID：{{ cand_facts_main_record_id }}{% endif %}
            {% if cand_facts_missing %}<span style="color:#8b1e1e;"> | 事实缺失：{{ cand_facts_missing|join('、') }}</span>{% endif %}
          {% else %}
            暂无候选版本，请填写下方重生条件后生成
          {% endif %}
        </div>
        <pre id="candidate_note">{% if candidate_note %}{{ candidate_note }}{% else %}（暂无候选版本）{% endif %}</pre>
        <button class="btn" onclick="copyCandidate()">复制候选版本</button>
        <form method="post" action="/xhs/adopt_note" style="display:inline; margin-left:8px;">
          <input type="hidden" name="xhs_record_id" value="{{ rid }}" />
          <button class="btn secondary" type="submit" {% if not candidate_note %}disabled{% endif %} onclick="return confirm('确认采纳当前候选版本，并更新飞书吗？');">采纳本版本并更新飞书</button>
        </form>
      </div>
    </div>
    <div class="card">
      <h3>重生设置（不满意原因 + 修改意见 + 模型）</h3>
      <form method="post" action="/xhs/regen_note_preview" class="regen-form">
        <input type="hidden" name="xhs_record_id" value="{{ rid }}" />
        <div class="row">
          <div class="col">
            <div class="meta">不满意点</div>
            <select class="select" name="dissatisfaction">
              <option value="">请选择</option>
              <option value="活人感不足/像陈述" {% if cand_dissatisfaction == '活人感不足/像陈述' %}selected{% endif %}>活人感不足/像陈述</option>
              <option value="信息密度过高/不适合手机阅读" {% if cand_dissatisfaction == '信息密度过高/不适合手机阅读' %}selected{% endif %}>信息密度过高/不适合手机阅读</option>
              <option value="剧情与原文不一致" {% if cand_dissatisfaction == '剧情与原文不一致' %}selected{% endif %}>剧情与原文不一致</option>
              <option value="种草感弱/互动弱" {% if cand_dissatisfaction == '种草感弱/互动弱' %}selected{% endif %}>种草感弱/互动弱</option>
            </select>
          </div>
          <div class="col">
            <div class="meta">模型提供方</div>
            <select class="select" name="model_provider">
              <option value="qwen" {% if cand_model_provider == 'qwen' %}selected{% endif %}>qwen</option>
              <option value="chatglm" {% if cand_model_provider == 'chatglm' %}selected{% endif %}>chatglm</option>
              <option value="deepseek" {% if cand_model_provider == 'deepseek' %}selected{% endif %}>deepseek</option>
              <option value="local" {% if cand_model_provider == 'local' %}selected{% endif %}>local(模板)</option>
            </select>
          </div>
          <div class="col">
            <div class="meta">模型名称（可手填）</div>
            <input class="input" name="model_name" value="{{ cand_model_name }}" placeholder="例：qwen-plus / qwen-max / glm-4-plus / deepseek-chat" />
          </div>
        </div>
        <div style="margin-top:8px;">
          <label class="meta"><input type="checkbox" name="allow_fallback" value="1" {% if cand_allow_fallback %}checked{% endif %}/> 模型失败时允许兜底模板（不勾选则直接报错，不产出候选）</label>
        </div>
        <div style="margin-top:10px;">
          <div class="meta">修改意见（会作为下一次重生约束）</div>
          <textarea class="textarea" name="feedback" placeholder="例：提升口语化和种草感；分段更短；保留3-4个emoji；不要大段设定复述；结尾给A/B互动提问。">{{ cand_feedback }}</textarea>
        </div>
        <div style="margin-top:10px;">
          <button class="btn regen-btn" type="submit" data-loading-text="正在重生候选版本...">按以上要求重新生成候选版本</button>
        </div>
      </form>
    </div>
    <div class="card">
      <h3>生成配图提示词</h3>
      <pre id="prompts">{{ prompts_text }}</pre>
    </div>
    <div class="card">
      <h3>字段快照</h3>
      <div class="meta">（用于排查；不包含附件内容本体）</div>
      <pre>{{ fields_json }}</pre>
    </div>
  </div>
  <script>
    function copyNote() {
      const text = document.getElementById('note').innerText;
      navigator.clipboard.writeText(text).then(() => alert('笔记正文已复制'));
    }
    function copyPrompts() {
      const text = document.getElementById('prompts').innerText;
      navigator.clipboard.writeText(text).then(() => alert('提示词已复制'));
    }
    function copyCandidate() {
      const el = document.getElementById('candidate_note');
      if (!el) return;
      const text = el.innerText;
      navigator.clipboard.writeText(text).then(() => alert('候选版本已复制'));
    }
    document.querySelectorAll('form.regen-form').forEach((form) => {
      form.addEventListener('submit', () => {
        const btn = form.querySelector('.regen-btn');
        if (!btn) return;
        btn.dataset.originText = btn.innerText;
        btn.innerText = btn.dataset.loadingText || '处理中...';
        btn.disabled = true;
      });
    });
  </script>
</body>
</html>
"""


def load_records():
    return service_load_records()


def load_run_summary():
    return service_load_run_summary()


def _safe_read_int(path):
    # Moved to scripts.web.services.local_runs and kept here only for compatibility.
    return 0


def _count_lines(path):
    # Moved to scripts.web.services.local_runs and kept here only for compatibility.
    return 0


def load_image_queue_status():
    return service_load_image_queue_status()

def load_xhs_stats_cached():
    """
    Returns (stats_dict, err_str). Uses a short in-memory cache because scanning Feishu tables can be slow.
    """
    import time as _time

    now = _time.time()
    if _XHS_STATS_CACHE["data"] is not None and (now - _XHS_STATS_CACHE["ts"]) < _XHS_STATS_CACHE_SEC:
        return _XHS_STATS_CACHE["data"], _XHS_STATS_CACHE["err"]

    client = FeishuClient()
    if not client.is_configured():
        err = "飞书未配置"
        _XHS_STATS_CACHE.update({"ts": now, "data": None, "err": err})
        return None, err
    cfg = get_feishu_config()
    table_id = cfg.get("related_table_ids", {}).get("小红书笔记库")
    if not table_id:
        err = "未配置小红书笔记库"
        _XHS_STATS_CACHE.update({"ts": now, "data": None, "err": err})
        return None, err

    try:
        field_meta = client.get_table_field_meta(table_id) or {}
        pub_meta = field_meta.get("是否发布笔记") or {}
        pub_options = (pub_meta.get("property") or {}).get("options") or []
        pub_id_to_name = {}
        for opt in pub_options:
            oid = opt.get("id") or opt.get("option_id") or opt.get("value")
            name = opt.get("name")
            if oid and name:
                pub_id_to_name[str(oid)] = str(name)

        total = 0
        published = 0
        prompt_complete = 0
        image_complete = 0
        md_missing = 0
        for it in client.iter_records(table_id, page_size=200):
            total += 1
            f = it.get("fields", {}) or {}
            raw = f.get("是否发布笔记")
            name = ""
            if isinstance(raw, str) and raw.strip():
                name = pub_id_to_name.get(raw, raw)
            if str(name).strip() == "是":
                published += 1
            p_ok = 0
            for i in range(1, 6):
                if str(f.get(f"生成配图提示词{i}", "")).strip():
                    p_ok += 1
            if p_ok >= 5:
                prompt_complete += 1
            im_ok = 0
            for i in range(1, 6):
                v = f.get(f"即梦生图{i}", [])
                if isinstance(v, list) and len(v) >= 1:
                    im_ok += 1
            if im_ok >= 5:
                image_complete += 1
            mdv = f.get("小红书笔记初稿", [])
            if not (isinstance(mdv, list) and len(mdv) >= 1):
                md_missing += 1
        unpublished = max(0, total - published)
        rate_pct = int(round((published / total) * 100)) if total else 0
        data = {
            "total": total,
            "published": published,
            "unpublished": unpublished,
            "rate_pct": rate_pct,
            "prompt_complete": prompt_complete,
            "prompt_incomplete": max(0, total - prompt_complete),
            "image_complete": image_complete,
            "image_incomplete": max(0, total - image_complete),
            "md_missing": md_missing,
        }
        _XHS_STATS_CACHE.update({"ts": now, "data": data, "err": None})
        return data, None
    except Exception as e:
        err = str(e)
        _XHS_STATS_CACHE.update({"ts": now, "data": None, "err": err})
        return None, err


def _is_truthy(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        v = value.strip()
        if v in ["", "否", "未", "未拆解", "0", "false", "False", "未入库", "未通过"]:
            return False
        if v in ["是", "已", "已拆解", "1", "true", "True", "已入库", "通过"]:
            return True
        return True
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return True
    return bool(value)


def load_yesno_stats_cached(table_name, yesno_field_candidates, cache_sec=_TOPIC_STATS_CACHE_SEC):
    """
    Count total/yes/no for a table using the first existing field in yesno_field_candidates.
    Returns (data, err). data keys: total, yes, no, rate_pct, field
    """
    import time as _time

    now = _time.time()
    hit = _TOPIC_STATS_CACHE.get(table_name)
    if hit and hit.get("data") is not None and (now - hit.get("ts", 0.0)) < cache_sec:
        return hit.get("data"), hit.get("err")

    client = FeishuClient()
    if not client.is_configured():
        err = "飞书未配置"
        _TOPIC_STATS_CACHE[table_name] = {"ts": now, "data": None, "err": err}
        return None, err
    cfg = get_feishu_config()
    table_id = (cfg.get("related_table_ids") or {}).get(table_name)
    if not table_id:
        err = f"未配置 {table_name} table_id"
        _TOPIC_STATS_CACHE[table_name] = {"ts": now, "data": None, "err": err}
        return None, err

    try:
        field_meta = client.get_table_field_meta(table_id) or {}
        field_name = None
        for cand in yesno_field_candidates:
            if cand in field_meta:
                field_name = cand
                break
        if not field_name:
            # Fall back: pick any field that looks like status.
            for cand in ["是否拆解", "是否入库", "是否通过", "状态", "审核状态"]:
                if cand in field_meta:
                    field_name = cand
                    break
        if not field_name:
            field_name = yesno_field_candidates[0] if yesno_field_candidates else "状态"

        fmeta = field_meta.get(field_name) or {}
        ftype = fmeta.get("type")
        opt_id_to_name = {}
        if ftype == 3:
            options = (fmeta.get("property") or {}).get("options") or []
            for opt in options:
                oid = opt.get("id") or opt.get("option_id") or opt.get("value")
                name = opt.get("name")
                if oid and name:
                    opt_id_to_name[str(oid)] = str(name)

        total = 0
        yes = 0
        for it in client.iter_records(table_id, page_size=200):
            total += 1
            v = (it.get("fields", {}) or {}).get(field_name)
            if ftype == 3 and isinstance(v, str) and v.strip():
                v = opt_id_to_name.get(v, v)
            if _is_truthy(v):
                yes += 1
        no = max(0, total - yes)
        rate_pct = int(round((yes / total) * 100)) if total else 0
        data = {"total": total, "yes": yes, "no": no, "rate_pct": rate_pct, "field": field_name}
        _TOPIC_STATS_CACHE[table_name] = {"ts": now, "data": data, "err": None}
        return data, None
    except Exception as e:
        err = str(e)
        _TOPIC_STATS_CACHE[table_name] = {"ts": now, "data": None, "err": err}
        return None, err


def _build_published_filter_expr(client, table_id, xhs_published):
    xhs_published = (xhs_published or "all").strip().lower()
    if xhs_published not in ["yes", "no"]:
        return None
    want = "是" if xhs_published == "yes" else "否"
    opt_id = client.resolve_single_select_option_id(table_id, "是否发布笔记", want)
    if opt_id:
        return client._build_filter_expr_and_eq({"是否发布笔记": opt_id})
    return client._build_filter_expr_and_eq({"是否发布笔记": want})


def _compute_xhs_missing(fields):
    return service_compute_xhs_missing(fields)


def _find_local_xhs_md(work_name, author):
    return service_find_local_xhs_md(work_name, author)


def _xhs_note_from_fields(fields):
    return service_xhs_note_from_fields(fields)


def _load_xhs_note_candidates():
    return service_load_xhs_note_candidates()


def _save_xhs_note_candidates(data):
    service_save_xhs_note_candidates(data)


def _find_xhs_record_by_id(client, rid):
    return service_find_xhs_record_by_id(client, rid)


def _field_contains_main_record_id(value, main_record_id):
    return service_field_contains_main_record_id(value, main_record_id)


def _find_main_record_by_id(client, main_record_id):
    return service_find_main_record_by_id(client, main_record_id)


def _collect_fact_pack(client, xhs_record):
    return service_collect_fact_pack(client, xhs_record)


def _facts_to_text(facts):
    return service_facts_to_text(facts)


def _apply_fact_overrides(analysis, facts):
    return service_apply_fact_overrides(analysis, facts)


def _start_fact_repair_async(rid, main_record_id, work):
    key = str(rid or "").strip()
    if not key:
        return
    if key in _XHS_FACT_REPAIRING:
        return
    _XHS_FACT_REPAIRING[key] = now_ts()

    def _run():
        try:
            analysis = _build_grounded_analysis(work)
            related_ids = sync_related(main_record_id, work, analysis)
            update_main_links(main_record_id, related_ids)
            append_jsonl(
                os.path.join(PATHS["logs"], "xhs_fact_repair_results.jsonl"),
                {
                    "ts": now_ts(),
                    "xhs_record_id": key,
                    "main_record_id": main_record_id,
                    "status": "done",
                    "related_ids": related_ids,
                },
            )
        except Exception as e:
            append_jsonl(
                os.path.join(PATHS["logs"], "xhs_fact_repair_results.jsonl"),
                {
                    "ts": now_ts(),
                    "xhs_record_id": key,
                    "main_record_id": main_record_id,
                    "status": "failed",
                    "error": str(e),
                },
            )
        finally:
            _XHS_FACT_REPAIRING.pop(key, None)

    threading.Thread(target=_run, daemon=True).start()


def _generate_note_candidate(work, dissatisfaction, feedback, provider, model_name, allow_fallback=True, facts=None):
    provider = (provider or "").strip().lower() or os.getenv("MODEL_PROVIDER", "qwen").strip().lower()
    model_name = (model_name or "").strip()
    dissatisfaction = (dissatisfaction or "").strip()
    feedback = (feedback or "").strip()

    work_aug = dict(work or {})
    constraints = []
    if dissatisfaction:
        constraints.append("不满意点：" + dissatisfaction)
    if feedback:
        constraints.append("修改意见：" + feedback)
    facts_text = _facts_to_text(facts or {}) if facts else ""
    if facts_text:
        constraints.append("事实约束：只允许使用事实卡，不得新增人名/事件/设定")
    if constraints:
        work_aug["重生成要求"] = "；".join(constraints)
        origin_intro = str(work_aug.get("简介", "") or "")
        pieces = [origin_intro, "【重生成要求】" + work_aug["重生成要求"]]
        if facts_text:
            pieces.append(facts_text)
        work_aug["简介"] = "\n\n".join([x for x in pieces if x]).strip()

    old_provider = os.getenv("MODEL_PROVIDER", "")
    old_openai_model = os.getenv("OPENAI_MODEL", "")
    old_qwen_model = os.getenv("QWEN_MODEL", "")
    try:
        os.environ["MODEL_PROVIDER"] = provider
        if provider in {"qwen", "dashscope"}:
            if model_name:
                os.environ["QWEN_MODEL"] = model_name
                os.environ["OPENAI_MODEL"] = model_name
        else:
            if model_name:
                os.environ["OPENAI_MODEL"] = model_name
        gen_source = "model"
        gen_error = ""
        try:
            analysis = analyze_work(work_aug)
        except Exception as e:
            gen_error = str(e)
            if not allow_fallback:
                raise
            analysis = _build_grounded_analysis(work_aug)
            gen_source = "fallback_grounded"
        if facts:
            analysis = _apply_fact_overrides(analysis, facts)
        note = _build_xhs_note_unclipped(work, analysis)
        return analysis, note, gen_source, gen_error
    finally:
        if old_provider:
            os.environ["MODEL_PROVIDER"] = old_provider
        elif "MODEL_PROVIDER" in os.environ:
            del os.environ["MODEL_PROVIDER"]
        if old_openai_model:
            os.environ["OPENAI_MODEL"] = old_openai_model
        elif "OPENAI_MODEL" in os.environ:
            del os.environ["OPENAI_MODEL"]
        if old_qwen_model:
            os.environ["QWEN_MODEL"] = old_qwen_model
        elif "QWEN_MODEL" in os.environ:
            del os.environ["QWEN_MODEL"]


def _build_xhs_note_unclipped(work, analysis):
    p = analysis.get("小红书包装", {}) or {}
    tags = p.get("热门标签推荐", [])
    if not isinstance(tags, list):
        tags = [str(tags)] if str(tags).strip() else []
    openers = analysis.get("开篇套路", []) or []
    emotions = analysis.get("情绪触发", []) or []
    quotes = analysis.get("金句", []) or []
    chars = analysis.get("人物设定", {}) or {}
    conflicts = analysis.get("冲突设计", {}) or {}

    lines = []
    lines.append(f"【标题】{p.get('小红书标题模板', work.get('作品名称', ''))}")
    lines.append("")
    lines.append("姐妹们我先说结论👇")
    lines.append(str(p.get("正文开头模板", "")).strip())
    lines.append("这本属于越看越上头、而且能聊出内容的那种。")
    lines.append("")
    lines.append("📚 作品速览")
    lines.append(f"- 书名：{work.get('作品名称', '')}")
    lines.append(f"- 作者：{work.get('作者', '')}")
    lines.append(f"- 平台：{work.get('平台', '')}")
    if str(work.get("分类", "")).strip():
        lines.append(f"- 标签：{work.get('分类', '')}")
    lines.append("")
    if str(work.get("简介", "")).strip():
        lines.append("🧾 一句话剧情")
        lines.append(f"- {str(work.get('简介', '')).strip()}")
        lines.append("")

    lines.append("✨ 核心亮点")
    lines.append("🔹 开篇抓人：先抛问题，再给反转")
    for i, item in enumerate(openers[:3], 1):
        lines.append(f"{i}. {str(item).strip()}")
    lines.append("")

    lines.append("🔹 人设不扁平，关系有拉扯")
    if str(chars.get("女主", "")).strip():
        lines.append(f"- 女主：{chars.get('女主', '')}")
    if str(chars.get("男主", "")).strip():
        lines.append(f"- 男主：{chars.get('男主', '')}")
    if str(chars.get("亮点配角", "")).strip():
        lines.append(f"- 配角：{chars.get('亮点配角', '')}")
    lines.append("")

    lines.append("🔹 冲突是递进的，不是单点吵架")
    if str(conflicts.get("第一层", "")).strip():
        lines.append(f"- 第一层：{conflicts.get('第一层', '')}")
    if str(conflicts.get("第二层", "")).strip():
        lines.append(f"- 第二层：{conflicts.get('第二层', '')}")
    if str(conflicts.get("第三层", "")).strip():
        lines.append(f"- 第三层：{conflicts.get('第三层', '')}")
    lines.append("")

    if emotions:
        lines.append("🔹 情绪反馈稳定，容易追更")
        lines.append("- 情绪关键词：" + " / ".join([str(x).strip() for x in emotions if str(x).strip()]))
        if str(p.get("正文结构建议", "")).strip():
            lines.append("- 结构节奏：" + str(p.get("正文结构建议", "")).strip())
        lines.append("")

    if quotes:
        lines.append("📝 可抄作业句子（收藏版）")
        for item in quotes[:5]:
            lines.append(f"- {str(item).strip()}")
        lines.append("")

    lines.append("💬 我的结论")
    lines.append("如果你最近想看“有爽点但不空心”的文，这本值得一试。")
    lines.append("")
    lines.append("👇 你来选")
    lines.append(str(p.get("互动话术模板", "你最吃哪类剧情？评论区告诉我")).strip())
    lines.append("我也想抄你们的书单，评论区互相投喂！")
    lines.append("")
    if tags:
        lines.append("🏷️ 标签")
        lines.append(" ".join([str(x).strip() for x in tags if str(x).strip()]))
    return "\n".join(lines).strip()


def load_xhs_filtered_list(q, page_size, page, xhs_published="all", xhs_missing="all"):
    """
    When filtering missing fields we can't reliably do server-side paging.
    We scan (with optional published filter), filter locally, cache 60s, then paginate locally.
    """
    import time as _time

    client = FeishuClient()
    if not client.is_configured():
        return [], {"prev_url": None, "next_url": None, "label": "飞书未配置"}
    cfg = get_feishu_config()
    table_id = cfg.get("related_table_ids", {}).get("小红书笔记库")
    if not table_id:
        return [], {"prev_url": None, "next_url": None, "label": "未配置小红书笔记库"}

    ql = (q or "").strip().lower()
    xhs_published = (xhs_published or "all").strip().lower()
    xhs_missing = (xhs_missing or "all").strip().lower()
    page = max(1, int(page or 1))
    key = (ql, xhs_published, xhs_missing)
    now = _time.time()
    hit = _XHS_FILTER_CACHE.get(key)
    if hit and (now - hit.get("ts", 0.0)) < _XHS_FILTER_CACHE_SEC:
        all_items = hit.get("items", []) or []
    else:
        try:
            field_meta = client.get_table_field_meta(table_id) or {}
            pub_meta = field_meta.get("是否发布笔记") or {}
            pub_options = (pub_meta.get("property") or {}).get("options") or []
            pub_id_to_name = {}
            for opt in pub_options:
                oid = opt.get("id") or opt.get("option_id") or opt.get("value")
                name = opt.get("name")
                if oid and name:
                    pub_id_to_name[str(oid)] = str(name)

            filter_expr = _build_published_filter_expr(client, table_id, xhs_published)
            all_items = []
            for it in client.iter_records(table_id, page_size=200, filter_expr=filter_expr):
                rid = it.get("record_id")
                f = it.get("fields", {}) or {}
                work_name = str(f.get("作品名称", "")).strip()
                author = str(f.get("作者", "")).strip()
                if ql and ql not in work_name.lower() and ql not in author.lower():
                    continue

                pub_raw = f.get("是否发布笔记")
                pub_name = ""
                if isinstance(pub_raw, str) and pub_raw.strip():
                    pub_name = pub_id_to_name.get(pub_raw, pub_raw)
                published = (str(pub_name).strip() == "是")

                miss_info = _compute_xhs_missing(f)
                prompt_ok = miss_info["prompt_ok"]
                image_ok = miss_info["image_ok"]
                md_ok = miss_info["md_ok"]
                miss_prompt = len(miss_info["prompt_missing_idx"]) > 0
                miss_image = len(miss_info["image_missing_idx"]) > 0
                miss_md = not bool(md_ok)
                miss_any = miss_prompt or miss_image or miss_md
                if xhs_missing == "any" and not miss_any:
                    continue
                if xhs_missing == "prompt" and not miss_prompt:
                    continue
                if xhs_missing == "image" and not miss_image:
                    continue
                if xhs_missing == "md" and not miss_md:
                    continue

                all_items.append(
                    {
                        "xhs_record_id": rid,
                        "work_name": work_name,
                        "author": author,
                        "update_time": str(f.get("更新时间", "")).strip(),
                        "prompt_ok": prompt_ok,
                        "image_ok": image_ok,
                        "md_ok": md_ok,
                        "missing_text": miss_info["missing_text"],
                        "published": published,
                        "published_name": pub_name or ("是" if published else "否"),
                    }
                )
        except Exception as e:
            return [], {"prev_url": None, "next_url": None, "label": f"筛选失败: {e}"}

        _XHS_FILTER_CACHE[key] = {"ts": now, "items": all_items}

    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    sliced = all_items[start:end]
    base = (
        f"/?tab=xhs&q={q or ''}&page_size={page_size}"
        f"&xhs_published={xhs_published}&xhs_missing={xhs_missing}"
    )
    prev_url = f"{base}&page={page-1}" if page > 1 else None
    next_url = f"{base}&page={page+1}" if end < total else None
    label = f"筛选结果 {total} 条 | 第 {page} 页"
    return sliced, {"prev_url": prev_url, "next_url": next_url, "label": label}


def _b64json_dumps(obj):
    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64json_loads(s):
    if not s:
        return []
    pad = "=" * (-len(s) % 4)
    raw = base64.urlsafe_b64decode((s + pad).encode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def paginate_local(items, page, page_size, q, published):
    total = len(items)
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    end = start + page_size
    sliced = items[start:end]
    for i, it in enumerate(sliced):
        it["_idx"] = start + i
    qs = f"&q={q}&published={published}&page_size={page_size}"
    prev_url = f"/?tab=local&page={page-1}{qs}" if page > 1 else None
    next_url = f"/?tab=local&page={page+1}{qs}" if end < total else None
    label = f"第 {page} 页 | 共 {total} 条"
    return sliced, {"prev_url": prev_url, "next_url": next_url, "label": label}


def load_xhs_page(q, page_size, page_token, stack_token, xhs_published="all", xhs_missing="all"):
    client = FeishuClient()
    if not client.is_configured():
        return [], {"prev_url": None, "next_url": None, "label": "飞书未配置"}
    cfg = get_feishu_config()
    table_id = cfg.get("related_table_ids", {}).get("小红书笔记库")
    if not table_id:
        return [], {"prev_url": None, "next_url": None, "label": "未配置小红书笔记库"}

    field_meta = client.get_table_field_meta(table_id) or {}
    pub_meta = field_meta.get("是否发布笔记") or {}
    pub_options = (pub_meta.get("property") or {}).get("options") or []
    pub_id_to_name = {}
    for opt in pub_options:
        oid = opt.get("id") or opt.get("option_id") or opt.get("value")
        name = opt.get("name")
        if oid and name:
            pub_id_to_name[str(oid)] = str(name)

    xhs_published = (xhs_published or "all").strip().lower()
    filter_expr = _build_published_filter_expr(client, table_id, xhs_published)

    items, next_token = client.list_records_page(
        table_id, page_size=page_size, page_token=page_token, filter_expr=filter_expr
    )
    out = []
    ql = (q or "").strip().lower()
    for it in items:
        rid = it.get("record_id")
        f = it.get("fields", {}) or {}
        work_name = str(f.get("作品名称", "")).strip()
        author = str(f.get("作者", "")).strip()
        if ql and ql not in work_name.lower() and ql not in author.lower():
            continue
        pub_raw = f.get("是否发布笔记")
        pub_name = ""
        if isinstance(pub_raw, str) and pub_raw.strip():
            pub_name = pub_id_to_name.get(pub_raw, pub_raw)
        elif pub_raw is not None and not isinstance(pub_raw, (str, list, dict)):
            pub_name = str(pub_raw)
        published = (str(pub_name).strip() == "是")
        miss_info = _compute_xhs_missing(f)
        prompt_ok = miss_info["prompt_ok"]
        image_ok = miss_info["image_ok"]
        md_ok = miss_info["md_ok"]
        out.append(
            {
                "xhs_record_id": rid,
                "work_name": work_name,
                "author": author,
                "update_time": str(f.get("更新时间", "")).strip(),
                "prompt_ok": prompt_ok,
                "image_ok": image_ok,
                "published": published,
                "published_name": pub_name or ("是" if published else "否"),
                "md_ok": md_ok,
                "missing_text": miss_info["missing_text"],
            }
        )

    stack = _b64json_loads(stack_token) if stack_token else []
    base = (
        f"/?tab=xhs&q={q or ''}&page_size={page_size}"
        f"&xhs_published={xhs_published}&xhs_missing={xhs_missing}"
    )
    prev_url = None
    if stack:
        prev_stack = stack[:-1]
        prev_token = stack[-1]
        prev_url = base + f"&page_token={prev_token}&stack={_b64json_dumps(prev_stack)}"
    next_url = None
    if next_token:
        next_stack = stack + ([page_token] if page_token else [""])
        next_url = base + f"&page_token={next_token}&stack={_b64json_dumps(next_stack)}"
    label = f"page_size={page_size} | 本页 {len(out)} 条"
    return out, {"prev_url": prev_url, "next_url": next_url, "label": label}


def build_graphic_note_content(item):
    xhs_path = item.get("xhs_path", "")
    note_text = ""
    if xhs_path and os.path.exists(xhs_path):
        with open(xhs_path, "r", encoding="utf-8") as f:
            note_text = f.read().strip()
    prompts = item.get("image_prompts", [])
    if not isinstance(prompts, list):
        prompts = []
    prompts = [str(x).strip() for x in prompts if str(x).strip()]
    lines = []
    lines.append(note_text or "（未找到小红书笔记正文）")
    lines.append("")
    lines.append("——")
    lines.append("配图提示词（小红书3:4竖版，动漫风优先）")
    for i, p in enumerate(prompts[:5], 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def build_note_only(item):
    xhs_path = item.get("xhs_path", "")
    if xhs_path and os.path.exists(xhs_path):
        with open(xhs_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "（未找到小红书笔记正文）"


def build_prompts_only(item):
    prompts = item.get("image_prompts", [])
    if not isinstance(prompts, list):
        prompts = []
    prompts = [str(x).strip() for x in prompts if str(x).strip()]
    lines = []
    lines.append("配图提示词（小红书3:4竖版，动漫风优先）")
    for i, p in enumerate(prompts[:5], 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def mark_published(record_id):
    if not record_id:
        return False
    client = FeishuClient()
    if not client.is_configured():
        return False
    # Update main table: 是否发布笔记 = True
    client.update_record(record_id, {"是否发布笔记": True})
    return True


def set_xhs_published(xhs_record_id, published):
    xhs_record_id = (xhs_record_id or "").strip()
    if not xhs_record_id:
        return False
    client = FeishuClient()
    if not client.is_configured():
        return False
    cfg = get_feishu_config()
    table_id = cfg.get("related_table_ids", {}).get("小红书笔记库")
    if not table_id:
        return False
    want = "是" if published else "否"
    opt_id = client.resolve_single_select_option_id(table_id, "是否发布笔记", want)
    val = opt_id or want
    client.update_record_in_table(table_id, xhs_record_id, {"是否发布笔记": val})
    return True


def _build_note_fields_for_xhs(meta, xhs_table_id, client, analysis):
    fields = {}
    pack = analysis.get("小红书包装", {}) or {}
    if "正文开头模板" in meta:
        fields["正文开头模板"] = str(pack.get("正文开头模板", "")).strip()[:68]
    if "正文结构建议" in meta:
        fields["正文结构建议"] = str(pack.get("正文结构建议", "")).strip()[:56]
    if "互动话术模板" in meta:
        fields["互动话术模板"] = str(pack.get("互动话术模板", "")).strip()[:56]
    if "小红书标题模板" in meta:
        fields["小红书标题模板"] = str(pack.get("小红书标题模板", "")).strip()
    if "热门标签推荐" in meta:
        tags = pack.get("热门标签推荐", [])
        fields["热门标签推荐"] = tags if isinstance(tags, list) else [str(tags)]
    if "更新时间" in meta and fields:
        fields["更新时间"] = int(datetime.now().timestamp() * 1000)

    # Normalize to current field types.
    for k, v in list(fields.items()):
        ftype = (meta.get(k) or {}).get("type")
        if ftype == 4:
            if k == "小红书标题模板":
                fields[k] = [str(v)] if not isinstance(v, list) else v[:1]
            elif isinstance(v, list):
                fields[k] = v
            else:
                parts = [x.strip() for x in str(v).replace("，", ",").split(",") if x.strip()]
                fields[k] = parts if parts else [str(v)]
        elif ftype == 3:
            raw = v[0] if isinstance(v, list) and v else str(v)
            s = str(raw or "").strip()
            if s:
                fields[k] = client.resolve_single_select_option_id(xhs_table_id, k, s) or s
            else:
                fields[k] = ""
        elif ftype == 5:
            fields[k] = int(v) if isinstance(v, int) else int(datetime.now().timestamp() * 1000)
    return fields


@app.route("/legacy")
def index():
    tab = request.args.get("tab", "local").strip() or "local"
    q = request.args.get("q", "").strip()
    page_size = int(request.args.get("page_size", "12") or 12)

    if tab == "overview":
        items = load_records()
        local_total = len(items)
        local_published = len([x for x in items if x.get("published")])
        xhs_stats, xhs_err = load_xhs_stats_cached()
        topic_stats, topic_err = load_yesno_stats_cached(
            "选题库", yesno_field_candidates=["是否拆解", "是否入库", "是否通过", "状态"]
        )
        prescreen_stats, prescreen_err = load_yesno_stats_cached(
            "选题库-初筛", yesno_field_candidates=["是否入库", "是否通过", "审核状态", "状态", "是否拆解"]
        )
        queue = load_image_queue_status()
        overview = {
            "cache_sec": _XHS_STATS_CACHE_SEC,
            "topic_cache_sec": _TOPIC_STATS_CACHE_SEC,
            "local_tasks_total": local_total,
            "local_tasks_published": local_published,
            "queue": queue,
            "xhs_total": (xhs_stats or {}).get("total", 0) if xhs_stats else 0,
            "xhs_published": (xhs_stats or {}).get("published", 0) if xhs_stats else 0,
            "xhs_unpublished": (xhs_stats or {}).get("unpublished", 0) if xhs_stats else 0,
            "xhs_publish_rate_pct": (xhs_stats or {}).get("rate_pct", 0) if xhs_stats else 0,
            "xhs_prompt_complete": (xhs_stats or {}).get("prompt_complete", 0) if xhs_stats else 0,
            "xhs_image_complete": (xhs_stats or {}).get("image_complete", 0) if xhs_stats else 0,
            "xhs_md_missing": (xhs_stats or {}).get("md_missing", 0) if xhs_stats else 0,
            "xhs_err": xhs_err,
            "topic_total": (topic_stats or {}).get("total", 0) if topic_stats else 0,
            "topic_yes": (topic_stats or {}).get("yes", 0) if topic_stats else 0,
            "topic_no": (topic_stats or {}).get("no", 0) if topic_stats else 0,
            "topic_rate_pct": (topic_stats or {}).get("rate_pct", 0) if topic_stats else 0,
            "topic_err": topic_err,
            "prescreen_total": (prescreen_stats or {}).get("total", 0) if prescreen_stats else 0,
            "prescreen_yes": (prescreen_stats or {}).get("yes", 0) if prescreen_stats else 0,
            "prescreen_no": (prescreen_stats or {}).get("no", 0) if prescreen_stats else 0,
            "prescreen_rate_pct": (prescreen_stats or {}).get("rate_pct", 0) if prescreen_stats else 0,
            "prescreen_err": prescreen_err,
        }
        return render_template_string(
            TEMPLATE,
            tab="overview",
            items=[],
            pager={"prev_url": None, "next_url": None, "label": ""},
            summary=None,
            queue=None,
            q="",
            published="all",
            xhs_published="all",
            xhs_missing="all",
            overview=overview,
            prescreen_banner=None,
            ps_mode="rank",
            ps_query="",
            ps_sources="fanqie,jjwxc",
            ps_limit=30,
            ps_batch=datetime.now().strftime("%Y-%m-%d"),
            ps_dry_run=False,
            prescreen_recent={"total": 0, "ok": 0, "failed": 0, "latest": []},
            prescreen_jobs={"total": 0, "queued": 0, "running": 0, "latest": []},
            prescreen_latest_rows=[],
            prescreen_latest_err=None,
            prescreen_latest_cache_sec=_PRESCREEN_LATEST_CACHE_SEC,
        )

    if tab == "prescreen":
        notice = (request.args.get("ps_notice", "") or "").strip()
        notice_job = (request.args.get("ps_job", "") or "").strip()
        prescreen_banner = None
        if notice == "queued":
            txt = "已提交抓取任务"
            if notice_job:
                txt += f"（job_id={notice_job}）"
            txt += "，请在右侧查看 queued/running/done 状态。"
            prescreen_banner = {"kind": "ok", "text": txt}

        ps_mode = (request.args.get("ps_mode", "rank") or "rank").strip()
        ps_query = (request.args.get("ps_query", "") or "").strip()
        ps_sources = (request.args.get("ps_sources", "fanqie,jjwxc") or "fanqie,jjwxc").strip()
        try:
            ps_limit = int(request.args.get("ps_limit", "30") or 30)
        except Exception:
            ps_limit = 30
        ps_batch = (request.args.get("ps_batch", "") or "").strip() or datetime.now().strftime("%Y-%m-%d")
        ps_dry_run = (request.args.get("ps_dry_run", "") or "").strip() == "1"
        prescreen_recent = load_prescreen_recent()
        prescreen_jobs = load_prescreen_jobs_tail()
        latest_items, latest_err = load_prescreen_latest_cached(limit=20)
        return render_template_string(
            TEMPLATE,
            tab="prescreen",
            items=[],
            pager={"prev_url": None, "next_url": None, "label": ""},
            summary=None,
            queue=None,
            q="",
            published="all",
            xhs_published="all",
            xhs_missing="all",
            overview=None,
            prescreen_banner=prescreen_banner,
            ps_mode=ps_mode,
            ps_query=ps_query,
            ps_sources=ps_sources,
            ps_limit=ps_limit,
            ps_batch=ps_batch,
            ps_dry_run=ps_dry_run,
            prescreen_recent=prescreen_recent,
            prescreen_jobs=prescreen_jobs,
            prescreen_latest_rows=latest_items,
            prescreen_latest_err=latest_err,
            prescreen_latest_cache_sec=_PRESCREEN_LATEST_CACHE_SEC,
        )

    if tab == "analysis":
        notice = (request.args.get("analysis_notice", "") or "").strip()
        notice_job = (request.args.get("analysis_job", "") or "").strip()
        analysis_banner = None
        if notice == "queued":
            txt = "已提交分析任务"
            if notice_job:
                txt += f"（job_id={notice_job}）"
            txt += "，请在右侧查看 queued/running/done 状态。"
            analysis_banner = {"kind": "ok", "text": txt}

        analysis_jobs = load_analysis_jobs_tail()
        analysis_recent = load_analysis_recent()
        latest_report = load_latest_analysis_report()
        analysis_batch = (request.args.get("analysis_batch", "") or "").strip() or datetime.now().strftime("%Y-%m-%d")
        analysis_account_name = (request.args.get("analysis_account_name", "主账号") or "主账号").strip()
        analysis_recovery_date = (request.args.get("analysis_recovery_date", "2026-03-01") or "2026-03-01").strip()
        analysis_dry_run = (request.args.get("analysis_dry_run", "") or "").strip() == "1"
        analysis_write_feishu = (request.args.get("analysis_write_feishu", "1") or "1").strip() == "1"
        analysis_experiment_id = (request.args.get("analysis_experiment_id", "") or "").strip()
        analysis_experiment_version = (request.args.get("analysis_experiment_version", "NA") or "NA").strip().upper()
        if analysis_experiment_version not in ["A", "B", "NA"]:
            analysis_experiment_version = "NA"
        analysis_experiment_variable = (request.args.get("analysis_experiment_variable", "") or "").strip()
        account7d_account_name = (request.args.get("account7d_account_name", "主账号") or "主账号").strip()
        account7d_snapshot_date = (request.args.get("account7d_snapshot_date", datetime.now().strftime("%Y-%m-%d")) or datetime.now().strftime("%Y-%m-%d")).strip()
        account7d_batch = (request.args.get("account7d_batch", datetime.now().strftime("%Y-%m-%d")) or datetime.now().strftime("%Y-%m-%d")).strip()
        account7d_dry_run = (request.args.get("account7d_dry_run", "") or "").strip() == "1"
        account7d_write_feishu = (request.args.get("account7d_write_feishu", "1") or "1").strip() == "1"
        report_days = (request.args.get("report_days", "14") or "14").strip()
        report_min_exposure = (request.args.get("report_min_exposure", "30") or "30").strip()
        report_sync_factors = (request.args.get("report_sync_factors", "0") or "0").strip() == "1"
        report_experiment_id = (request.args.get("report_experiment_id", "") or "").strip()
        return render_template_string(
            TEMPLATE,
            tab="analysis",
            items=[],
            pager={"prev_url": None, "next_url": None, "label": ""},
            summary=None,
            queue=None,
            q="",
            published="all",
            xhs_published="all",
            xhs_missing="all",
            overview=None,
            prescreen_banner=None,
            ps_mode="rank",
            ps_query="",
            ps_sources="fanqie,jjwxc",
            ps_limit=30,
            ps_batch=datetime.now().strftime("%Y-%m-%d"),
            ps_dry_run=False,
            prescreen_recent={"total": 0, "ok": 0, "failed": 0, "latest": []},
            prescreen_jobs={"total": 0, "queued": 0, "running": 0, "latest": []},
            prescreen_latest_rows=[],
            prescreen_latest_err=None,
            prescreen_latest_cache_sec=_PRESCREEN_LATEST_CACHE_SEC,
            analysis_banner=analysis_banner,
            analysis_jobs=analysis_jobs,
            analysis_recent=analysis_recent,
            latest_report=latest_report,
            analysis_batch=analysis_batch,
            analysis_account_name=analysis_account_name,
            analysis_recovery_date=analysis_recovery_date,
            analysis_dry_run=analysis_dry_run,
            analysis_write_feishu=analysis_write_feishu,
            analysis_experiment_id=analysis_experiment_id,
            analysis_experiment_version=analysis_experiment_version,
            analysis_experiment_variable=analysis_experiment_variable,
            account7d_account_name=account7d_account_name,
            account7d_snapshot_date=account7d_snapshot_date,
            account7d_batch=account7d_batch,
            account7d_dry_run=account7d_dry_run,
            account7d_write_feishu=account7d_write_feishu,
            report_days=report_days,
            report_min_exposure=report_min_exposure,
            report_sync_factors=report_sync_factors,
            report_experiment_id=report_experiment_id,
            analysis_report_dir=os.path.join(PATHS["outputs"], "分析周报"),
        )

    if tab == "xhs":
        page_token = request.args.get("page_token", "").strip() or None
        stack = request.args.get("stack", "").strip()
        xhs_published = (request.args.get("xhs_published", "all") or "all").strip()
        xhs_missing = (request.args.get("xhs_missing", "all") or "all").strip()
        xhs_notice = (request.args.get("xhs_notice", "") or "").strip().lower()
        xhs_part = (request.args.get("xhs_part", "") or "").strip().lower()
        xhs_rid = (request.args.get("xhs_rid", "") or "").strip()
        xhs_banner = None
        if xhs_notice in ["queued", "ok"]:
            part_name = "笔记+提示词" if xhs_part in ["", "all"] else ("笔记" if xhs_part == "note" else "提示词")
            txt = f"已提交重生任务（{part_name}）"
            if xhs_rid:
                txt += f" | xhs_record_id={xhs_rid}"
            txt += "，请稍后刷新查看结果。"
            xhs_banner = {"kind": "ok", "text": txt}
        elif xhs_notice in ["err", "error"]:
            txt = "提交重生任务失败，请检查服务日志。"
            if xhs_rid:
                txt += f" | xhs_record_id={xhs_rid}"
            xhs_banner = {"kind": "err", "text": txt}
        page = int(request.args.get("page", "1") or 1)
        if xhs_missing.strip().lower() != "all":
            items, pager = load_xhs_filtered_list(
                q=q,
                page_size=page_size,
                page=page,
                xhs_published=xhs_published,
                xhs_missing=xhs_missing,
            )
        else:
            items, pager = load_xhs_page(
                q=q,
                page_size=page_size,
                page_token=page_token,
                stack_token=stack,
                xhs_published=xhs_published,
                xhs_missing=xhs_missing,
            )
        return render_template_string(
            TEMPLATE,
            tab="xhs",
            items=items,
            pager=pager,
            summary=None,
            queue=None,
            q=q,
            published="all",
            xhs_published=xhs_published,
            xhs_missing=xhs_missing,
            overview=None,
            xhs_banner=xhs_banner,
            prescreen_banner=None,
            ps_mode="rank",
            ps_query="",
            ps_sources="fanqie,jjwxc",
            ps_limit=30,
            ps_batch=datetime.now().strftime("%Y-%m-%d"),
            ps_dry_run=False,
            prescreen_recent={"total": 0, "ok": 0, "failed": 0, "latest": []},
            prescreen_jobs={"total": 0, "queued": 0, "running": 0, "latest": []},
            prescreen_latest_rows=[],
            prescreen_latest_err=None,
            prescreen_latest_cache_sec=_PRESCREEN_LATEST_CACHE_SEC,
        )

    published = request.args.get("published", "all").strip()
    page = int(request.args.get("page", "1") or 1)

    items = load_records()
    if q:
        items = [x for x in items if q.lower() in str(x.get("work_name", "")).lower() or q.lower() in str(x.get("author", "")).lower()]
    if published == "yes":
        items = [x for x in items if x.get("published")]
    elif published == "no":
        items = [x for x in items if not x.get("published")]

    items, pager = paginate_local(items, page=page, page_size=page_size, q=q, published=published)
    return render_template_string(
        TEMPLATE,
        tab="local",
        items=items,
        pager=pager,
        summary=load_run_summary(),
        queue=load_image_queue_status(),
        q=q,
        published=published,
        xhs_published="all",
        xhs_missing="all",
        overview=None,
        prescreen_banner=None,
        ps_mode="rank",
        ps_query="",
        ps_sources="fanqie,jjwxc",
        ps_limit=30,
        ps_batch=datetime.now().strftime("%Y-%m-%d"),
        ps_dry_run=False,
        prescreen_recent={"total": 0, "ok": 0, "failed": 0, "latest": []},
        prescreen_jobs={"total": 0, "queued": 0, "running": 0, "latest": []},
        prescreen_latest_rows=[],
        prescreen_latest_err=None,
        prescreen_latest_cache_sec=_PRESCREEN_LATEST_CACHE_SEC,
    )


def load_prescreen_recent():
    return service_load_prescreen_recent()


def load_prescreen_jobs_tail():
    return service_load_prescreen_jobs_tail()


def humanize_prescreen_summary(summary):
    return service_humanize_prescreen_summary(summary)


def load_prescreen_latest_cached(limit=20):
    return service_load_prescreen_latest_cached(limit=limit)


def fmt_compact_num(v):
    return service_fmt_compact_num(v)


def load_analysis_recent():
    return service_load_analysis_recent()


def load_analysis_jobs_tail():
    return service_load_analysis_jobs_tail()


def load_latest_analysis_report():
    return service_load_latest_analysis_report()


@app.route("/prescreen/fetch", methods=["POST"])
def prescreen_fetch():
    """
    Start a background fetch+upsert to Feishu "选题库-初筛" by invoking scripts/prescreen_fetch_insert.py.
    """
    ensure_dirs()
    mode = (request.form.get("mode", "rank") or "rank").strip()
    query = (request.form.get("query", "") or "").strip()
    sources = (request.form.get("sources", "fanqie,jjwxc") or "fanqie,jjwxc").strip()
    try:
        limit = int(request.form.get("limit", "30") or 30)
    except Exception:
        limit = 30
    batch = (request.form.get("batch", "") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    dry_run = (request.form.get("dry_run") or "").strip() == "1"

    job_id = f"ps_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"),
        {
            "ts": now_ts(),
            "job_id": job_id,
            "mode": mode,
            "query": query,
            "sources": sources,
            "limit": limit,
            "batch": batch,
            "dry_run": dry_run,
            "status": "queued",
        },
    )

    import subprocess
    import threading

    def run_job():
        append_jsonl(
            os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"),
            {"ts": now_ts(), "job_id": job_id, "status": "running"},
        )
        cmd = [
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, "scripts", "prescreen_fetch_insert.py"),
            "--sources",
            sources,
            "--limit",
            str(limit),
            "--batch",
            batch,
            "--mode",
            mode,
        ]
        if mode == "search":
            cmd.extend(["--query", query])
        if dry_run:
            cmd.append("--dry-run")

        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 15)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            last = out.splitlines()[-1].strip() if out else ""
            ok_flag = p.returncode == 0
            summary = last or f"returncode={p.returncode}"
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "ok": ok_flag,
                    "mode": mode,
                    "query": query,
                    "sources": sources,
                    "limit": limit,
                    "batch": batch,
                    "dry_run": dry_run,
                    "summary": summary,
                    "summary_cn": humanize_prescreen_summary(summary),
                    "stderr_tail": err[-800:] if err else "",
                },
            )
        except Exception as e:
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "ok": False,
                    "mode": mode,
                    "query": query,
                    "sources": sources,
                    "limit": limit,
                    "batch": batch,
                    "dry_run": dry_run,
                    "summary": f"exception: {e}",
                },
            )
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "prescreen_web_jobs.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "status": "done",
                    "ok": ok_flag,
                    "summary": summary,
                    "summary_cn": humanize_prescreen_summary(summary),
                },
            )

    threading.Thread(target=run_job, daemon=True).start()

    return redirect(
        url_for(
            "index",
            tab="prescreen",
            ps_notice="queued",
            ps_job=job_id,
            ps_mode=mode,
            ps_query=query,
            ps_sources=sources,
            ps_limit=limit,
            ps_batch=batch,
            ps_dry_run="1" if dry_run else "0",
        )
    )


@app.route("/analysis/upload", methods=["POST"])
def analysis_upload():
    ensure_dirs()
    upload = request.files.get("xlsx_file")
    if not upload:
        return redirect(url_for("index", tab="analysis"))

    account_name = (request.form.get("account_name", "主账号") or "主账号").strip()
    recovery_date = (request.form.get("recovery_date", "2026-03-01") or "2026-03-01").strip()
    batch = (request.form.get("batch", "") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    dry_run = (request.form.get("dry_run") or "").strip() == "1"
    write_feishu = (request.form.get("write_feishu") or "").strip() == "1"
    experiment_id = (request.form.get("experiment_id", "") or "").strip()
    experiment_version = (request.form.get("experiment_version", "NA") or "NA").strip().upper()
    if experiment_version not in ["A", "B", "NA"]:
        experiment_version = "NA"
    experiment_variable = (request.form.get("experiment_variable", "") or "").strip()

    uploads_dir = os.path.join(PATHS["logs"], "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    safe_name = os.path.basename(upload.filename or "")
    if not safe_name.lower().endswith(".xlsx"):
        safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_metrics.xlsx"
    file_path = os.path.join(uploads_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}")
    upload.save(file_path)

    job_id = f"an_up_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
        {
            "ts": now_ts(),
            "job_id": job_id,
            "kind": "upload",
            "status": "queued",
            "file_path": file_path,
            "account_name": account_name,
            "recovery_date": recovery_date,
            "batch": batch,
            "experiment_id": experiment_id,
            "experiment_version": experiment_version,
            "experiment_variable": experiment_variable,
            "dry_run": dry_run,
            "write_feishu": write_feishu,
        },
    )

    import subprocess
    import threading

    def run_job():
        append_jsonl(os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"), {"ts": now_ts(), "job_id": job_id, "kind": "upload", "status": "running"})
        cmd = [
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, "scripts", "note_metrics_import.py"),
            "--xlsx",
            file_path,
            "--batch",
            batch,
            "--account-name",
            account_name,
            "--recovery-date",
            recovery_date,
            "--experiment-id",
            experiment_id,
            "--experiment-version",
            experiment_version,
            "--experiment-variable",
            experiment_variable,
        ]
        if dry_run:
            cmd.append("--dry-run")
        if write_feishu:
            cmd.append("--write-feishu")

        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 20)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            last = out.splitlines()[-1].strip() if out else ""
            ok_flag = p.returncode == 0
            summary = last or f"returncode={p.returncode}"
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "kind": "upload",
                    "ok": ok_flag,
                    "summary": summary,
                    "stderr_tail": err[-800:] if err else "",
                },
            )
        except Exception as e:
            summary = f"exception: {e}"
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "upload", "ok": False, "summary": summary},
            )
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "upload", "status": "done", "ok": ok_flag, "summary": summary},
            )

    threading.Thread(target=run_job, daemon=True).start()
    return redirect(
        url_for(
            "index",
            tab="analysis",
            analysis_notice="queued",
            analysis_job=job_id,
            analysis_batch=batch,
            analysis_account_name=account_name,
            analysis_recovery_date=recovery_date,
            analysis_dry_run="1" if dry_run else "0",
            analysis_write_feishu="1" if write_feishu else "0",
            analysis_experiment_id=experiment_id,
            analysis_experiment_version=experiment_version,
            analysis_experiment_variable=experiment_variable,
        )
    )


@app.route("/analysis/report", methods=["POST"])
def analysis_report():
    ensure_dirs()
    days = (request.form.get("days", "14") or "14").strip()
    min_exposure = (request.form.get("min_exposure", "30") or "30").strip()
    sync_factors = (request.form.get("sync_factors") or "").strip() == "1"
    experiment_id = (request.form.get("experiment_id", "") or "").strip()

    job_id = f"an_rp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
        {
            "ts": now_ts(),
            "job_id": job_id,
            "kind": "report",
            "status": "queued",
            "days": days,
            "min_exposure": min_exposure,
            "sync_factors": sync_factors,
            "experiment_id": experiment_id,
        },
    )

    import subprocess
    import threading

    def run_job():
        append_jsonl(os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"), {"ts": now_ts(), "job_id": job_id, "kind": "report", "status": "running"})
        cmd = [
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, "scripts", "hot_model_report.py"),
            "--days",
            days,
            "--min-exposure",
            min_exposure,
        ]
        if experiment_id:
            cmd.extend(["--experiment-id", experiment_id])
        if sync_factors:
            cmd.append("--sync-factors")

        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 10)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            last = out.splitlines()[-1].strip() if out else ""
            ok_flag = p.returncode == 0
            summary = last or f"returncode={p.returncode}"
            service_clear_analysis_report_cache()
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "kind": "report",
                    "ok": ok_flag,
                    "summary": summary,
                    "stderr_tail": err[-800:] if err else "",
                },
            )
        except Exception as e:
            summary = f"exception: {e}"
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "report", "ok": False, "summary": summary},
            )
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "report", "status": "done", "ok": ok_flag, "summary": summary},
            )

    threading.Thread(target=run_job, daemon=True).start()
    return redirect(
        url_for(
            "index",
            tab="analysis",
            analysis_notice="queued",
            analysis_job=job_id,
            report_days=days,
            report_min_exposure=min_exposure,
            report_sync_factors="1" if sync_factors else "0",
            report_experiment_id=experiment_id,
        )
    )


@app.route("/analysis/account7d_upload", methods=["POST"])
def analysis_account7d_upload():
    ensure_dirs()
    upload = request.files.get("xlsx_file")
    if not upload:
        return redirect(url_for("index", tab="analysis"))

    account_name = (request.form.get("account_name", "主账号") or "主账号").strip()
    snapshot_date = (request.form.get("snapshot_date", datetime.now().strftime("%Y-%m-%d")) or datetime.now().strftime("%Y-%m-%d")).strip()
    batch = (request.form.get("batch", "") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    dry_run = (request.form.get("dry_run") or "").strip() == "1"
    write_feishu = (request.form.get("write_feishu") or "").strip() == "1"

    uploads_dir = os.path.join(PATHS["logs"], "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    safe_name = os.path.basename(upload.filename or "")
    if not safe_name.lower().endswith(".xlsx"):
        safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_account7d.xlsx"
    file_path = os.path.join(uploads_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}")
    upload.save(file_path)

    job_id = f"an_7d_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    append_jsonl(
        os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
        {
            "ts": now_ts(),
            "job_id": job_id,
            "kind": "upload_7d",
            "status": "queued",
            "file_path": file_path,
            "account_name": account_name,
            "snapshot_date": snapshot_date,
            "batch": batch,
            "dry_run": dry_run,
            "write_feishu": write_feishu,
        },
    )

    import subprocess
    import threading

    def run_job():
        append_jsonl(
            os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
            {"ts": now_ts(), "job_id": job_id, "kind": "upload_7d", "status": "running"},
        )
        cmd = [
            os.path.join(BASE_DIR, ".venv", "bin", "python"),
            os.path.join(BASE_DIR, "scripts", "account_7d_import.py"),
            "--xlsx",
            file_path,
            "--batch",
            batch,
            "--account-name",
            account_name,
            "--snapshot-date",
            snapshot_date,
        ]
        if dry_run:
            cmd.append("--dry-run")
        if write_feishu:
            cmd.append("--write-feishu")

        ok_flag = False
        summary = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 10)
            out = (p.stdout or "").strip()
            err = (p.stderr or "").strip()
            last = out.splitlines()[-1].strip() if out else ""
            ok_flag = p.returncode == 0
            summary = last or f"returncode={p.returncode}"
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {
                    "ts": now_ts(),
                    "job_id": job_id,
                    "kind": "upload_7d",
                    "ok": ok_flag,
                    "summary": summary,
                    "stderr_tail": err[-800:] if err else "",
                },
            )
        except Exception as e:
            summary = f"exception: {e}"
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_results.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "upload_7d", "ok": False, "summary": summary},
            )
        finally:
            append_jsonl(
                os.path.join(PATHS["logs"], "analysis_web_jobs.jsonl"),
                {"ts": now_ts(), "job_id": job_id, "kind": "upload_7d", "status": "done", "ok": ok_flag, "summary": summary},
            )

    threading.Thread(target=run_job, daemon=True).start()
    return redirect(
        url_for(
            "index",
            tab="analysis",
            analysis_notice="queued",
            analysis_job=job_id,
            account7d_account_name=account_name,
            account7d_snapshot_date=snapshot_date,
            account7d_batch=batch,
            account7d_dry_run="1" if dry_run else "0",
            account7d_write_feishu="1" if write_feishu else "0",
        )
    )


@app.route("/preview/<int:idx>")
def preview(idx):
    items = load_records()
    if idx < 0 or idx >= len(items):
        abort(404)
    item = items[idx]
    content = build_graphic_note_content(item)
    note_text = build_note_only(item)
    prompts_text = build_prompts_only(item)
    return render_template_string(
        PREVIEW_TEMPLATE,
        item=item,
        content=content,
        note_text=note_text,
        prompts_text=prompts_text,
    )


@app.route("/xhs/<rid>")
def xhs_preview(rid):
    notice = (request.args.get("notice", "") or "").strip().lower()
    payload, status = service_load_xhs_preview_data(
        rid=rid,
        notice=notice,
        is_fact_repairing=(rid in _XHS_FACT_REPAIRING),
    )
    if status == 404:
        abort(404)
    if status >= 500:
        abort(500)
    if not payload.get("ok"):
        abort(500)
    return render_template_string(
        XHS_PREVIEW_TEMPLATE,
        rid=payload.get("rid", rid),
        title=payload.get("title", ""),
        author=payload.get("author", ""),
        note_text=payload.get("note_text", ""),
        note_source=payload.get("note_source", ""),
        candidate_note=payload.get("candidate_note", ""),
        candidate_ts=payload.get("candidate_ts", ""),
        cand_feedback=payload.get("cand_feedback", ""),
        cand_dissatisfaction=payload.get("cand_dissatisfaction", ""),
        cand_model_provider=payload.get("cand_model_provider", ""),
        cand_model_name=payload.get("cand_model_name", ""),
        cand_gen_source=payload.get("cand_gen_source", ""),
        cand_gen_error=payload.get("cand_gen_error", ""),
        cand_allow_fallback=payload.get("cand_allow_fallback", True),
        cand_facts_missing=payload.get("cand_facts_missing", []),
        cand_facts_main_record_id=payload.get("cand_facts_main_record_id", ""),
        xhs_banner=payload.get("xhs_banner"),
        prompts_text=payload.get("prompts_text", "（无提示词）"),
        fields_json=payload.get("fields_json", "{}"),
        back_url="/?tab=xhs",
    )


@app.route("/xhs/regen_note_preview", methods=["POST"])
def xhs_regen_note_preview():
    rid = (request.form.get("xhs_record_id", "") or "").strip()
    dissatisfaction = (request.form.get("dissatisfaction", "") or "").strip()
    feedback = (request.form.get("feedback", "") or "").strip()
    model_provider = (request.form.get("model_provider", "") or "").strip().lower()
    model_name = (request.form.get("model_name", "") or "").strip()
    allow_fallback = (request.form.get("allow_fallback", "") or "").strip() in {"1", "true", "on", "yes", "y"}
    if not rid:
        return redirect(url_for("index", tab="xhs", xhs_notice="err"))
    try:
        client = FeishuClient()
        table_id, rec = _find_xhs_record_by_id(client, rid)
        if not table_id or not rec:
            return redirect(url_for("xhs_preview", rid=rid, notice="err"))
        fields = rec.get("fields", {}) or {}
        work_name = str(fields.get("作品名称", "")).strip()
        work = _find_topic_work(client, work_name) or {
            "作品名称": work_name,
            "作者": str(fields.get("作者", "")).strip(),
            "平台": "",
            "分类": "",
            "简介": "",
        }
        facts = _collect_fact_pack(client, rec)
        if facts.get("missing"):
            _start_fact_repair_async(rid, facts.get("main_record_id", ""), work)
            append_jsonl(
                os.path.join(PATHS["logs"], "xhs_fact_repair_results.jsonl"),
                {
                    "ts": now_ts(),
                    "xhs_record_id": rid,
                    "main_record_id": facts.get("main_record_id", ""),
                    "status": "queued",
                    "missing": facts.get("missing", []),
                },
            )
            return redirect(url_for("xhs_preview", rid=rid, notice="fact_repairing"))
        analysis, note, gen_source, gen_error = _generate_note_candidate(
            work=work,
            dissatisfaction=dissatisfaction,
            feedback=feedback,
            provider=model_provider,
            model_name=model_name,
            allow_fallback=allow_fallback,
            facts=facts,
        )
        cands = _load_xhs_note_candidates()
        cands[rid] = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "rid": rid,
            "work_name": work.get("作品名称", ""),
            "author": work.get("作者", ""),
            "dissatisfaction": dissatisfaction,
            "feedback": feedback,
            "model_provider": model_provider or os.getenv("MODEL_PROVIDER", "qwen").strip().lower(),
            "model_name": model_name,
            "allow_fallback": allow_fallback,
            "gen_source": gen_source,
            "gen_error": gen_error,
            "facts_missing": facts.get("missing", []),
            "facts_main_record_id": facts.get("main_record_id", ""),
            "note": note,
            "analysis": analysis,
        }
        _save_xhs_note_candidates(cands)
        return redirect(url_for("xhs_preview", rid=rid, notice="preview_ready"))
    except Exception as e:
        append_jsonl(
            os.path.join(PATHS["logs"], "xhs_regen_job_results.jsonl"),
            {
                "ts": now_ts(),
                "xhs_record_id": rid,
                "part": "note_preview",
                "ok": False,
                "stderr_tail": str(e),
            },
        )
        return redirect(url_for("xhs_preview", rid=rid, notice="err"))


@app.route("/xhs/adopt_note", methods=["POST"])
def xhs_adopt_note():
    rid = (request.form.get("xhs_record_id", "") or "").strip()
    if not rid:
        return redirect(url_for("index", tab="xhs", xhs_notice="err"))
    try:
        cands = _load_xhs_note_candidates()
        cand = (cands or {}).get(rid) if isinstance(cands, dict) else None
        if not isinstance(cand, dict):
            return redirect(url_for("xhs_preview", rid=rid, notice="err"))
        client = FeishuClient()
        table_id, rec = _find_xhs_record_by_id(client, rid)
        if not table_id or not rec:
            return redirect(url_for("xhs_preview", rid=rid, notice="err"))
        meta = client.get_table_field_meta(table_id) or {}
        analysis = cand.get("analysis", {}) or {}
        note = str(cand.get("note", "")).strip()
        if not note:
            return redirect(url_for("xhs_preview", rid=rid, notice="err"))

        fields = _build_note_fields_for_xhs(meta, table_id, client, analysis)
        if fields:
            client.update_record_in_table(table_id, rid, fields)

        rec_fields = rec.get("fields", {}) or {}
        work_name = str(rec_fields.get("作品名称", "")).strip()
        author = str(rec_fields.get("作者", "")).strip()
        out_dir = os.path.join(PATHS["outputs"], "小红书笔记_v3", f"{work_name}_{author}")
        os.makedirs(out_dir, exist_ok=True)
        md_path = os.path.join(out_dir, f"{work_name}-小红书笔记初稿.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(note)
        if "小红书笔记初稿" in meta:
            token = client.upload_file_to_bitable(md_path)
            client.update_record_in_table(table_id, rid, {"小红书笔记初稿": [{"file_token": token}]})

        # Candidate is one-time; clear after adopt.
        cands.pop(rid, None)
        _save_xhs_note_candidates(cands)
        return redirect(url_for("xhs_preview", rid=rid, notice="adopted"))
    except Exception:
        return redirect(url_for("xhs_preview", rid=rid, notice="err"))


@app.route("/xhs/regenerate", methods=["POST"])
def xhs_regenerate():
    import subprocess

    rid = (request.form.get("xhs_record_id", "") or "").strip()
    part = (request.form.get("part", "all") or "all").strip().lower()
    if part not in ["all", "note", "prompts"]:
        part = "all"
    if not rid:
        return redirect(url_for("index", tab="xhs", xhs_notice="err"))

    def run_job():
        try:
            cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "scripts", "repair_xhs_record.py"),
                "--record-id",
                rid,
                "--part",
                part,
            ]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 8)
            ok_flag = p.returncode == 0
            append_jsonl(
                os.path.join(PATHS["logs"], "xhs_regen_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "xhs_record_id": rid,
                    "part": part,
                    "ok": ok_flag,
                    "stdout_tail": (p.stdout or "")[-1000:],
                    "stderr_tail": (p.stderr or "")[-1000:],
                },
            )
        except Exception as e:
            append_jsonl(
                os.path.join(PATHS["logs"], "xhs_regen_job_results.jsonl"),
                {
                    "ts": now_ts(),
                    "xhs_record_id": rid,
                    "part": part,
                    "ok": False,
                    "stderr_tail": str(e),
                },
            )

    threading.Thread(target=run_job, daemon=True).start()
    return redirect(url_for("index", tab="xhs", xhs_notice="queued", xhs_part=part, xhs_rid=rid))


@app.route("/publish", methods=["POST"])
def publish():
    record_id = request.form.get("record_id", "").strip()
    work_name = request.form.get("work_name", "")
    author = request.form.get("author", "")
    ok = mark_published(record_id)

    # Also append local audit trail
    audit = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "record_id": record_id,
        "work_name": work_name,
        "author": author,
        "action": "publish_mark",
        "success": ok,
    }
    os.makedirs(PATHS["logs"], exist_ok=True)
    with open(os.path.join(PATHS["logs"], "publish_audit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(audit, ensure_ascii=False) + "\n")

    # Update local records.jsonl published status
    records = load_records()
    updated = []
    for item in records:
        if record_id and item.get("record_id") == record_id:
            item["published"] = True
        elif not record_id and item.get("work_name") == work_name and item.get("author") == author:
            item["published"] = True
        updated.append(item)
    if updated:
        with open(os.path.join(PATHS["logs"], "records.jsonl"), "w", encoding="utf-8") as f:
            for item in updated:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return redirect(url_for("index"))


@app.route("/xhs/publish", methods=["POST"])
def xhs_publish():
    rid = request.form.get("xhs_record_id", "").strip()
    val = request.form.get("published", "").strip().lower()
    published = val in ["1", "true", "yes", "y", "on", "是"]
    try:
        ok = set_xhs_published(rid, published)
    except Exception as e:
        msg = str(e)
        return render_template_string(
            """
            <!doctype html><meta charset="utf-8" />
            <div style="font-family: system-ui, -apple-system, 'PingFang SC', sans-serif; padding:20px;">
              <h3>更新失败</h3>
              <pre style="white-space:pre-wrap; word-break:break-word; background:#f6f6f6; padding:12px; border-radius:8px;">{{ msg }}</pre>
              <a href="{{ back }}">返回列表</a>
            </div>
            """,
            msg=msg,
            back=(request.referrer or "/?tab=xhs"),
        )
    if not ok:
        return render_template_string(
            """
            <!doctype html><meta charset="utf-8" />
            <div style="font-family: system-ui, -apple-system, 'PingFang SC', sans-serif; padding:20px;">
              <h3>更新失败</h3>
              <div>未能更新飞书记录（可能是飞书未配置或表未配置）。</div>
              <a href="{{ back }}">返回列表</a>
            </div>
            """,
            back=(request.referrer or "/?tab=xhs"),
        )
    return redirect(request.referrer or "/legacy?tab=xhs")


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    # Allow command-line environment variables (e.g. WEB_PORT) to override .env.
    load_dotenv(os.path.join(base_dir, ".env"), override=False)
    host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("WEB_PORT", "8080"))
    app.run(host=host, port=port, debug=False)
