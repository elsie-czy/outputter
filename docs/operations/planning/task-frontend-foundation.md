## 当前线程：Sprint V2.0 — 前端架构地基搭建

> 主线程下发 | 执行线程独立开发 | 所有细节已在本文件列明 | 完成输出交接摘要

---

=== **背景** ===

当前 `web_app_legacy.py` 是 2876 行巨石：HTML 写死在 Python 字符串变量、CSS/JS 内联。V2 要拆成标准前端架构：独立 CSS 文件、Jinja2 模板继承、可复用组件。**本线程只打地基，不动旧版代码。**

---

=== **产出物清单** ===

```
scripts/
├── static/                          # Flask static_folder（需配置）
│   ├── css/
│   │   └── base.css                 # ← 0.3 产出，全文指定
│   ├── js/
│   │   └── .gitkeep                 # ← 0.1 产出，空目录占位
│   └── img/
│       └── .gitkeep                 # ← 0.1 产出，空目录占位
│
├── web/
│   └── templates/                   # Flask template_folder（需配置）
│       ├── base.html                # ← 0.4 产出，全文指定
│       ├── _nav.html                # ← 0.5 产出，全文指定
│       ├── landing.html             # ← 0.6 产出，全文指定
│       └── _components/
│           └── .gitkeep             # ← 0.2 产出，空目录占位
│
├── web_app_legacy.py                # 不改动
└── web/
    └── app.py                       # ← 只改一行：配置 template_folder/static_folder
```

---

=== **0.1 创建 static/ 目录结构** ===

```bash
mkdir -p scripts/static/css
mkdir -p scripts/static/js
mkdir -p scripts/static/img
touch scripts/static/js/.gitkeep
touch scripts/static/img/.gitkeep
```

---

=== **0.2 创建 templates/ 目录** ===

```bash
mkdir -p scripts/web/templates/_components
touch scripts/web/templates/_components/.gitkeep
```

---

=== **0.3 创建 static/css/base.css — 完整内容** ===

> 文件路径：`scripts/static/css/base.css`

```css
/* ===== RESET ===== */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

/* ===== CSS 变量（全部颜色从这里取，禁止在组件中硬编码色值）===== */
:root {
  /* 状态色 */
  --color-gray: #9CA3AF;
  --color-blue: #3B82F6;
  --color-green: #10B981;
  --color-red: #EF4444;
  --color-orange: #F59E0B;
  --color-yellow: #EAB308;

  /* 背景 */
  --bg-page: #F3F4F6;
  --bg-card: #FFFFFF;
  --bg-nav: #FFFFFF;
  --bg-hover: #F9FAFB;

  /* 文字 */
  --text-primary: #111827;
  --text-secondary: #6B7280;
  --text-muted: #9CA3AF;

  /* 边框 */
  --border: #E5E7EB;
  --border-light: #F3F4F6;

  /* 间距 */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  /* 圆角 */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);

  /* 字体 */
  --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  --font-mono: "SF Mono", "Fira Code", monospace;
}

/* ===== 基础样式 ===== */
html, body {
  height: 100%;
}

body {
  font-family: var(--font-family);
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-page);
  -webkit-font-smoothing: antialiased;
}

a {
  color: var(--color-blue);
  text-decoration: none;
}
a:hover { text-decoration: underline; }

/* ===== 布局 ===== */
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.main-content {
  flex: 1;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  padding: var(--space-lg);
}

/* ===== 卡片 ===== */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  box-shadow: var(--shadow-sm);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-lg);
}

/* ===== 导航栏（由 _nav.html 使用）===== */
.top-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--space-lg);
  background: var(--bg-nav);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.nav-brand a {
  color: var(--text-primary);
  text-decoration: none;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 4px;
  list-style: none;
}

.nav-links a {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  transition: background 0.15s, color 0.15s;
  white-space: nowrap;
}

.nav-links a:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.nav-links a.active {
  background: var(--bg-hover);
  color: var(--color-blue);
}

.nav-links a.disabled {
  color: var(--text-muted);
  cursor: not-allowed;
  pointer-events: none;
}

/* ===== 状态标签（供 _components/status_badge.html 使用）===== */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-pending  { background: #F3F4F6; color: var(--color-gray); }
.status-pending .status-dot { background: var(--color-gray); }

.status-processing { background: #EFF6FF; color: var(--color-blue); }
.status-processing .status-dot {
  background: var(--color-blue);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-done { background: #ECFDF5; color: var(--color-green); }
.status-done .status-dot { background: var(--color-green); }

.status-failed { background: #FEF2F2; color: var(--color-red); }
.status-failed .status-dot { background: var(--color-red); }

.status-retry { background: #FFF7ED; color: var(--color-orange); }
.status-retry .status-dot { background: var(--color-orange); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* ===== 评分进度条（供 _components/score_bar.html 使用）===== */
.score-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-bottom: var(--space-xs);
}

.score-label {
  width: 120px;
  font-size: 13px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.score-track {
  flex: 1;
  height: 8px;
  background: #F3F4F6;
  border-radius: 999px;
  overflow: hidden;
}

.score-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}

.score-fill.high   { background: var(--color-green); }
.score-fill.medium { background: var(--color-yellow); }
.score-fill.low    { background: var(--color-red); }

.score-value {
  width: 50px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
  flex-shrink: 0;
}

/* ===== Toast 通知（供 _components/toast.html 使用）===== */
.toast {
  position: fixed;
  top: 72px;
  right: var(--space-lg);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  box-shadow: var(--shadow-md);
  z-index: 200;
  animation: slideIn 0.3s ease;
}

.toast-success { background: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }
.toast-error   { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }
.toast-warning { background: #FFF7ED; color: #9A3412; border: 1px solid #FED7AA; }

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
}

/* ===== 队列卡片（供 _components/queue_card.html 使用）===== */
.queue-card {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-size: 13px;
}

.queue-card:hover { border-color: var(--color-blue); background: var(--bg-hover); }
.queue-card.selected { border-color: var(--color-blue); background: #EFF6FF; }

.queue-card .work-name { font-weight: 600; color: var(--text-primary); }
.queue-card .author { color: var(--text-secondary); }
.queue-card .platform { color: var(--text-muted); font-size: 12px; }

/* ===== 空状态（供 _components/empty_state.html 使用）===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl) var(--space-lg);
  color: var(--text-muted);
  text-align: center;
}

.empty-state .empty-icon { font-size: 48px; margin-bottom: var(--space-md); }
.empty-state h3 { font-size: 16px; color: var(--text-secondary); margin-bottom: var(--space-xs); }
.empty-state p { font-size: 13px; }

/* ===== 工具类 ===== */
.text-muted { color: var(--text-muted); }
.text-secondary { color: var(--text-secondary); }
.text-center { text-align: center; }
.mt-md { margin-top: var(--space-md); }
.mb-md { margin-bottom: var(--space-md); }
.flex-center { display: flex; align-items: center; justify-content: center; }
```

---

=== **0.4 创建 templates/base.html — 完整内容** ===

> 文件路径：`scripts/web/templates/base.html`
> 所有页面继承此骨架，只写 content block

```jinja2
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{% block title %}超级工具{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/base.css') }}" />
  {% block head %}{% endblock %}
</head>
<body>
  <div class="app-container">
    {% include "_nav.html" %}

    <main class="main-content">
      {% block content %}{% endblock %}
    </main>
  </div>

  {% block scripts %}{% endblock %}
</body>
</html>
```

**关键说明**：
- `{{ url_for('static', filename='css/base.css') }}` 让 Flask 自动计算 static 目录路径
- `{% include "_nav.html" %}` 在每个页面自动渲染导航
- body 里 `<div class="app-container">` 包裹全页，`<main class="main-content">` 是内容区
- 子页面只需填充 `{% block content %}` 和可选的 `{% block scripts %}`

---

=== **0.5 创建 templates/_nav.html — 完整内容** ===

> 文件路径：`scripts/web/templates/_nav.html`
> 被 base.html 通过 `{% include %}` 引用，在每个页面自动显示

```jinja2
{% set nav_items = [
    {"label": "工作台",   "url": "/#",         "key": "dashboard",   "available": false},
    {"label": "拆文中心", "url": "/#",         "key": "deconstruct", "available": false},
    {"label": "笔记生成", "url": "/#",         "key": "notes",       "available": false},
    {"label": "知识库",   "url": "/#",         "key": "knowledge",   "available": false},
    {"label": "视频脚本", "url": "/#",         "key": "video",       "available": false},
    {"label": "数据中心", "url": "/#",         "key": "data",        "available": false},
    {"label": "系统设置", "url": "/#",         "key": "settings",    "available": false},
] %}

{% set active = active_page|default("") %}

<nav class="top-nav">
  <div class="nav-brand">
    <span>&#x1F4DD;</span>
    <a href="/">超级工具</a>
  </div>

  <ul class="nav-links">
    {% for item in nav_items %}
      {% set is_active = (active == item.key) %}
      {% set css_class = [] %}
      {% if is_active %}{% set _ = css_class.append("active") %}{% endif %}
      {% if not item.available %}{% set _ = css_class.append("disabled") %}{% endif %}
      <li>
        <a href="{{ item.url }}"
           class="{{ css_class|join(' ') }}"
           {% if not item.available %}aria-disabled="true"{% endif %}>
          {{ item.label }}
        </a>
      </li>
    {% endfor %}
  </ul>
</nav>
```

**关键说明**：
- `available: false` — 所有页面链接当前都是 `disabled`（置灰不可点击），等各页面路由注册后再逐个改为 `true`
- `active_page` 变量由各页面路由传入，当前页高亮
- `disabled` 样式已在 base.css 中定义（cursor: not-allowed, pointer-events: none）
- 导航栏左侧 emoji `📝` + 文字"超级工具"，点击可回首页

---

=== **0.6 创建 templates/landing.html — 完整内容** ===

> 文件路径：`scripts/web/templates/landing.html`
> V2 首页，展示功能模块引导卡片

```jinja2
{% extends "base.html" %}

{% block title %}超级工具{% endblock %}

{% block content %}
<div style="padding-top: var(--space-xl);">

  <div style="text-align: center; margin-bottom: var(--space-xl);">
    <h1 style="font-size: 28px; font-weight: 700; color: var(--text-primary); margin-bottom: var(--space-sm);">
      &#x1F4DD; 超级工具 V2
    </h1>
    <p style="font-size: 15px; color: var(--text-secondary);">
      网文拆解 → 爆款基因 → 小红书笔记 · 一站式内容生产
    </p>
  </div>

  <div class="card-grid">

    {% set modules = [
      {"icon": "&#x1F3E0;", "title": "工作台", "desc": "任务队列概览、批量操作入口、统计面板", "url": "/dashboard", "available": false},
      {"icon": "&#x1F527;", "title": "拆文中心", "desc": "拆文队列管理、拆文结果预览、批量拆解", "url": "/deconstruct", "available": false},
      {"icon": "&#x1F4DD;", "title": "笔记生成", "desc": "小红书标题/正文/标签/互动话术 + AI评分", "url": "/notes", "available": false},
      {"icon": "&#x1F4DA;", "title": "知识库", "desc": "开篇套路/人物设定/冲突设计/情绪触发/金句", "url": "/knowledge", "available": false},
      {"icon": "&#x1F3AC;", "title": "视频脚本", "desc": "口播稿 + 分镜脚本生成（纯文本）", "url": "/video", "available": false},
      {"icon": "&#x1F4CA;", "title": "数据中心", "desc": "笔记效果统计 · AI评分分布 · 爆款因子", "url": "/data", "available": false},
    ] %}

    {% for mod in modules %}
    <div class="card" style="{% if not mod.available %}opacity: 0.5; cursor: not-allowed;{% endif %}">
      <div style="font-size: 32px; margin-bottom: var(--space-md);">{{ mod.icon|safe }}</div>
      <h2 style="font-size: 18px; font-weight: 600; margin-bottom: var(--space-xs); color: var(--text-primary);">
        {{ mod.title }}
        {% if not mod.available %}
          <span style="font-size: 11px; color: var(--text-muted); font-weight: 400;">（即将上线）</span>
        {% endif %}
      </h2>
      <p style="font-size: 13px; color: var(--text-secondary); line-height: 1.6;">{{ mod.desc }}</p>
      {% if mod.available %}
        <a href="{{ mod.url }}" style="display: inline-block; margin-top: var(--space-md); font-size: 13px; font-weight: 500;">
          进入 →
        </a>
      {% endif %}
    </div>
    {% endfor %}

  </div>

  <div style="text-align: center; margin-top: var(--space-xl); padding: var(--space-lg); color: var(--text-muted); font-size: 12px;">
    V2.0 开发中 · 旧版工具仍可用 → <a href="/legacy" style="color: var(--color-blue);">打开旧版</a>
  </div>

</div>
{% endblock %}
```

**关键说明**：
- 6 张卡片对应 6 个功能模块，全部 `available: false`（置灰 + 半透明）
- 当路由注册后，改为 `available: true` 即可激活
- 底部链接指向旧版 `/legacy`（Thread 3 会注册这个路由）
- 不依赖任何 JS，纯静态 HTML + Jinja2

---

=== **0.X 配置 Flask 的 template_folder / static_folder** ===

> 文件路径：`scripts/web/app.py`
> 修改 `create_app()` 函数，告知 Flask 模板和静态文件的新位置

**当前代码**：
```python
from scripts.web.routes import register_routes
from scripts.web_app_legacy import app as legacy_app

def create_app():
    register_routes(legacy_app)
    return legacy_app
```

**改为**：
```python
from scripts.web.routes import register_routes
from scripts.web_app_legacy import app as legacy_app
import os

def create_app():
    # 配置 V2 模板目录和静态资源目录
    base = os.path.dirname(__file__)
    legacy_app.template_folder = os.path.join(base, "templates")
    legacy_app.static_folder = os.path.join(base, "..", "static")
    legacy_app.static_url_path = "/static"

    register_routes(legacy_app)
    return legacy_app
```

**解释**：
- `template_folder` → `scripts/web/templates/`（相对路径，基于 Flask app 的 root_path）
- `static_folder` → `scripts/static/`（`..` 回退一级到 scripts 目录）
- `static_url_path="/static"` → 浏览器访问 `/static/css/base.css` 时 Flask 能正确返回文件
- 这段改动是**对 `app.py` 的最小修改**，不碰 `web_app_legacy.py`

---

=== **验证** ===

```bash
# 启动
cd /Users/lalalaba/Desktop/personal-supertool
source .venv/bin/activate
python scripts/web_app.py
```

### 验证清单（逐项确认）

| # | 操作 | 预期结果 |
|---|------|----------|
| 1 | `curl -s http://127.0.0.1:8080/static/css/base.css \| head -5` | 返回 CSS 文件前 5 行，非 404 |
| 2 | `curl -s http://127.0.0.1:8080/_health` | 返回 `{"ok":true}` |
| 3 | 浏览器打开 `http://127.0.0.1:8080/legacy` | 旧版页面正常（5 个 tab、样式完好） |
| 4 | **编写测试路由验证模板渲染**（见下方） | landing 页正确渲染 |

### 临时测试路由（验证完成后可删除）

在 `scripts/web/app.py` 中临时加一个路由来验证模板能渲染：

```python
# 临时测试路由 — 验证通过后删除
@legacy_app.route("/v2-test")
def v2_test():
    from flask import render_template
    return render_template("landing.html", active_page="")
```

然后浏览器访问 `http://127.0.0.1:8080/v2-test`，确认能看到：
- 顶部导航栏（所有链接置灰）
- 6 张功能模块卡片（半透明 + "即将上线"）
- 底部"旧版工具"链接

---

=== **规范要求** ===

- `docs/guides/线程协作规范.md` §二 核心红线、§五 交接摘要模板
- `docs/guides/开发规范手册.md` §1.3 Jinja2 模板规范、§二 文件长度限制
- `docs/guides/项目目录结构规范.md` 命名规范（文件名 snake_case）
- `docs/planning/V2_PLAN.md` §6 页面层级结构、§8.0 任务清单

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b feature/v2-frontend-arch-foundation
```

### 结束时执行（必须）

```bash
git add -A
git commit -m "feat: V2 前端地基 — base.css / base.html / _nav.html / landing.html + Flask 模板配置"
git push origin feature/v2-frontend-arch-foundation
```

---

=== **禁止事项** ===

- ❌ 不修改 `web_app_legacy.py` 任何代码
- ❌ 不在 HTML 中写内联 `<style>`（禁止通过，全部放 base.css）
- ❌ 不在 HTML 中写内联 `<script>`（禁止通过，后续放 static/js/）
- ❌ 不用 any CSS 框架（Bootstrap/Tailwind 等），全部手写
- ❌ 不在模板中写复杂 Python 逻辑
