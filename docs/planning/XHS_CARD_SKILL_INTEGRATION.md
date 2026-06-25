# 小红书内容研究与卡片生成能力集成方案

> 2026-06-25 | 吸收 `content-research-writer` 与 `guizang-social-card-skill` 的项目内集成设计；`canvas-design` 降为低优先级审美补充

## 1. 背景

本项目当前已经具备从网文选题到小红书笔记、配图提示词、HTML 卡片和飞书回填的端到端流程。现有链路能跑通批量生产，但仍有两个明显短板：

- 内容生成层偏依赖硬编码标题公式和单次模型拆解，缺少可复盘的选题、受众、钩子和图文页结构。
- 卡片生成层已有 `html_card_generator.py`，但当前主要依赖正文拆段和关键词匹配模板，缺少视觉简报、设计哲学和成品质检。

本方案优先吸收两个外部 skill 的方法论：

- `content-research-writer`：吸收其选题研究、hook 强化、内容结构化和反馈闭环思想。
- `guizang-social-card-skill`：吸收其社交卡片工作流、Editorial/Swiss 双视觉系统、版式 recipes、平台尺寸、HTML 渲染和 DOM 级质量校验思想。

`canvas-design` 不进入主线工程任务，仅作为低优先级审美补充：保留“先写视觉哲学”“少字高视觉表达”“二次精修”“边界与留白检查”等原则，用于增强 `视觉简报.visual_philosophy` 和 QA 文案。

目标不是把两个 skill 原样安装成手动工具，而是把它们拆成项目生产管线里的两个稳定能力层。

## 2. 集成原则

### 2.1 不另起一条平行流程

现有主流程保持不变：

```text
选题库/初筛
  -> analyze_work()
  -> build_xhs_note()
  -> sync_xhs_note_table()
  -> image_strategy: ai/html_card
  -> 飞书与 Web 预览
```

新增能力必须嵌入现有链路，避免出现一套 Codex 手工流程和一套 Python 自动化流程互相分裂。

### 2.2 用结构化 brief 替代散落 prompt

当前项目里已经有 `小红书包装`、`卖点分析`、`配图提示词` 等结构。后续不继续无限扩写 prompt 文本，而是新增两个稳定结构：

- `内容简报`：负责选题、受众、痛点、标题、封面钩子和图文页结构。
- `视觉简报`：负责视觉哲学、风格、卡片规划、布局约束和质检规则。

### 2.3 保留现有生成策略

`ai` 生图和 `html_card` 程序化卡片都保留：

- `ai`：继续走即梦生图，适合人物/场景插画。
- `html_card`：吸收 `guizang-social-card-skill` 的 recipe/validator 思路，升级为封面和图文卡片主产线。
- `auto`：后续可根据作品类型或运营配置自动选择。

## 3. 当前可承接位置

| 能力 | 当前文件 | 当前职责 | 吸收方向 |
|------|----------|----------|----------|
| 模型拆解 | `scripts/model_adapter.py` | `analyze_work()` 输出作品拆解、小红书包装和提示词 | 新增 `内容简报`、后续新增 `视觉简报` |
| 笔记正文 | `scripts/deconstruct_daily.py` | `build_xhs_note()` 生成小红书 Markdown 初稿 | 优先读取 `内容简报` 中的标题、钩子和结构 |
| 参考与反馈 | `scripts/generation_context.py` | 注入爆款参考笔记和运营修改偏好 | 扩展为内容研究上下文 |
| 卡片生成 | `scripts/html_card_generator.py` | 笔记正文拆页，渲染 HTML 并截图 PNG | 接入 `视觉简报`、`内容简报.图文页结构` 和 recipe-based planner |
| 图片策略 | `data/config/image_strategy.json` | 控制 `ai/html_card/auto`、style、count | 新增 brief 模式和质检开关 |
| Web 配置 | `scripts/web/routes/task_detail_page.py` | 图片策略 API 与任务详情交互 | 后续增加重生 brief/卡片能力 |

## 4. 目标架构

```text
作品信息 + 历史参考 + 运营反馈
        |
        v
analyze_work()
        |
        +-- 开篇套路 / 人物设定 / 冲突设计 / 情绪触发 / 金句
        +-- 卖点分析
        +-- 小红书包装
        +-- 内容简报
        +-- 视觉简报
        +-- 配图提示词
        |
        v
build_xhs_note()
        |
        +-- Markdown 初稿
        +-- 标题候选
        +-- 封面钩子
        |
        v
html_card_generator.generate_cards_from_note()
        |
        +-- 读取 内容简报.图文页结构
        +-- 读取 视觉简报.card_plan/layout_rules
        +-- 渲染 HTML
        +-- Playwright 截图 PNG
        +-- 质量检查
```

## 5. 数据结构设计

### 5.1 `内容简报`

建议加入 `analyze_work()` 的 JSON schema，并在 `_ensure_analysis_shape()` 中做默认补齐。

```json
{
  "内容简报": {
    "目标人群": ["书荒读者", "网文爱好者", "写作者"],
    "核心痛点": "最近想找一本有强钩子、人物不扁平、情绪反馈稳定的文",
    "读者收益": "快速判断这本书是否值得加入书单",
    "标题候选": [
      "这本真的不是普通爽文，开篇就把人拽住了",
      "书荒可以冲：这本的情绪反馈太稳了",
      "喜欢强冲突开篇的姐妹别错过"
    ],
    "封面钩子": {
      "主标题": "书荒可以冲",
      "副标题": "开篇强钩子 + 情绪反馈稳定",
      "情绪": "惊喜、上头、收藏",
      "点击理由": "一句话告诉用户为什么值得点开"
    },
    "图文页结构": [
      {
        "page": 1,
        "role": "cover",
        "message": "用最短标题表达推荐理由"
      },
      {
        "page": 2,
        "role": "problem",
        "message": "指出读者书荒或踩雷痛点"
      },
      {
        "page": 3,
        "role": "insight",
        "message": "解释这本书的稀缺卖点"
      },
      {
        "page": 4,
        "role": "proof",
        "message": "用人物、冲突或节奏证明推荐理由"
      },
      {
        "page": 5,
        "role": "summary",
        "message": "给收藏理由和互动问题"
      }
    ],
    "证据素材": ["简介线索", "分类题材", "历史爆款参考"],
    "禁用表达": ["私信", "加我", "站外平台名", "夸张承诺"]
  }
}
```

### 5.2 `视觉简报`

`视觉简报` 可以第一阶段由规则生成，第二阶段再由模型生成。它服务于 `html_card_generator.py`，主参考来自 `guizang-social-card-skill` 的社交卡片系统。

```json
{
  "视觉简报": {
    "visual_philosophy": "用清晰的知识卡片结构承载强情绪推荐，视觉上像一张可收藏的编辑部书单。",
    "style_mode": "editorial",
    "style": "warm",
    "layout_recipe": "cover-ledger-closing",
    "palette": ["#F8E8D8", "#2F2621", "#D85C4A", "#FFFFFF"],
    "typography": {
      "title": "serif-heavy",
      "body": "sans-readable",
      "accent": "handwritten-or-display"
    },
    "layout_rules": {
      "canvas_width": 1080,
      "canvas_height": 1440,
      "safe_margin": 72,
      "cover_title_max_chars": 18,
      "subtitle_max_chars": 32,
      "body_line_max_chars": 18,
      "density": "medium"
    },
    "card_plan": [
      {
        "type": "cover",
        "recipe": "cover",
        "title": "书荒可以冲",
        "subtitle": "开篇强钩子 + 情绪反馈稳定",
        "visual_metaphor": "书单便签、重点划线、柔和高亮",
        "priority": "click"
      },
      {
        "type": "content",
        "recipe": "tall-ledger",
        "section_tag": "亮点 01",
        "section_title": "开篇就有抓力",
        "points": ["先抛冲突", "再给反转", "读者马上知道看点"]
      }
    ],
    "quality_rules": [
      "封面主标题手机缩略图可读",
      "每页只表达一个核心意思",
      "正文不超过 3 个要点",
      "文字和图形不得越界或重叠",
      "同一组卡片风格、字体和页码一致"
    ]
  }
}
```

字段说明：

- `style_mode`：优先使用 `editorial` 或 `swiss` 两类视觉姿态。`editorial` 偏叙事、阅读、生活方式；`swiss` 偏结构、方法论、数据和产品说明。
- `layout_recipe`：当前卡片组的整体版式策略，可从 cover、checklist、evidence-wall、tall-ledger、before-after、closing-note 等自研 recipes 中选择。
- `recipe`：单页版式角色。后续由 `html_card_generator.py` 映射到项目自己的 Jinja 模板或局部 HTML skeleton。

注意：`guizang-social-card-skill` 仓库许可证为 AGPL-3.0。项目吸收其方法论、结构和校验思路，但不直接复制模板、脚本、assets 或 CSS/HTML 实现，避免引入许可证传染风险。

### 5.3 图片策略配置

现有配置：

```json
{
  "strategy": "html_card",
  "style": "warm",
  "count": 3
}
```

建议升级为：

```json
{
  "strategy": "html_card",
  "style": "auto",
  "count": 3,
  "brief_mode": "content_plus_visual",
  "canvas_quality_check": true
}
```

兼容规则：

- 缺少新字段时按旧逻辑运行。
- `brief_mode=off` 时完全使用当前行为。
- `brief_mode=content_only` 时只使用 `内容简报` 拆页，不启用视觉简报。
- `brief_mode=content_plus_visual` 时启用完整新链路。

## 6. 模块改造方案

### 6.1 `scripts/model_adapter.py`

改造点：

- 在 system prompt 的输出字段中新增 `内容简报`。
- 第二阶段新增 `视觉简报`，或先由规则模块从 `内容简报` 派生。
- `_ensure_analysis_shape()` 补齐两个新结构，保证旧数据和 local fallback 不崩。
- `_local_analyze()` 增加最小可用默认值，方便无模型环境测试。

注意事项：

- `max_tokens` 需要评估是否从 2000 提高到 2600-3200。
- JSON 输出字段变多后，必须保留解析失败 fallback。
- 新字段不应影响主表和小红书笔记库已有字段写入。

### 6.2 `scripts/deconstruct_daily.py`

改造点：

- `generate_title_options()` 优先读取 `analysis["内容简报"]["标题候选"]`，不足时再用现有标题公式兜底。
- `build_xhs_note()` 开头和结构优先读取 `内容简报.封面钩子`、`核心痛点`、`读者收益`。
- `build_report()` 增加 `内容简报` 和 `视觉简报` 摘要，便于复盘。
- `sync_xhs_note_table()` 暂不强制写入飞书新字段，避免 schema 改动过大。后续可按需要加字段。

### 6.3 `scripts/html_card_generator.py`

改造点：

- `generate_cards_from_note()` 增加可选参数：

```python
def generate_cards_from_note(
    note_content: dict,
    style: str = "auto",
    n: int = 3,
    output_dir: str = None,
    visual_brief: dict = None,
    content_brief: dict = None,
) -> list[str]:
```

- `_plan_cards()` 优先使用 `visual_brief.card_plan`。
- 如果没有视觉简报，则使用 `content_brief.图文页结构`。
- 如果两个 brief 都没有，保持当前正文拆段逻辑。
- 新增 `_validate_cards()`，检查标题长度、页数、每页要点数量、空字段。
- 后续可新增 `_quality_check_screenshot()`，用 Playwright 截图后检查 PNG 是否存在、尺寸是否正确。

### 6.4 `scripts/generation_context.py`

改造点：

- 当前已有 `reference_notes` 和 `recent_feedback`，可以继续复用。
- 后续新增 `content_preferences`，从历史修改日志中提取偏好，例如“标题更短”“少用泛泛标签”“正文第一段先给结论”。
- 不让主流程依赖飞书，获取失败仍降级为空上下文。

### 6.5 Web 与配置

第一阶段不改前端，只改后端默认行为。

第二阶段再在任务详情或生产中心增加：

- 重生内容 brief
- 重生视觉 brief
- 重生 HTML 卡片
- 采纳卡片版本
- 查看 brief JSON

## 7. 任务安排

### 阶段 1：内容简报接入（P0，已完成）

目标：把 `content-research-writer` 的核心能力变成项目内 `内容简报`。

任务：

1. 已修改 `scripts/model_adapter.py` 的 JSON schema，新增 `内容简报`。
2. 已修改 `_ensure_analysis_shape()` 和 `_local_analyze()`，保证默认结构完整。
3. 已修改 `generate_title_options()`，优先使用 `内容简报.标题候选`。
4. 已修改 `build_xhs_note()`，使用 `核心痛点`、`读者收益`、`封面钩子` 强化开头。
5. 已增加测试，覆盖旧 analysis 缺少 `内容简报` 时不报错、标题优先级、默认补齐和本地 fallback。

验收：

- 旧记录重生笔记不报错。
- 新生成结果包含 `内容简报`。
- 标题候选可被优先使用。
- 本地 fallback 模式仍能跑通。

### 阶段 2：HTML 卡片接入内容简报（P0）

目标：让卡片拆页从正文拆段升级为按图文页结构生成。

任务：

1. 修改 `generate_cards_from_note()`，支持 `content_brief` 参数。
2. 修改 `_plan_cards()`，优先读取 `内容简报.图文页结构`。
3. 保留现有拆段逻辑作为 fallback。
4. 生成卡片时写出 `brief.md` 或 `card_plan.json` 到输出目录，便于复盘。
5. 增加测试，覆盖有 brief 和无 brief 两种路径。

验收：

- `html_card` 策略能生成封面、内容页和总结页。
- 没有 `内容简报` 的旧数据仍按原逻辑生成。
- 输出 PNG 尺寸为 1080x1440。

### 阶段 3：视觉简报与 guizang 社交卡片系统吸收（P1）

目标：把 `guizang-social-card-skill` 的社交卡片方法论落到卡片生成链路，形成项目自有的 recipe planner、主题系统和质量检查。

任务：

1. 新增 `scripts/xhs_visual_brief.py`，从 `内容简报`、`小红书包装`、`卖点分析` 派生 `视觉简报`。
2. 设计项目自有 recipe 集合，先实现 cover、checklist、tall-ledger、before-after、closing-note 五类。
3. `html_card_generator.py` 支持 `visual_brief.card_plan` 和 `recipe` 映射。
4. 扩展模板变量，允许传入 palette、typography、layout_rules、style_mode。
5. 新增质量检查：标题长度、要点数量、边距、空字段、PNG 是否生成、3:4 画布密度、footer 碰撞。
6. 在 `build_report()` 或输出目录记录 `visual-philosophy.md` 与 `card_plan.json`。
7. 评估公众号封面对模式：`21:9` 主封面 + `1:1` 分享卡，分别构图，不做简单裁切。

验收：

- 同一选题能稳定生成风格一致的一组卡片。
- 卡片主标题不超长，手机缩略图可读。
- 每页只表达一个核心点。
- 卡片输出目录包含视觉简报、视觉哲学记录和卡片计划。
- QA 能发现明显溢出、空白过多和 footer 碰撞问题。

### 阶段 3.5：canvas-design 审美原则补充（P3）

目标：低成本吸收 `canvas-design` 的审美原则，不把它作为工程主线。

任务：

1. 在 `视觉简报.visual_philosophy` 生成逻辑中加入“视觉哲学”一句话描述。
2. 在 QA checklist 中加入二次精修原则：优先让已有构图更完整，不靠继续堆元素解决问题。
3. 在卡片复盘记录中保留“少文字、高视觉表达、边界、留白、字体完成度”等检查项。

验收：

- 不新增生产依赖。
- 不直接引入 `canvas-design` 模板或资产。
- 只作为视觉简报和质量检查的文本原则存在。

### 阶段 4：配置与 Web 操作（P2）

目标：让运营可以在 Web 内选择和调试新能力。

任务：

1. 升级 `data/config/image_strategy.json`，增加 `brief_mode` 和 `canvas_quality_check`。
2. 更新图片策略 API，兼容新字段。
3. 在任务详情页展示 brief 摘要。
4. 增加“重生卡片”“重生视觉 brief”按钮。
5. 失败时展示可读错误，不影响笔记正文保存。

验收：

- Web 可以查看当前策略配置。
- 修改策略后后端能读取新字段。
- brief 生成失败时可降级到旧卡片逻辑。

### 阶段 5：沉淀 Codex skill（P2）

目标：把这套方法论沉淀为维护项目时可触发的 Codex 开发 skill，而不是生产依赖。

建议位置：

```text
~/.codex/skills/xiaohongshu-card-studio/
```

内容：

- `SKILL.md`：说明何时使用，以及如何维护项目内内容 brief/视觉 brief/card generator。
- `references/content-research.md`：吸收 `content-research-writer` 的内容策划规则。
- `references/social-card-system.md`：吸收 `guizang-social-card-skill` 的平台尺寸、视觉模式、recipe planner 和 QA 思路。
- `references/canvas-design-lite.md`：低优先级记录 `canvas-design` 的审美原则，只用于视觉哲学和二次精修。

验收：

- 当用户提出“小红书封面/图文卡片/笔记选题/卡片工作流”时能触发。
- skill 指向项目内真实模块，而不是要求手工复制外部流程。

## 8. 风险与回滚

| 风险 | 表现 | 应对 |
|------|------|------|
| JSON 字段变多导致模型输出解析失败 | `openai_parse_fallback` 增多 | 分阶段加入字段，保留 fallback，提高 token 上限 |
| 笔记变得过度模板化 | 标题和卡片像固定格式 | 内容简报只提供结构，不强制所有句式 |
| 卡片文字溢出 | PNG中文字被裁切或重叠 | `_validate_cards()` + 模板 CSS 固定字号和安全边距 |
| 飞书 schema 改动影响线上 | 字段缺失或类型不匹配 | 第一阶段不新增飞书字段，仅本地 analysis JSON 使用 |
| brief 失败影响主流程 | 生成中断 | 所有 brief 读取都必须有 fallback |
| 外部 skill 许可证风险 | 直接复制 AGPL 模板或脚本 | 只吸收方法论，自研 recipes、模板和 validator |

回滚方式：

- 将 `brief_mode` 设置为 `off`。
- 保留旧 `_plan_cards()` 逻辑。
- `build_xhs_note()` 中 brief 读取失败时使用现有标题公式和正文生成逻辑。

## 9. 验收样例

给定一个旧作品记录，执行重生笔记和 HTML 卡片：

预期结果：

- `analysis` 中存在 `内容简报`。
- `build_xhs_note()` 生成的标题优先来自 `标题候选`。
- `html_card_generator.py` 生成 3-5 张 PNG。
- 无 `内容简报` 的旧数据仍可生成 PNG。
- 输出目录包含用于复盘的 brief 文件。

## 10. 推荐实施顺序

优先做阶段 1 和阶段 2。它们直接改善内容与卡片结构，且风险低。

阶段 3 再引入视觉简报和 recipe-based planner，避免一开始同时修改模型 schema、正文生成、卡片生成和样式系统，导致问题难以定位。

`canvas-design` 对应阶段 3.5，保持 P3 低优先级。阶段 4 和阶段 5 属于产品化和长期维护，不阻塞前两阶段上线。
