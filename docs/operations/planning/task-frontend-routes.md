## 当前线程：Sprint V2.0 — 前端路由注册 + 旧版入口 + 验证

> 主线程下发 | 执行线程独立开发 | 依赖 Thread 1+2 完成 | 完成输出交接摘要

---

=== **背景** ===

地基模板（base.html / _nav.html / landing.html）和 5 个可复用组件已就位。现在需要：
1. 注册新页面路由，让 `http://127.0.0.1:8080/` 渲染新版 landing 页
2. 在旧版 web_app_legacy.py 侧边栏加一个"新版工具"入口链接
3. 验证新旧页面共存无冲突

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/web/routes/landing_page.py` | **新建** | Flask Blueprint，注册 `/` 和 `/deconstruct` 路由 |
| `scripts/web/routes/__init__.py` | **修改** | import 并注册 landing_page Blueprint |
| `scripts/web_app_legacy.py` | **最小修改** | 侧边栏 `<ul>` 追加一行 `<li><a>` 链接到新版首页 |
| `docs/planning/V2_PLAN.md` | **修改** | 更新任务清单 0.12-0.15 状态为 ☑ |

=== **技术要点** ===

### 1. landing_page.py

```python
from flask import Blueprint, render_template

bp = Blueprint("web_landing", __name__)

@bp.get("/")
def landing():
    return render_template("landing.html", active_page="home")

@bp.get("/deconstruct")
def deconstruct_page():
    # 拆文中心页面暂未实现，先返回占位
    return render_template("landing.html", active_page="deconstruct")
```

**关键约束**：
- `bp` 命名为 `web_landing`，确保不与旧版 blueprint 冲突
- `url_prefix` 不设置，直接用 `/`
- 确保 `/` 路由在旧版 `web_app_legacy.py` 的 `/` 路由之前注册（通过 `__init__.py` 中的注册顺序控制）
  - 因为 `create_app()` 中先调用 `register_routes(legacy_app)`，旧版路由先注册，新版后注册
  - Flask 路由匹配是 LIFO（后注册优先），所以新版 `/` 会优先于旧版 `/`
  - **这是预期行为**：新版首页替代旧版首页

### 2. __init__.py 修改

```python
from scripts.web.routes.health import bp as health_bp
from scripts.web.routes.system_api import bp as system_api_bp
from scripts.web.routes.xhs_api import bp as xhs_api_bp
from scripts.web.routes.landing_page import bp as landing_bp  # 新增

def register_routes(app):
    if "web_health" not in app.blueprints:
        app.register_blueprint(health_bp)
    if "web_system_api" not in app.blueprints:
        app.register_blueprint(system_api_bp)
    if "web_xhs_api" not in app.blueprints:
        app.register_blueprint(xhs_api_bp)
    if "web_landing" not in app.blueprints:   # 新增
        app.register_blueprint(landing_bp)    # 新增
```

### 3. web_app_legacy.py 最小修改

在旧版侧边栏 `<ul class="sidebar-nav">` 最底部追加一个 `<li>`：

```html
<li style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px">
  <a href="/" style="color:var(--color-blue);font-weight:600">
    🆕 新版工具
  </a>
</li>
```

不删除不修改旧版任何其他代码。位置在旧版 5 个 tab 链接之后。

### 4. 旧版路由保护

旧版 tab 路由通过 `?tab=xxx` query param 工作。新版 `/` 会覆盖旧版 `/`，但旧版的 `/` 路由需要保留以便通过 `/` + query param 访问旧版。

解决方案：在旧版 `index()` 路由中去掉 `/`，改用 `/legacy`，或者保持旧版路由但确保旧版页面仍可通过某种方式访问。

**现在用简单方案**：旧版 `/` 路由保留不动（Flask 后注册优先，新版 landing 覆盖），但旧版可改为 `/legacy` 或保持现状。实际上 Flask 的 URL 规则是后注册的优先，但参数化路由（`/` vs `/?tab=`）可能不同。

**关键检查**：确认 `web_app_legacy.py` 中 `index()` 路由的定义：
```python
@app.route("/")
def index():
    ...
```
这个路由会和新版 landing_page 的 `@bp.get("/")` 冲突。Flask 规则：同一个 app 上，后注册的 blueprint 路由优先于先注册的。

**结论**：把旧版 index 路由改为 `/legacy`：
```
旧版: @app.route("/legacy")  → def index():
新版: @bp.get("/")           → def landing():
```
这样新旧各自独立，不冲突。旧版导航入口链接也改为 `/legacy`。

**详细修改部分**：

web_app_legacy.py 改动：
- 第 1774 行附近 `@app.route("/")` → `@app.route("/legacy")`  
- 侧边栏 logo 链接改为 `/legacy`
- 之后追加新版入口 `<li>`

### 5. 路由规范约定更新

更新 `docs/planning/V2_PLAN.md` 中的 0.12 任务状态，确认规范已在文档中明确（§6 页面架构 技术方案部分）。

=== **验证** ===

```bash
source .venv/bin/activate
python scripts/web_app.py
```

手动验证：

| # | 验证项 | 预期 |
|---|--------|------|
| 1 | `http://127.0.0.1:8080/` | 新版 landing 页（功能模块引导卡片） |
| 2 | `http://127.0.0.1:8080/legacy` | 旧版页面，5 个 tab 正常 |
| 3 | `http://127.0.0.1:8080/deconstruct` | 占位页（或 landing） |
| 4 | `http://127.0.0.1:8080/_health` | 健康检查 JSON 正常 |
| 5 | `/api/system/local-summary` | API 正常 |
| 6 | landing 页导航栏点击各 tab | 链接正确 |
| 7 | landing 页底部组件渲染区 | 5 个组件正确渲染 |
| 8 | 旧版侧边栏"新版工具"链接 | 点击跳转到 `/` |

=== **规范要求** ===

- 遵循 `docs/guides/线程协作规范.md` §五（交接摘要）、§六（文档更新）
- 遵循 `docs/planning/V2_PLAN.md` §8.0 任务清单 0.12-0.15

=== **分支** ===

```
git checkout feature/v2-frontend-arch-components
git checkout -b feature/v2-frontend-arch-routes
```

### 结束时执行（必须）

```
git add -A
git commit -m "feat: V2 前端路由注册 — landing_page blueprint + /legacy 旧版保护 + 导航入口"
```

=== **任务清单** ===

| # | 任务 | 产出物 |
|---|------|--------|
| 0.12 | 新页面路由规范约定（确认 `docs/planning/V2_PLAN.md` §6 技术方案 已明确） | 规范确认 |
| 0.13 | 创建 `scripts/web/routes/landing_page.py` + 注册到 `__init__.py` | 路由文件 |
| 0.14 | 旧版 `web_app_legacy.py` 修改：`/` → `/legacy` + 侧边栏追加新版入口 | 旧版兼容 |
| 0.15 | 启动验证所有人项：新旧页面共存、API 正常、组件渲染、导航正确 | 验收通过 |
