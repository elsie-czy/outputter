## 当前线程：Sprint V2.0 — 前端架构地基搭建

> 主线程下发 | 执行线程独立开发 | 完成输出交接摘要

---

=== **背景** ===

当前 `web_app_legacy.py` 是 2876 行巨石：HTML 写死在 Python 字符串变量、CSS/JS 内联、所有页面逻辑在一个文件里。需要在不改动旧版代码的前提下，建立新页面架构标准，后续拆文中心、工作台等所有 V2 新页面都走新架构（Jinja2 独立模板 + 独立 CSS/JS + 可复用组件）。

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `static/css/base.css` | **新建** | 公共样式：CSS reset、字体、颜色变量、布局工具类、导航样式、状态标签颜色 |
| `static/js/` | **新建目录** | 后续 JS 模块存放位置，本线程只需建目录 + `.gitkeep` |
| `static/img/` | **新建目录** | 静态图片资源，建目录 + `.gitkeep` |
| `templates/base.html` | **新建** | 页面骨架：`<head>` 含 charset/viewport、`<link rel="stylesheet">` 引用 base.css、`{% block title %}`、`{% include "_nav.html" %}`、`{% block content %}`、`{% block scripts %}` |
| `templates/_nav.html` | **新建** | 导航栏组件：`<nav>` 含左侧 logo 链接 + 右侧 tab 列表（工作台/拆文中心/知识库/数据中心），`request.path` 判断当前页高亮 |
| `templates/landing.html` | **新建** | V2 首页占位：`{% extends "base.html" %}`，中间 `<main>` 区域渲染功能模块引导卡片（拆文中心、知识库、数据中心、视频脚本），每张卡片含标题+描述+点击跳转链接 |
| `templates/_components/` | **新建目录** | 可复用 Jinja2 宏组件目录，本线程只需建目录 + `.gitkeep` |

=== **技术要点** ===

1. **不引入前端框架**：纯 Flask + Jinja2 模板，CSS 手写，JS 后续用 Vanilla JS
2. **模板继承**：`base.html` 是骨架，所有页面 `{% extends "base.html" %}` 并填充 `title`/`content`/`scripts` block
3. **导航高亮**：用 `{% if request.path == '/deconstruct' %}active{% endif %}` 或通过传参 `active_page` 变量控制
4. **颜色变量**：CSS 变量 定义在 `:root`，后续组件直接用 `var(--color-success)` 等
   ```
   状态色：--color-gray #9CA3AF | --color-blue #3B82F6 | --color-green #10B981 | --color-red #EF4444 | --color-orange #F59E0B
   背景色：--bg-main #F9FAFB | --bg-card #FFFFFF
   文字色：--text-primary #111827 | --text-secondary #6B7280
   ```
5. **响应式**：简单 `max-width` + flex/grid 即可，不做移动端适配
6. **不碰旧版**：不修改 `web_app_legacy.py` 任何代码

=== **验证** ===

```bash
# 启动 Flask 并验证
source .venv/bin/activate
python scripts/web_app.py

# 手动验证：
# 1. 浏览器打开 http://127.0.0.1:8080/ → landing 首页正常渲染
# 2. 导航栏链接正确可点击
# 3. 页面样式正常（字体、颜色变量生效）
# 4. 旧版页面 http://127.0.0.1:8080/?tab=overview 仍然正常
```

=== **规范要求** ===

- 遵循 `docs/线程协作规范.md` §二（核心红线）、§五（交接摘要）、§七（开场模板）
- 遵循 `docs/V2_PLAN.md` §6 页面架构 技术方案
- 遵循 `docs/V2_PLAN.md` §8.0 任务清单

=== **分支** ===

```
git checkout main
git pull --ff-only origin main   # 如无 origin 则跳过
git checkout -b feature/v2-frontend-arch-foundation
```

### 结束时执行（必须）

```
git add -A
git commit -m "feat: V2 前端架构地基 — base.css / base.html / _nav.html / landing.html"
```

=== **任务清单** ===

| # | 任务 | 产出物 |
|---|------|--------|
| 0.1 | 创建 `static/css/` `static/js/` `static/img/` 目录 + `.gitkeep` | 目录就位 |
| 0.2 | 确保 `templates/` 存在，建 `_components/` 子目录 + `.gitkeep` | 目录就位 |
| 0.3 | 创建 `static/css/base.css` 公共样式文件 | CSS 文件 |
| 0.4 | 创建 `templates/base.html` 页面骨架模板 | 骨架模板 |
| 0.5 | 创建 `templates/_nav.html` 导航栏组件 | 导航组件 |
| 0.6 | 创建 `templates/landing.html` V2 首页 | 首页模板 |
