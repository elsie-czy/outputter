## 当前线程：Sprint V2.0 — 选题池页面开发

> 主线程下发 | 执行线程独立开发 | 所有规格已在本文档列明

---

=== **背景** ===

当前项目缺少选题管理入口。选题需在飞书表格手动操作，然后通过 API 入队。需要建设选题池页面，实现选题浏览→筛选→评估→批量提交生产的完整入口。

--- 

=== **开工前必读（5个文件）** ===

| # | 文件 | 为什么读 |
|---|------|----------|
| 1 | `docs/ui-rules.md` | **全项目 UI 规范**，颜色/字体/卡片/按钮/状态/图标全部从这里取 |
| 2 | `docs/项目目录结构规范.md` | 模板文件放哪、CSS/JS 放哪、命名规范 |
| 3 | `docs/开发规范手册.md` | Jinja2 模板规范、JS 编码规范、文件长度限制 |
| 4 | `docs/线程协作规范.md` | 分支规则、提交格式、交接摘要模板 |
| 5 | `docs/V2_PLAN.md` §6 页面层级结构 | 导航架构、页面与模板映射关系 |

---

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/web/templates/topic_pool.html` | **新建** | 选题池页面模板，继承 base.html |
| `scripts/static/css/topic_pool.css` | **新建** | 选题池页面样式 |
| `scripts/static/js/topic_pool.js` | **新建** | 选题池交互逻辑（筛选/多选/提交/KPI轮询） |
| `scripts/web/routes/topic_pool_page.py` | **新建** | `/topic-pool` 页面路由 + `/api/topic-pool/stats` API |
| `scripts/web/routes/__init__.py` | **修改** | 注册 topic_pool_page blueprint |
| `scripts/web/templates/_nav.html` | **修改** | 导航栏"选题池"链接从 disabled 改为 可点击 |
| `scripts/web/templates/landing.html` | **修改** | 选题池卡片从置灰改为可点击 |

---

=== **技术要点** ===

### 1. 页面路由

```python
# scripts/web/routes/topic_pool_page.py

from flask import Blueprint, jsonify, render_template
from scripts.queue_manager import get_queue

bp = Blueprint("web_topic_pool", __name__)

@bp.get("/topic-pool")
def topic_pool_page():
    return render_template("topic_pool.html", active_page="topic_pool")

@bp.get("/api/topic-pool/stats")
def topic_pool_stats():
    """顶部 KPI 统计"""
    items = get_queue().get("items", [])
    selected = sum(1 for i in items if i.get("status") == "pending")
    return jsonify({
        "ok": True,
        "data": {
            "pending_topics": len(items),
            "today_added": 0,      # 暂不接入实时数据
            "high_potential": 0,   # 暂不接入评分
            "selected_count": selected,
        }
    })
```

### 2. 数据来源

选题池数据来自队列文件 `data/queue/deconstruct_queue.jsonl`。已有 API `GET /api/deconstruct/queue` 返回列表，**复用此 API** 作为选题列表数据源，不新建接口。

提交生产调用已存在的 `POST /api/deconstruct/batch-enqueue`。

### 3. 页面布局

```
┌─ 顶部统计区 (KPI 4 卡片，高度 100px) ──────────────────────┐
│ 待拆作品 56  │  今日新增 12  │  高潜作品 18  │  已选作品 3  │
├──────────────┬──────────────────────────────────────────────┤
│  选题列表 70% │  生产计划区 30%（固定吸顶）                    │
│              │                                              │
│  ┌搜索+筛选┐ │  ┌── 已选作品 3篇 ────────────────────────┐ │
│  │ ......  │ │  │  分类: 都市 2  幻言 1                  │ │
│  └─────────┘ │  │  平台: 起点 2  晋江 1                  │ │
│              │  │  均分: 83                                │ │
│  ┌─卡片──┐  │  │                                          │ │
│  │☐ 书名 │  │  │  ┌──────────────────────────────────┐  │ │
│  │作者    │  │  │  │     提交生产（3篇）              │  │ │
│  │数据... │  │  │  └──────────────────────────────────┘  │ │
│  └───────┘  │  └───────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────┘
```

### 4. 选题卡片规格

```css
/* 每行 2 列 */
.topic-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--gap);
}

/* 卡片高 220px */
.topic-card {
  height: 220px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-md);
}

.topic-card.selected {
  border-color: var(--color-primary);
  background: #F0FDF4;
}
```

卡片内容字段和顺序：
```
☐ 复选框（左上角）
作品名称  18px 600
作者      12px --text-muted
平台·分类  12px --text-muted
收藏 x.xk | 点赞 x.xk | 评论 xxx | 排名 #xx
综合评分 XX 🔥
```

### 5. 评分展示

```
90+ → S级爆款   #EF4444  红色
80+ → A级推荐   #F59E0B  橙色
70+ → B级可拆   #16A34A  绿色
60- → C级观察   #94A3B8  灰色
```

### 6. 生产计划区（右侧面板）

```
结构顺序（从上到下）：
  · 已选作品 X篇
  · 分类分布
  · 平台分布
  · 平均评分
  · 预计 Token 消耗
  · 预计耗时
  · 预计产出（拆文报告X份/笔记初稿X篇/评分报告X份）
  · [提交生产（N篇）] 按钮  ← 固定底部
```

### 7. 提交生产弹窗

```
确认提交生产
本次共选择：
  · 废材小姐被退婚后
  · 全球高考
  · 豪门再临
执行流程：✓ 拆文分析 ✓ 笔记生成 ✓ AI评分
预计耗时：3分钟

[取消]  [确认提交]
```

点击确认 → 调用 `POST /api/deconstruct/batch-enqueue` → 成功后提示 → 跳转 `/production-center`（暂跳 `/deconstruct` 作为临时兜底）

### 8. 顶部 KPI 卡片规格

```css
.kpi-card {
  width: 220px;
  height: 100px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.kpi-card .kpi-value { font-size: var(--fs-title); font-weight: 600; }
.kpi-card .kpi-label { font-size: var(--fs-meta); color: var(--text-muted); }
.kpi-card .kpi-trend { font-size: var(--fs-meta); }
```

---

=== **UI 规范硬性要求** ===

| 项目 | 必须 | 禁止 |
|------|------|------|
| 颜色 | var(--color-primary) 绿色主色 | 硬编码色值 / 超过5种色 |
| 字体 | 24px/18px/14px/12px | 11px/13px/15px/17px |
| 圆角 | 12px 统一 | 8px/16px 混用 |
| 图标 | emoji &#x 编码 | lucide-react/font-awesome |
| 状态 | pending/processing/review/completed/failed | 自定义状态名 |
| 空状态 | 必须显示引导文案+按钮 | 空白 |
| 卡片 | bg:#fff border:#e5e7eb | 渐变/彩色边框 |
| 主按钮 | 绿色 #16A34A 每页只有1个 | 一页3个绿色按钮 |
| 模块间距 | gap:16px 统一 | 忽大忽小 |
| 页面宽度 | max-width:1600px padding:24px | 顶边贴死 |

---

=== **复用的现有 API（不需要新建）** ===

| API | 方法 | 用途 |
|-----|------|------|
| `/api/deconstruct/queue?per_page=200` | GET | 选题列表数据源 |
| `/api/deconstruct/batch-enqueue` | POST | 提交生产 |

---

=== **验证** ===

```bash
source .venv/bin/activate && python scripts/web_app.py
```

| # | 验证项 | 预期 |
|---|--------|------|
| 1 | `http://127.0.0.1:8080/topic-pool` | 选题池页面正常渲染 |
| 2 | 顶部4个KPI卡片 | 数据正确（待拆/新增/高潜/已选） |
| 3 | 选题列表 | 显示队列中所有 pending 状态任务 |
| 4 | 搜索框输入作者名 | 列表实时过滤 |
| 5 | 平台筛选点击 | 列表过滤 |
| 6 | 勾选卡片 | 右侧已选计数更新 |
| 7 | 右侧面板 | 显示分类分布/平台分布/均分/预计产出 |
| 8 | 点击提交生产 | 弹窗确认 → 调用 API → 成功提示 |
| 9 | 导航栏"选题池" | 为 active 态（绿色高亮） |
| 10 | landing 页选题池卡片 | 可点击跳转 |

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b feature/v2-topic-pool
```

### 结束时执行（必须）

```bash
git add -A
git commit -m "feat: 选题池页面 — 选题列表/筛选/KPI/批量提交生产"
git push origin feature/v2-topic-pool
```

---

=== **禁止事项** ===

- ❌ 不修改 `web_app_legacy.py`
- ❌ 不引入任何 npm 包 / JS 框架 / CSS 框架
- ❌ 不硬编码颜色值（必须 var(--color-*)）
- ❌ 不使用非标准字号（24/18/14/12 以外）
- ❌ 不在一个区域放多个主按钮
- ❌ 不写内联 `<style>` 或 `<script>`（放 static/ 目录）
