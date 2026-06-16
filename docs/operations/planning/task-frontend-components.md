## 当前线程：Sprint V2.0 — 前端可复用组件

> 主线程下发 | 执行线程独立开发 | 依赖 Thread 1 完成 | 完成输出交接摘要

---

=== **背景** ===

前端架构地基（base.html / _nav.html / base.css）已就位。现在需要创建一套 Jinja2 可复用宏组件，供后续所有 V2 页面（拆文中心、工作台、笔记预览等）直接引用，保证 UI 一致性。

所有组件为 Jinja2 宏（`{% macro %}`），通过 `{% from "_components/xxx.html" import xxx %}` 引用。

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `templates/_components/status_badge.html` | **新建** | 状态标签宏，参数 `status`，输出带颜色+图标标签 |
| `templates/_components/score_bar.html` | **新建** | 评分进度条宏，参数 `label`/`score`/`max`，输出带颜色判断的进度条 |
| `templates/_components/queue_card.html` | **新建** | 队列任务卡片宏，参数 `task` 对象，渲染一行任务卡片 |
| `templates/_components/empty_state.html` | **新建** | 空状态占位宏，参数 `icon`/`title`/`description`，渲染居中引导提示 |
| `templates/_components/toast.html` | **新建** | Toast 通知宏，参数 `message`/`type`，渲染右上角浮动提示（需配合 JS 触发，本组件只做 HTML 结构） |

=== **技术要点** ===

### 1. status_badge.html
```
输入: status: str  — "pending" | "processing" | "done" | "failed" | "retry"
输出: <span class="status-badge status-{status}">
        <span class="status-dot"></span> {label}
      </span>
颜色: pending=灰, processing=蓝+脉冲动画, done=绿, failed=红, retry=橙
文本: pending→排队中, processing→处理中, done→已完成, failed→失败, retry→重试中
CSS: 复用 base.css 中 --color-* 变量
```

### 2. score_bar.html
```
输入: label: str, score: int, max: int (默认20)
输出: 一行包含 label + 进度条 + 分数
      <div class="score-row">
        <span class="score-label">{label}</span>
        <div class="score-bar" style="width:{score/max*100}%" class="score-{grade}"></div>
        <span>{score}/{max}</span>
      </div>
颜色: score/max >= 0.85 → 绿, >= 0.75 → 黄, < 0.75 → 红
```

### 3. queue_card.html
```
输入: task: dict  — {work_name, author, platform, category, status, score, record_id}
输出: 一行卡片 <div class="queue-card {selected}">
        <span class="check">☐</span>
        {status_badge(task.status)}
        <span class="work-name">{task.work_name}</span>
        <span class="author">{task.author}</span>
        <span class="platform">{task.platform}·{task.category}</span>
        {score 如果存在}
        <a href="?rid={task.record_id}" class="view-link">查看</a>
      </div>
复用: 内部调用 status_badge 宏
```

### 4. empty_state.html
```
输入: icon: str (可选emoji), title: str, description: str
输出: 居中占位区 <div class="empty-state">
        <div class="empty-icon">{icon|d("📭")}</div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
```

### 5. toast.html
```
输入: message: str, type: str — "success"|"error"|"warning"
输出: <div class="toast toast-{type}">
        <span class="toast-icon">{✓|✗|⚠}</span>
        <span class="toast-message">{message}</span>
      </div>
注意: 本组件只生成 HTML，显示/隐藏/自动消失由 JS 控制
```

### 通用约束
- 所有组件只用 Jinja2 宏，不写内联 JS
- 样式写在各组件的 `<style>` 块或追加到 base.css
- 颜色变量统一使用 base.css 中定义的 CSS 自定义属性
- 组件间可互相引用（如 queue_card 引用 status_badge）

=== **验证** ===

将 landing.html 修改为引用所有组件进行渲染测试：
```jinja2
{% from "_components/status_badge.html" import status_badge %}
{% from "_components/score_bar.html" import score_bar %}
{% from "_components/queue_card.html" import queue_card %}
{% from "_components/empty_state.html" import empty_state %}
{% from "_components/toast.html" import toast %}

{# 在 landing 页底部追加测试区 #}
{{ status_badge("pending") }}
{{ status_badge("done") }}
{{ score_bar("标题吸引力", 16, 20) }}
{{ queue_card({...}) }}
{{ empty_state(title="暂无任务", description="请先从选题库添加作品") }}
{{ toast(message="保存成功", type="success") }}
```

```bash
source .venv/bin/activate
python scripts/web_app.py
# 浏览器打开 http://127.0.0.1:8080/
# 确认 landing 页底部能正确渲染所有 5 个组件
```

=== **规范要求** ===

- 遵循 `docs/guides/线程协作规范.md` §五（交接摘要）、§八（文件长度控制：组件 ≤ 50 行）
- 遵循 `docs/planning/V2_PLAN.md` §8.0 任务清单 0.7-0.11

=== **分支** ===

```
git checkout feature/v2-frontend-arch-foundation
git checkout -b feature/v2-frontend-arch-components
```

### 结束时执行（必须）

```
git add -A
git commit -m "feat: V2 前端可复用组件 — status_badge / score_bar / queue_card / empty_state / toast"
```

=== **任务清单** ===

| # | 任务 | 产出物 |
|---|------|--------|
| 0.7 | 创建 `templates/_components/status_badge.html` 状态标签宏 | 状态组件 |
| 0.8 | 创建 `templates/_components/score_bar.html` 评分进度条宏 | 评分组件 |
| 0.9 | 创建 `templates/_components/queue_card.html` 队列卡片宏 | 队列组件 |
| 0.10 | 创建 `templates/_components/empty_state.html` 空状态占位宏 | 空状态组件 |
| 0.11 | 创建 `templates/_components/toast.html` Toast 通知宏 | Toast 组件 |
