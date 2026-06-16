## 当前线程：V2 样式合规改造 — 对齐 ui-rules.md

> 主线程下发 | 执行线程独立开发 | 所有细节已列明 | 不新增功能，只改样式

---

=== **背景** ===

`docs/guides/ui-rules.md` 已发布为全项目 UI 规范，但现有 CSS 和 JS 文件中存在 40 处不合规：蓝色残留（应改为绿色主色）、非标准字号（11px/13px/15px）、废弃 CSS 变量。本线程只做样式对齐，不新增任何功能。

---

=== **开工前必读（2个文件）** ===

| # | 文件 | 为什么读 |
|---|------|----------|
| 1 | `docs/guides/ui-rules.md` | 目标规范——所有颜色、字号、圆角、按钮标准 |
| 2 | `scripts/static/css/base.css` | CSS 变量定义，修改时确认变量存在 |

---

=== **改动范围** ===

| 文件 | 变更类型 | 改动说明 |
|------|------|------|
| `scripts/static/css/base.css` | 修改 | 14处：移除废弃变量/字号13px→12px/圆角统一/按钮色对齐 |
| `scripts/static/css/deconstruct.css` | 修改 | 17处：蓝色→绿色主色/11px→12px/13px→12px或14px |
| `scripts/static/js/note.js` | 修改 | 5处：color-blue→color-primary/11px→12px |
| `scripts/static/js/queue.js` | 修改 | 2处：accent-color/color 蓝色→绿色 |
| `scripts/web/templates/_components/status_badge.html` | 修改 | 状态系统对齐ui-rules Rule10 |
| `scripts/web/templates/landing.html` | 修改 | 模块名+emoji对齐新导航结构 |

---

=== **逐文件改动清单** ===

### 文件1：`scripts/static/css/base.css`（14处）

| # | 位置/查找 | 改动 |
|---|-----------|------|
| 1 | `--radius-sm: 6px;` `--radius-md: 8px;` `--radius-lg: 12px;` | 删除 `--radius-md` `--radius-lg`，只保留 `--radius: 12px;` `--radius-sm: 6px;` |
| 2 | `.score-label` 中的 `font-size: 13px` | → `font-size: var(--fs-meta)` 即 12px |
| 3 | `.score-value` 中的 `font-size: 13px` | → `font-size: var(--fs-meta)` |
| 4 | `.queue-card` 中 `font-size: 13px` | → `font-size: var(--fs-meta)` |
| 5 | `.empty-state p` 中 `font-size: 13px` | → `font-size: var(--fs-meta)` |
| 6 | `border-radius: var(--radius-md)` ×2处 | → `border-radius: var(--radius)` |
| 7 | `.queue-card:hover { border-color: var(--color-blue)` | → `var(--color-primary)` |
| 8 | `.queue-card.selected { border-color: var(--color-blue)` | → `var(--color-primary)` |
| 9 | `.score-track` 的 `background: #F3F4F6` → OK |
| 10 | `.score-fill.high { background: var(--color-green)` → `var(--color-success)` |
| 11 | `.score-fill.medium { background: var(--color-yellow)` → OK |
| 12 | `.score-fill.low { background: var(--color-red)` → OK |
| 13 | `.status-processing` 的 `var(--color-blue)` → **不改**（蓝色用于信息/生产中状态，符合ui-rules） |
| 14 | `.nav-links a.active` 已是 `var(--color-primary)` → 确认不改 |

### 文件2：`scripts/static/css/deconstruct.css`（17处）

| # | 查找 | 改动 |
|---|------|------|
| 1 | `border-radius: var(--radius-lg)` | → `var(--radius)` |
| 2 | `.dc-panel-header` `font-size: 13px` | → `var(--fs-meta)` |
| 3 | `.dc-filter input:focus { border-color: var(--color-blue)` | → `var(--color-primary)` |
| 4 | `.dc-chip { font-size: 11px` | → `var(--fs-meta)` |
| 5 | `.dc-chip:hover { border-color: var(--color-blue)` | → `var(--color-primary)` |
| 6 | `.dc-chip.active { background: #EFF6FF; color: var(--color-blue); border-color: var(--color-blue)` | → `background: #F0FDF4; color: var(--color-primary); border-color: var(--color-primary)` |
| 7 | `.dc-btn:hover { border-color: var(--color-blue); color: var(--color-blue)` | → `var(--color-primary); color: var(--color-primary)` |
| 8 | `.dc-btn.primary` 三处 `var(--color-blue)` | → `var(--color-primary)`，hover → `var(--color-primary-hover)` |
| 9 | `.dc-queue-item.selected { background: #EFF6FF; border: 1px solid var(--color-blue)` | → `background: #F0FDF4; border-color: var(--color-primary)` |
| 10 | `.dc-queue-item .qi-sub` `font-size: 11px` | → `var(--fs-meta)` |
| 11 | `.dc-section-head` `font-size: 13px` | → `var(--fs-body)` |
| 12 | `.dc-section-body` `font-size: 13px` | → `var(--fs-meta)` |
| 13 | `.dc-note-field label` `font-size: 11px` | → `var(--fs-meta)` |
| 14 | `.dc-note-field textarea/input` `font-size: 13px` | → `var(--fs-body)` |
| 15 | `.dc-note-field textarea:focus` `border-color: var(--color-blue)` | → `var(--color-primary)` |
| 16 | `.dc-ref-item:hover` `color: var(--color-blue)` | → `var(--color-primary)` |
| 17 | `.dc-ref-item input` `accent-color: var(--color-blue)` | → `var(--color-primary)` |
| 18 | `.dc-asset-thumb` `font-size: 11px` | → `var(--fs-meta)` |
| 19 | `.dc-empty` `font-size: 13px` | → `var(--fs-body)` |
| 20 | `.dc-meta` `font-size: 11px` | → `var(--fs-meta)` |
| 21 | `.dc-btn` `font-size: 12px` | OK |
| 22 | `.dc-filter input` `font-size: 12px` | OK |

### 文件3：`scripts/static/js/note.js`（5处）

| # | 查找 | 改动 |
|---|------|------|
| 1 | `style="color:var(--color-blue)"` | → `var(--color-primary)` |
| 2 | `style="font-size:11px"` ×3处 | → `12px` |
| 3 | `style="accent-color:var(--color-blue)"` | → `var(--color-primary)` |

### 文件4：`scripts/static/js/queue.js`（2处）

| # | 查找 | 改动 |
|---|------|------|
| 1 | `style="accent-color:var(--color-blue)"` | → `var(--color-primary)` |
| 2 | `color:var(--color-blue)` | → `var(--color-primary)` |

### 文件5：`scripts/web/templates/_components/status_badge.html`

根据 `docs/guides/ui-rules.md` Rule 10，状态系统改为 5 态：

```jinja2
{% macro status_badge(status, text=None) %}
  {% set labels = {
    "pending": "待处理",
    "processing": "生产中",
    "review": "待审核",
    "completed": "已完成",
    "failed": "失败"
  } %}
  ...
{% endmacro %}
```

同时保留 `"done"` 和 `"retry"` 的兼容映射（向后兼容旧队列数据）：
```python
# done → completed, retry → pending
```

### 文件6：`scripts/web/templates/landing.html`

模块列表对齐 `_nav.html`，增加选题池卡片：

```python
{% set modules = [
  {"icon": "&#x1F3E0;", "title": "工作台",     ...},
  {"icon": "&#x1F4D6;", "title": "选题池",     "url": "/topic-pool", "available": false},  # 新增
  {"icon": "&#x1F527;", "title": "拆文中心",   "url": "/deconstruct", "available": true},   # 改为 true
  {"icon": "&#x1F4DD;", "title": "笔记生成",   ...},
  {"icon": "&#x1F4DA;", "title": "知识库",     ...},
  {"icon": "&#x1F3AC;", "title": "视频脚本",   ...},
  {"icon": "&#x1F4CA;", "title": "数据中心",   ...},
] %}
```

---

=== **验证** ===

```bash
source .venv/bin/activate && python scripts/web_app.py
```

| # | 验证项 | 预期 |
|---|--------|------|
| 1 | `http://127.0.0.1:8080/deconstruct` | 页面正常，按钮/选中态为绿色非蓝色 |
| 2 | `http://127.0.0.1:8080/` | landing 页卡片正常，选题池/拆文中心可点击 |
| 3 | 搜索检查：`grep -r "color-blue\|13px\|11px\|--radius-lg\|--radius-md" scripts/static/` | **除了 status-processing 和 --color-blue 变量定义外，无其他残留** |
| 4 | 样式一致性 | 点击/hover/选中/active 全部使用绿色 #16A34A |

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b feature/v2-ui-compliance
```

### 结束时执行（必须）

```bash
git add -A
git commit -m "refactor: 样式对齐ui-rules — 绿色主色/统一字号/圆角规范/状态系统"
git push origin feature/v2-ui-compliance
```

---

=== **禁止事项** ===

- ❌ 不改任何业务逻辑（只改 CSS 和 JS 中的样式字符串）
- ❌ 不新增文件
- ❌ 不引入新依赖
- ❌ 不改 web_app_legacy.py
- ❌ CSS 变量名不能乱改（base.css 的 `:root` 变量名只能增删，不能改名）
