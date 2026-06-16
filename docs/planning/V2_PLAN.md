# personal-supertool V2 规划

> 2026-06-10 | 基于 v1.0/v1.1 现状制定

---

## 0. V2 核心原则

V2 不追求功能数量，追求一个核心指标：

**一个运营人员一天能产出多少可发布的笔记。**

当前瓶颈不是"功能不够多"，而是：

- 一次只能拆一篇（无批量）
- 生成质量波动大，人工修改量高（无对标、无反馈闭环）
- 拆文结果不缓存，重复调用浪费成本且结果不一致

V2 的每个迭代必须直接服务于降低人工修改量或提升单日产稿数。

---

## 1. V2 功能范围

### 1.1 V2 做

| 功能 | 优先级 | 预期收益 |
|------|--------|----------|
| 批量拆文队列 | P0 | 日产能从 5-10 篇 → 30-50 篇 |
| 笔记参考样本注入（few-shot） | P0 | 生成质量对标感增强，减少修改 |
| 人工反馈闭环 | P1 | 唯一实质降低修改量的手段 |
| 拆文结果缓存 | P1 | 减少 LLM 调用成本，保证一致性 |
| AI 质量评分 | P1 | 自动拦截低质内容，减少人工筛查 |
| 视频脚本生成（纯文本） | P2 | 视频内容生产的第一步，不渲染 |
| 小红书笔记库增强（发布状态+修改历史） | P2 | 支撑发布流程和数据回收 |

### 1.2 V2 明确不做

| 功能 | 原因 |
|------|------|
| 自动发布到小红书 | 需小红书 API 逆向/对接，非技术瓶颈，先解决内容质量 |
| 视频渲染/合成 | 图文质量稳定后再投入，避免两级 AI 不确定性叠加 |
| 数据分析引擎 | 数据量不够时分析无意义，先积累 500+ 笔记效果数据 |
| 知识库资产化/向量检索 | V3 的事，需要先积累足够拆解记录 |
| 销售版/自用版双分支 | 用 feature flag 配置化代替，不拆代码分支 |
| 改造成 SaaS 多租户 | 当前单人使用，基础设施不支撑 |

---

## 2. 功能详细设计

### 2.1 批量拆文队列（P0）

**现状**：`deconstruct_daily.py` 单次执行，`select_work_from_topic_library.py` 每次只选一篇标记为"已拆解"的作品。

**目标**：选题库选中 N 篇 → 入队列 → 顺序或并行消费 → 各自走完整拆文流程。

**实现路径**：

```
选题库 → 勾选多篇"是否拆解=true"
         ↓
      写入 data/queue/deconstruct_queue.jsonl
         ↓
      scripts/deconstruct_worker.py（新脚本）
         ├─ 逐条消费队列
         ├─ 调 model_adapter.py 拆文
         ├─ 调 related_sync.py 写知识库
         ├─ 调 image_generator.py 入队生图
         └─ 更新队列状态（pending/processing/done/failed）
```

**状态机**：

```
pending    → 待处理
processing → 处理中（加文件锁防并发）
done       → 已完成
failed     → 失败（记录错误原因）
retry      → 可重试（人工或自动）
```

**触发方式**：

- 手动：Web 页面点击"批量拆解"
- 定时：cron 每 30 分钟扫描队列
- Docker：`deconstruct-runner` 容器改为常驻循环消费模式

**不引入消息队列**：用 JSONL 文件 + 文件锁即可，当前量级不需要 Redis/RabbitMQ。

**工作量**：~300 行（新脚本 + 队列文件读写 + Web 触发按钮）

---

### 2.2 笔记参考样本注入 / Few-shot（P0）

**现状**：`model_adapter.py` 每次生成笔记全靠 prompt 描述格式，没有参考样本，模型容易"自由发挥"导致风格漂移。

**目标**：从飞书笔记结果库取历史爆款笔记（点赞+收藏 top 3）作为 few-shot 注入 prompt。

**实现路径**：

```
1. hot_model_report.py 已有按效果排序的能力，复用其读取逻辑
2. model_adapter.py analyze_work() 新增参数 reference_notes: list[dict]
3. prompt 模板追加：
   "以下是本账号历史表现最好的3篇笔记，请参考其风格和结构：\n{ref1}\n{ref2}\n{ref3}"
4. feishu_client.py 新增方法 get_top_notes(limit=3) 读笔记结果库
```

**关键约束**：
- few-shot 必须来自**同一个账号**的历史数据，跨账号风格不可通用
- 如果笔记结果库为空（新账号），降级为无参考模式

**工作量**：~150 行（model_adapter 加参 + feishu_client 加方法）

---

### 2.3 人工反馈闭环（P1）

**现状**：运营在飞书笔记库里手动改标题/正文/标签，改完就结束了，模型下次生成继续犯同样的错。

**目标**：记录每次人工修改，下次生成时注入"历史修改偏好"。

**实现路径**：

```
1. 飞书小红书笔记库新增字段：
   - 修改日志（文本，追加格式）："标题改为 XX 风格 | 去掉 XX 标签 | 正文缩短至 300 字"
   - 修改后评分（数字，运营自评）：1-5 分

2. model_adapter.py 生成 prompt 追加：
   "以下是运营最近修改笔记的偏好记录：\n{recent_feedback}\n请避免类似问题。"

3. feishu_client.py 新增方法 get_recent_modifications(author, limit=5)
   读笔记库"修改日志"字段，取最近 5 条

4. Web 页面笔记预览 tab 加一个"保存修改"按钮
   点击后 diff 原始内容 vs 当前内容，写入修改日志
```

**为什么这是降低修改量的唯一手段**：
- AI 质量评分只能拦截低分，解决不了高分仍需改的问题
- 只有让模型知道"上次哪里改过、改成了什么样"，才能持续逼近运营要的风格

**工作量**：~400 行（feishu schema + model_adapter + Web diff + 保存逻辑）

---

### 2.4 拆文结果缓存（P1）

**现状**：同一本书如果被重新触发拆解，会重新调 LLM，结果不同 → 笔记不同 → 不一致。

**目标**：拆文结果写入飞书主表后，下次同一作品+作者直接读缓存。

**实现路径**：

```
1. deconstruct_daily.py 开头加查重：
   检查飞书主表是否存在 作品名称+作者 且 拆解时间不为空
   如果存在 → 读飞书字段组装 result → 跳过 LLM 调用

2. 如果缓存命中但图片缺失 → 只补跑图片生成

3. 加一个"强制重拆"参数，手动触发时允许绕过缓存
```

**工作量**：~100 行（deconstruct_daily.py 头部加查重逻辑）

---

### 2.5 AI 质量评分（P1）

**目标**：生成笔记后自动评分，低于阈值自动重试，减少人工筛选成本。

**评分维度**：

```
标题吸引力      0-20  够不够抓人
情绪浓度        0-20  是否引发共鸣/好奇/痛点
收藏价值        0-20  是否让人想收藏
互动引导        0-15  是否有钩子引导评论
小红书风格匹配   0-15  是否像真人笔记
AI痕迹          0-10  是否一眼 AI（扣分项）
─────────────────────
总分            0-100
```

**评分规则**：

```
< 75   → 自动重生成（最多 3 次，取最高分）
75-85  → 标记"需人工审核"，Web 页面高亮
> 85   → 直接通过，标注"推荐发布"
```

**实现**：
- 单独一次 LLM 调用做评分（prompt 输入笔记内容，输出 JSON 评分）
- 不增加生成阶段的 prompt 复杂度

**工作量**：~200 行（`scripts/quality_scorer.py` + model_adapter 调用 + Web 展示）

---

### 2.6 视频脚本生成 / 纯文本（P2）

**目标**：基于拆文结果 + 笔记内容，生成视频口播脚本和分镜描述，不渲染视频。

**产出物**：

```
视频标题
视频标签
口播稿全文（200-300 字，适合 30-60 秒视频）
分镜脚本：
  - 镜头 1：画面描述 + 字幕 + 配音
  - 镜头 2：...
  - 镜头 3-5：...
```

**输入**：拆文结果 JSON + 小红书笔记 markdown

**实现**：`model_adapter.py` 新增 `generate_video_script(analysis_result, note_md)` 方法

**不做的原因**：视频渲染需要 stable diffusion / runway 等能力，投入产出不成比例。先验证脚本可用性，脚本跑通后再考虑渲染。

**工作量**：~300 行（model_adapter 新方法 + Web 展示 + 飞书视频脚本字段）

---

### 2.7 小红书笔记库增强（P2）

**新增字段**：

```
发布状态    单选：未发布 / 已发布 / 待修改
发布时间    日期
发布链接    文本（小红书笔记链接）
修改日志    文本（累积追加）
修改后评分  数字（1-5）
```

**Web 增强**：
- 笔记库列表增加筛选：按发布状态 / 质量评分
- 增加"批量导出"按钮：导出选中笔记为 markdown 文件

**工作量**：~200 行（schema + feishu_client + Web 页面）

---

## 3. 技术架构演进

### V1 → V2 变化

```
V1:
  python scripts/deconstruct_daily.py  # 单次执行
  python scripts/web_app.py           # Flask 单进程

V2:
  scripts/deconstruct_worker.py       # 队列消费（常驻或 cron 触发）
  scripts/quality_scorer.py           # 质量评分模块（新）
  scripts/web_app.py                  # 不变，加新路由
  model_adapter.py                    # 加 few-shot + feedback + video 参数
```

**不动的东西**：
- 飞书多维表格继续做主数据源
- Flask 继续做 Web 框架
- 不引入新数据库（不用 PostgreSQL/MySQL）
- 不引入消息队列（不用 Redis/RabbitMQ）
- 不引入 ORM

**为什么不动**：当前量级（单人、一天几十篇）不需要这些基础设施，加了反增运维成本。

---

## 4. 迭代计划

### V2.0 — 效率底座（2-3 天）

```
☐ 批量拆文队列
☐ 笔记参考样本注入（few-shot）
☐ 拆文结果缓存
```

**验收标准**：选题库勾选 10 篇 → 一键批量拆解 → 10 篇笔记全量产出。

### V2.1 — 质量闭环（2-3 天）

```
☐ AI 质量评分
☐ 人工反馈闭环
☐ 笔记库 Web 增强（筛选/导出）
```

**验收标准**：生成笔记自动评分，低分自动重试，修改偏好被记录并在下次生成中体现。

### V2.2 — 视频初探（2-3 天）

```
☐ 视频脚本生成（纯文本）
☐ 视频脚本 Web 预览
☐ 飞书视频脚本字段落地
```

**验收标准**：一篇拆文结果 → 一键生成口播稿 + 分镜脚本。

---

## 5. 不做但记下来的事（V3+）

```
☐ 视频渲染/合成
☐ 小红书自动发布
☐ 数据分析引擎（爆文/规律/AB实验自动分析）
☐ 知识库向量化 + 语义检索 + 重组生成
☐ 多账号支持
☐ SaaS 化
```

---

## 6. 页面架构

V2 前端从当前单一 Flask 内嵌页面（web_app_legacy.py 2876 行）拆分为多页面结构。

### 页面总览

| 页面 | 功能核心 | 优先级 | 理由 |
|------|---------|--------|------|
| 工作台 Dashboard | 任务队列概览、批量操作入口、统计面板 | P0 | 账号A每日内容生产核心入口 |
| 拆文中心 | 拆文队列管理、拆文结果预览 | P0 | 直接影响拆文效率 |
| 笔记生成/预览 | 小红书标题、正文、互动话术、AI评分 | P0 | 直接影响产出质量 |
| 知识库中心 | 子库浏览、条目详情 | P1 | 可用飞书表格暂代 |
| 视频脚本 | 视频脚本文本生成、分镜预览 | P1 | 只做文本，不做视频生成 |
| 任务中心 | 全部任务列表 | P1 | 批量拆文辅助管理 |
| 数据中心 | 笔记结果统计、AI评分、爆款因子 | P1 | 支撑参考笔记注入 |
| 发布管理 | 待发布列表、状态追踪 | P2 | 先手动发布 |
| 案例分析 | 成长/爆文/失败/AB实验 | P2 | 账号B素材来源 |
| 实验管理 | AB实验创建与分析 | P2 | 可手工管理 |
| 系统设置 | 模型/API/Feature flag | P2 | 初期硬编码 |

### 页面与迭代对应

```
V2.0 实现：
  工作台 Dashboard（P0）
  拆文中心（P0）
  笔记生成/预览（P0）
  任务中心（P1）← 基础版列表

V2.1 实现：
  知识库中心（P1）
  数据中心（P1）

V2.2 实现：
  视频脚本（P1）
  发布管理（P2）

V3+ 实现：
  案例分析（P2）
  实验管理（P2）
  系统设置（P2）
```

### 页面层级结构

```
V2 页面树
│
├── 🏠 工作台            /dashboard         # V2.0 首页，登录后默认跳转
│   ├── 📋 任务中心       /tasks             # V2.0，全部任务列表
│   │   └── 任务详情       /tasks/<id>        # V2.1
│   └── 📤 发布管理       /publish           # V2.2，待发布列表
│
├── 🔧 拆文中心            /deconstruct       # V2.0，核心功能页面
│   └── 拆文结果详情       内嵌面板，不独立路由   # 选中任务后中间区域展示
│
├── 📝 笔记生成            /notes             # V2.0，笔记列表+编辑
│   └── 笔记预览           /notes/<rid>       # 单篇笔记详情（已部分实现）
│
├── 📚 知识库              /knowledge         # V2.1，子库总览
│   ├── 开篇套路            /knowledge/openings
│   ├── 人物设定            /knowledge/characters
│   ├── 冲突设计            /knowledge/conflicts
│   ├── 情绪触发            /knowledge/emotions
│   └── 金句                /knowledge/quotes
│
├── 🎬 视频脚本            /video             # V2.2，脚本文本生成
│
├── 📊 数据中心            /data              # V2.1，统计分析入口
│   ├── 笔记统计            /data/notes        # 笔记效果统计
│   ├── 爆款因子            /data/factors      # 爆款因子分析
│   ├── AI评分             /data/scores       # 评分分布
│   └── 📈 案例分析         /data/cases        # V3+
│       ├── 成长案例         /data/cases/growth
│       ├── 爆文案例         /data/cases/hot
│       └── 失败案例         /data/cases/failed
│
├── 🧪 实验管理            /experiments       # V3+
│
└── ⚙️ 系统设置            /settings          # V3+
    ├── 模型配置
    ├── API 配置
    └── Feature Flag
```

### 导航结构

顶部导航栏（`_nav.html`）显示一级入口，页面内带二级子菜单：

```
┌──────────────────────────────────────────────────────────┐
│ 🔧 超级工具   工作台  拆文中心  笔记生成  知识库  视频  数据  设置 │
└──────────────────────────────────────────────────────────┘

工作台（当前激活时展开左侧子菜单）：
  ├── 📋 任务中心
  └── 📤 发布管理

知识库（当前激活时展开左侧子菜单）：
  ├── 开篇套路
  ├── 人物设定
  ├── 冲突设计
  ├── 情绪触发
  └── 金句

数据中心（当前激活时展开左侧子菜单）：
  ├── 笔记统计
  ├── 爆款因子
  ├── AI评分
  └── 案例分析

其余一级页面无子菜单，直接显示页面内容。
```

### 页面与模板文件映射

| 页面 | URL | 模板文件 | Sprint |
|------|-----|----------|--------|
| 工作台 | `/dashboard` | `dashboard.html` | V2.0 |
| 任务中心 | `/tasks` | `tasks.html` | V2.0 |
| 拆文中心 | `/deconstruct` | `deconstruct_center.html` | V2.0 |
| 笔记生成 | `/notes` | `notes.html` | V2.0 |
| 笔记预览 | `/notes/<rid>` | `notes_detail.html` | V2.0 |
| 知识库 | `/knowledge` | `knowledge.html` | V2.1 |
| 知识库-子库 | `/knowledge/<type>` | `knowledge_detail.html` | V2.1 |
| 视频脚本 | `/video` | `video.html` | V2.2 |
| 数据中心 | `/data` | `data.html` | V2.1 |
| 数据中心-子页 | `/data/<type>` | `data_<type>.html` | V2.1 |
| 发布管理 | `/publish` | `publish.html` | V2.2 |
| 案例分析 | `/data/cases` | `cases.html` | V3+ |
| 实验管理 | `/experiments` | `experiments.html` | V3+ |
| 系统设置 | `/settings` | `settings.html` | V3+ |

### 技术方案

- 复用 Flask + Jinja2 模板，不引入前端框架
- 每个页面独立模板文件（`scripts/web/templates/` 目录）
- 公共组件（导航栏、状态标签、队列卡片）抽取为 `templates/_components/`
- 页面间通过顶部导航 Tab 切换，各页面独立 URL（非 SPA）
- 二级菜单为当前页内的侧边栏，非全局组件

---

## 7. 版本标记

- v2.0：批量拆文 + few-shot + 缓存 | 页面：工作台 + 拆文中心 + 笔记预览
- v2.1：质量评分 + 反馈闭环 | 页面：知识库中心 + 数据中心
- v2.2：视频脚本生成 | 页面：视频脚本 + 发布管理

---

## 8. 任务清单

> 状态标记：☐ 未开始 | ◐ 进行中 | ☑ 已完成

### 8.-1 主线程任务池

> 用途：主线程用于下发给执行线程的任务单。执行线程优先读取对应 `docs/operations/planning/*.md` 文件。

| # | 任务单 | 类型 | 优先级 | 状态 | 说明 |
|---|--------|------|--------|------|------|
| A | `docs/operations/planning/task-v2-stability-baseline.md` | hotfix | P0 | ☑ | 修复 Web/Gunicorn 启动、增加状态归一化、建立稳定基线 |
| B | `docs/operations/planning/task-v2-production-loop.md` | feature | P0 | ☑ | 打通 worker 评分、任务详情保存、重新评分、修改日志闭环 |
| C | `docs/operations/planning/task-v2-legacy-migration.md` | refactor | P1 | ☐ | 逐步迁移 `web_app_legacy.py`，控制文件长度和维护成本 |
| D | `docs/guides/SCREENSHOT_HANDOFF_TEMPLATE.md` | workflow | P0 | ☑ | 固化截图/设计图交付模板，供后续页面开发使用 |
| E | 任务详情页工作台优化 | UI | P0 | ☑ | 重排顶部概览、进度轴、笔记三栏和 5 秒自动刷新，不改后端 API |

### 8.0 前端架构优化

> 目标：不动旧版代码，建立新页面架构标准。后续所有 V2 页面走新架构（Jinja2 模板 + 独立 CSS/JS + 可复用组件）

| # | 任务 | 优先级 | 状态 | 描述 | 产出物 | 预估 |
|---|------|--------|------|------|--------|------|
| 0.1 | 创建 `static/` 目录结构 | P0 | ☑ | `static/css/` `static/js/` `static/img/`，加 `.gitkeep` | 目录就位 | 10min |
| 0.2 | 确保 `templates/` 模板目录 | P0 | ☑ | 确保 `templates/` 存在，建 `_components/` 子目录 | 目录就位 | 5min |
| 0.3 | 创建 `static/css/base.css` | P0 | ☑ | 公共样式：reset、字体、颜色变量、布局工具类、导航栏样式、状态标签颜色 | 基础 CSS | 30min |
| 0.4 | 创建 `templates/base.html` | P0 | ☑ | 页面骨架：`<head>` 含 charset/viewport/title block、`<link>` 引用 base.css；`<body>` 含 `{% include "_nav.html" %}` + `{% block content %}` + `{% block scripts %}` | 基础模板 | 20min |
| 0.5 | 创建 `templates/_nav.html` | P0 | ☑ | 导航栏组件：左侧 logo + 右侧 tab 链接列表（工作台/拆文中心/知识库/数据中心），当前页高亮 | 导航组件 | 15min |
| 0.6 | 创建 `templates/landing.html` | P0 | ☑ | 占位首页：`{% extends "base.html" %}`，中间显示 V2 功能模块引导卡片 | 首页 | 15min |
| 0.7 | 创建 `templates/_components/status_badge.html` | P1 | ☑ | 状态标签宏：传入 status，返回带颜色和图标标签（排队灰/处理中蓝脉冲/完成绿/失败红/重试橙） | 状态组件 | 15min |
| 0.8 | 创建 `templates/_components/score_bar.html` | P1 | ☑ | 评分进度条宏：传入 label/score/max，返回带颜色判断进度条（绿≥85/黄≥75/红<75） | 评分组件 | 15min |
| 0.9 | 创建 `templates/_components/queue_card.html` | P1 | ☑ | 队列任务卡片宏：传入 task，渲染一行卡片（作品名/作者/平台/状态/评分/操作按钮） | 队列组件 | 15min |
| 0.10 | 创建 `templates/_components/empty_state.html` | P1 | ☑ | 空状态占位：传入 icon/title/description，渲染居中引导提示 | 空状态组件 | 10min |
| 0.11 | 创建 `templates/_components/toast.html` | P1 | ☑ | Toast 通知宏：传入 message/type(success/error/warning)，渲染右上角浮动提示 | Toast 组件 | 10min |
| 0.12 | 新页面路由规范约定 | P0 | ☑ | 文档约定：每个新页面一个 Blueprint，放在 `web/routes/<name>_page.py`，模板放 `templates/<name>.html`，API 放 `web/routes/<name>_api.py` | 规范文档 | 10min |
| 0.13 | 创建示例页面路由 `landing_page.py` | P0 | ☑ | `Blueprint("web_landing", __name__)` + `@bp.get("/")` 返回 `render_template("landing.html")`，注册到 `__init__.py` | 示例路由 | 10min |
| 0.14 | 旧版导航栏加"新版入口"链接 | P0 | ☑ | `web_app_legacy.py` 侧边栏 ul 中追加 `<li>`，链接文字"新版工具"，href 指向新版首页，最小侵入 | 入口链接 | 5min |
| 0.15 | 启动验证新旧页面共存 | P0 | ☑ | 启动 Flask → 新版首页正常 → 旧版 URL 不受影响 → 导航链接正确 → 组件渲染正常 | 验收通过 | 15min |

**执行顺序**：
```
第一批（并行，10min）：  0.1 + 0.2 + 0.12
第二批（25min）：        0.3 + 0.4 + 0.5 + 0.6
第三批（30min）：        0.7 + 0.8 + 0.9 + 0.10 + 0.11
第四批（15min）：        0.13 + 0.14
第五批（10min）：        0.15
```

---

### 8.1 队列系统

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 1.1 | 创建 `data/queue/` 目录 | P0 | ☑ | 新增目录，加入 `.gitkeep` | 5min |
| 1.2 | `config.py` 新增 queue 路径 | P0 | ☑ | PATHS 字典加 `"queue"` 键 | 5min |
| 1.3 | `deconstruct_queue.jsonl` 读写封装 | P0 | ☑ | `scripts/queue_manager.py`：入队/出队/更新状态/查询，5 状态机 | 1h |
| 1.4 | `deconstruct_worker.py` 队列消费脚本 | P0 | ☑ | 循环消费队列 → 调 `model_adapter.analyze_work()` → 调 `related_sync` 写知识库 → 调 `image_generator` 入队 → 更新队列状态。文件锁防并发。可 cron 或常驻模式 | 3h |
| 1.5 | 选题批量入队 | P0 | ☑ | 飞书选题库多选 → 批量写入队列。修改 `select_work_from_topic_library` 支持 `select_works(limit=N)` | 1h |
| 1.6 | 队列状态轮询 API | P0 | ☑ | `GET /api/deconstruct/queue` 返回列表，支持筛选/分页 + 5 个操作端点 | 30min |

### 8.2 API 层 — 队列管理

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 2.1 | `POST /api/deconstruct/batch-start` | P0 | ☑ | 接收 `record_ids` 列表，更新队列状态为 processing | 30min |
| 2.2 | `POST /api/deconstruct/batch-complete` | P0 | ☑ | 批量标记完成，状态 → done | 20min |
| 2.3 | `POST /api/deconstruct/{rid}/retry` | P0 | ☑ | 重试失败任务，重置状态 + retry_count++ | 20min |
| 2.4 | `GET /api/deconstruct/{rid}/result` | P0 | ☑ | 返回单个拆文结果 JSON | 30min |
| 2.5 | `GET /api/deconstruct/{rid}/stats` | P0 | ☑ | 统计条数据：今日产出/完成率/均分/均耗时 | 30min |

### 8.3 API 层 — 笔记操作

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 3.1 | `GET /api/note/{rid}` | P0 | ☑ | 获取笔记内容 + AI 评分 | 20min |
| 3.2 | `POST /api/note/{rid}/regenerate` | P1 | ☑ | 重新生成笔记，body 含 `fields` 和 `reference_ids`，注入 few-shot | 1h |
| 3.3 | `POST /api/note/{rid}/save` | P1 | ☑ | 保存人工修改，记录 diff 到飞书修改日志 | 1h |
| 3.4 | `POST /api/note/batch-generate` | P0 | ☑ | 批量生成笔记 | 30min |
| 3.5 | `POST /api/note/{rid}/score` | P1 | ☑ | 重新评分 | 20min |

### 8.4 API 层 — 资产状态 + 参考

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 4.1 | `GET /api/deconstruct/{rid}/assets` | P1 | ☑ | 封面图 + 视频脚本生成状态（复用 `local_runs.load_image_queue_status` 逻辑） | 30min |
| 4.2 | `POST /api/image/batch-generate` | P1 | ☑ | 批量生成图片 | 30min |
| 4.3 | `GET /api/image/{rid}/preview` | P1 | ☑ | 预览封面图 | 20min |
| 4.4 | `GET /api/reference/top-notes` | P0 | ☑ | 历史爆款 top 3，按点赞+收藏排序，同账号 | 30min |

### 8.5 模型层

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 5.1 | `analyze_work()` 增加 `reference_notes` 参数 | P0 | ☐ | prompt 末尾追加 few-shot 样本，降级处理空参考 | 1h |
| 5.2 | `analyze_work()` 增加 `recent_feedback` 参数 | P1 | ☐ | prompt 追加历史修改偏好 | 30min |
| 5.3 | `quality_scorer.py` 评分模块 | P1 | ☑ | 独立 LLM 调用，六维评分（标题/情绪/收藏/互动/风格/AI痕迹），输出 0-100 | 2h |
| 5.4 | `generate_video_script()` 视频脚本生成 | P2 | ☐ | 输入拆文结果 + 笔记，输出口播稿 + 分镜脚本 | 2h |
| 5.5 | 拆文结果缓存 | P1 | ☑ | `deconstruct_worker.py` 调 LLM 前查飞书主表，作品+作者已存在则复用 | 30min |

### 8.6 飞书层

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 6.1 | 笔记库新增字段 schema | P1 | ☑ | 发布状态/发布时间/发布链接/修改日志/修改后评分/笔记正文全文 | 30min |
| 6.2 | `feishu_client.get_top_notes(limit=3)` | P0 | ☑ | 读笔记结果库，按点赞+收藏排序取 top，返回标题+正文 | 30min |
| 6.3 | `feishu_client.get_recent_modifications(n=5)` | P1 | ☑ | 读笔记库修改日志字段，取最近 N 条 | 20min |
| 6.4 | `feishu_client.save_modification_log(rid, diff)` | P1 | ☑ | 追加写入修改日志字段 | 20min |

### 8.7 前端 — 拆文中心页面

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 7.1 | 页面骨架 + CSS | P0 | ☐ | `templates/deconstruct_center.html`，三栏 Grid 布局，导航栏入口 | 2h |
| 7.2 | `queue.js` — 左侧任务队列 | P0 | ☑ | 列表渲染/状态颜色/筛选器/分页/多选/拖拽排序 | 3h |
| 7.3 | `batch.js` — 批量操作栏 | P0 | ☑ | 全选/反选/计数/开始拆文/生成笔记/生成图片/标记完成 | 2h |
| 7.4 | `deconstruct.js` — 中间拆文结果面板 | P0 | ☑ | 五维可折叠面板，展开/折叠/复制本条/复制全部 | 2h |
| 7.5 | `note.js` — 笔记编辑区 | P0 | ☑ | 标题+正文+标签+话术四个编辑区/采纳/重生成/复制全文/导出MD | 3h |
| 7.6 | `score.js` — AI 评分面板 | P1 | ☐ | 六维进度条/颜色规则/重新评分/一键重生成 | 2h |
| 7.7 | `reference.js` — 参考笔记选择 | P1 | ☐ | 爆款列表/多选/注入生成 | 1h |
| 7.8 | `modlog.js` — 修改日志 | P1 | ☐ | 日志时间线渲染/查看 | 30min |
| 7.9 | `stats.js` — 统计条 | P1 | ☐ | 今日产出/完成率/均分/均耗时，30s 轮询 | 1h |
| 7.10 | `assets.js` — 生成状态卡片 | P1 | ☐ | 封面图缩略图+状态/视频脚本状态，5s 轮询 | 1h |

### 8.8 路由 + 入口

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 8.1 | 注册新路由模块 `web/routes/deconstruct_api.py` | P0 | ☑ | 将 8.2/8.3/8.4 的所有 API 挂载到 Blueprint | 1h |
| 8.2 | 注册页面路由 `/deconstruct` | P0 | ☐ | 返回 `deconstruct_center.html` 渲染 | 15min |
| 8.3 | 旧版 tab 栏新增入口 | P1 | ☑ | `web_app_legacy.py` 侧边栏加"拆文中心"链接 | 15min |

### 8.9 联调 + 验收

| # | 任务 | 优先级 | 状态 | 描述 | 预估 |
|---|------|--------|------|------|------|
| 9.1 | 端到端流程验证 | P0 | ☑ | 选题入队 → worker 消费 → 拆文 → 笔记 → 评分 → 前端展示 | 2h |
| 9.2 | 边界情况处理 | P1 | ☐ | 队列为空/全部失败/网络超时/飞书 API 限流/LLM 超时重试 | 1h |
| 9.3 | Docker 适配 | P2 | ☐ | `deconstruct-runner` 容器改为常驻队列消费模式 | 1h |

---

### 进度总览

```
前端架构:     15/15 ████████████ 100%
队列系统:     6/6  ████████████ 100%
API 层:       14/14 ████████████ 100%
模型层:       4/5  █████████░░░  80%
飞书层:       4/4  ████████████ 100%
前端页面:     5/10 ██████░░░░░░  50%
路由+入口:    3/3  ████████████ 100%
联调+验收:    1/3  ████░░░░░░░░  33%
─────────────────────────────────
总计:         52/60 ██████████░░  87%
```
