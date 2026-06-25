# 变更记录（每日更新）

规则：
- 每次“优化/修复/字段变更/飞书表结构变更/模型切换/提示词策略变更”都要记录
- 记录必须包含：日期、影响范围、行为变化、回滚方式
- 不要写入密钥、token、用户隐私信息

模板（复制一段填写）：

## YYYY-MM-DD
- 变更摘要：
- 影响范围：主流程 / 生图 / Web / 飞书表结构 / 模型
- 行为变化：
- 配置变更（.env）：
- 数据迁移/回填动作：
- 回滚方式：
- 风险与注意事项：

## 2026-06-25（生产链路与卡片策略收口）
- 变更摘要：收口选题池生图策略、HTML 卡片路径、worker 缓存补图和小红书卡片能力规划文档。
- 影响范围：主流程 / 生图 / Web / Worker / 文档
- 行为变化：
  - 选题池提交生产时可携带 `image_strategy`，队列任务记录策略，worker 按任务策略选择 `ai`、`html_card` 或 `auto`
  - 缓存命中任务补图时会过滤疑似飞书 record id 的标签，并构造结构化笔记供 HTML 卡片使用
  - HTML 卡片截图使用 `Path.as_uri()` 生成 file URL，兼容含空格或特殊字符的本地路径
  - 任务详情图片预览和 `/_health/images/<path>` 支持完整相对路径，兼容 HTML 卡片子目录输出
  - 选题池 owner 模式按本地结果和队列完成状态过滤已拆解作品
  - 新增 `docs/planning/XHS_CARD_SKILL_INTEGRATION.md`，规划内容简报、视觉简报与卡片生成能力集成
  - `.gitignore` 补充本地日志、锁文件、worker 心跳、本地配置和临时启动脚本
- 配置变更（.env）：无新增必填项；本地 `data/config/image_strategy.json` 继续作为运行态配置，不纳入提交
- 数据迁移/回填动作：无；运行态 `data/*.jsonl` 不纳入本次代码提交
- 回滚方式：回退本次涉及的 worker、队列、选题池、图片服务、HTML 卡片生成器、文档和 `.gitignore` 改动
- 风险与注意事项：
  - HTML 卡片实际截图仍依赖 Playwright/Chromium 环境，缺失时会降级为生成失败日志，不应阻断笔记正文
  - `内容简报` 与 `视觉简报` 仍是规划，尚未接入模型 schema 和卡片 planner

## 2026-06-20（Dashboard 与选题池布局精简）
- 变更摘要：统一顶部页面标题靠左，精简 Dashboard 与选题池重复/冗余区域。
- 影响范围：Web / 公共 Header / Dashboard / 选题池
- 行为变化：
  - 公共顶部菜单栏页面标题改为靠左展示，普通页面统一生效
  - Dashboard 主内容区删除重复的“运营工作台 / 数据总览”标题
  - Dashboard 数据趋势图按卡片容器宽度绘制，减少居中留白
  - 选题池搜索、筛选、快捷筛选、批量选择与同步入口合并为一块紧凑工具栏
  - 选题池 KPI 数字字号调整为 24px，与生产中心 KPI 规格保持一致
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/_header.html`、`scripts/static/css/base.css`、`scripts/web/templates/dashboard.html`、`scripts/static/css/dashboard.css`、`scripts/static/js/dashboard.js`、`scripts/web/templates/topic_pool.html`、`scripts/static/css/topic_pool.css` 和本条记录
- 风险与注意事项：
  - 本次只调整布局与样式，不改选题池筛选/批量选择业务逻辑

## 2026-06-20（Dashboard Banner 与环形图二次修正）
- 变更摘要：继续按反馈优化 Dashboard banner 背景铺色和账号表现环形图实现。
- 影响范围：Web / Dashboard
- 行为变化：
  - Banner 取消外边框，浅紫背景铺满到右侧插画区域
  - 账号表现从 CSS conic-gradient 改为自定义 SVG 分段圆环，模拟 Pie 的内外半径、分段间距、圆角断点和白色描边
  - 中心文字和图例继续使用自定义 DOM，便于后续接入真实账号指标
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/static/css/dashboard.css`、`scripts/static/js/dashboard.js` 和本条记录
- 风险与注意事项：
  - 本次不新增 Recharts 依赖，仍保持 Vanilla JS 实现

## 2026-06-20（Dashboard 视觉反馈修正）
- 变更摘要：按截图反馈修正 Dashboard Hero 插画、快捷操作卡片和账号表现环形图。
- 影响范围：Web / Dashboard
- 行为变化：
  - Hero 插画改为透明背景 PNG，并允许在 banner 右侧和底部轻微外溢
  - 移除 Dashboard 内容标题区右侧通知按钮和日期范围
  - 修复快捷操作入口内部文字被误当卡片导致的溢出问题，入口图标继续使用 lucide
  - 账号表现环形图改为分段环与右侧指标列表样式
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/dashboard.html`、`scripts/static/css/dashboard.css`、`scripts/static/js/dashboard.js`、`scripts/static/img/dashboard-hero.png` 和本条记录
- 风险与注意事项：
  - 账号表现仍只展示任务侧真实指标，粉丝、阅读增长继续保持未接入空态

## 2026-06-20（Dashboard 首页数据总览）
- 变更摘要：新增真正可用的 `/dashboard` 运营工作台首页和 `/api/dashboard/overview` 聚合接口。
- 影响范围：Web / Dashboard / 公共侧栏 / 文档
- 行为变化：
  - `/dashboard` 不再返回 `landing.html`，改为渲染 `dashboard.html`
  - 新增首页 KPI、近 7 日趋势、热门选题 TOP5、账号任务指标、内容状态和快捷操作区
  - 聚合接口复用现有队列、本地选题和统计能力，不改现有 API、不改队列结构、不新增数据库
  - 阅读量、粉丝增长等尚未接入真实来源的指标返回空状态，不展示伪造数据
  - 左侧侧栏新增可用的“工作台”入口并支持 dashboard 高亮
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/routes/dashboard_page.py`、`scripts/web/routes/__init__.py`、`scripts/web/routes/landing_page.py`、`scripts/web/templates/dashboard.html`、`scripts/web/templates/_sidebar.html`、`scripts/static/css/dashboard.css`、`scripts/static/js/dashboard.js`、`scripts/static/img/dashboard-hero.png` 和本条记录
- 风险与注意事项：
  - 热门选题排序依赖当前已有的评分、收藏、点赞、评论与创建时间字段；字段缺失时只按已有真实信息展示
  - 发布状态字段尚未统一接入，待发布笔记当前按“已完成且有笔记内容但未标记发布”的待处理口径估算

## 2026-06-20（选题池列表与侧栏按钮对齐）
- 变更摘要：将侧栏收起按钮移回左侧菜单栏，并按生产中心任务列表风格优化选题池主列表。
- 影响范围：Web / 公共 AppShell / 选题池
- 行为变化：
  - 侧栏收起按钮从顶部 Header 移入侧栏品牌区，折叠后仍保留展开入口
  - 选题池作品列表从大卡片改为高密度行式表格，信息层级对齐生产中心列表
  - 作品信息、综合评分、数据指标、生产价值和操作入口分列展示，筛选、快捷筛选、批量选择、右侧生产计划和提交生产能力保留
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/_header.html`、`scripts/web/templates/_sidebar.html`、`scripts/web/templates/topic_pool.html`、`scripts/static/css/base.css`、`scripts/static/css/topic_pool.css`、`scripts/static/js/topic_pool.js` 和本条记录
- 风险与注意事项：
  - 选题池仍使用原前端筛选和分页逻辑，本次只调整列表呈现和操作入口布局

## 2026-06-19（任务详情页红框问题修正）
- 变更摘要：按参考图修正任务详情页顶部导航、任务概览信息栏、右侧操作按钮和底部操作栏覆盖范围。
- 影响范围：Web / 任务详情 / 公共 Header 条件态
- 行为变化：
  - 任务详情页顶部 Header 新增“返回生产中心”入口，并将页面标题与任务 ID 胶囊左对齐展示
  - 顶部任务信息栏调整为作品身份、静态任务信息、进度状态、右侧操作按钮四区布局
  - 右侧操作按钮改为纵向动作栈，保留手动刷新、重新生成笔记、重新评分接口绑定
  - 底部保存/审核操作栏限制在右侧内容区，不再横跨左侧菜单栏
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/routes/task_detail_page.py`、`scripts/web/templates/_header.html`、`scripts/web/templates/task_detail.html`、`scripts/static/css/base.css`、`scripts/static/css/task_detail.css`、`scripts/static/js/task_detail.js` 和本条记录
- 风险与注意事项：
  - 公共 Header 仅在传入 `header_back_href` 时启用上下文态；其它页面保持原 Header 结构

## 2026-06-18（生产中心任务列表页优化）
- 变更摘要：按参考设计优化生产中心任务列表页，提升 KPI、筛选区、状态进度、任务信息和操作区的扫读效率。
- 影响范围：Web / 生产中心
- 行为变化：
  - 顶部统计区移除平均处理时长和资源使用率卡片，新增突出显示的“累计完成任务”主 KPI
  - 状态 Tab 增加数量徽标，筛选区补充阶段筛选，搜索、分类和批量操作保留
  - 任务列表压缩行高与封面尺寸，作品标题、作者、平台、分类拆分展示，失败原因单行截断避免撑坏表格
  - 状态 Badge、进度条、模型标签和操作按钮重新分组，查看入口更明确，危险操作保留确认弹窗
  - 5 秒自动刷新继续保留，并在表格内容未变化时避免重复重绘
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/production_center.html`、`scripts/static/css/production_center.css`、`scripts/static/js/production_center.js` 和本条记录
- 风险与注意事项：
  - 本次不改后端数据结构、不删除现有 API、不改 worker / 队列逻辑
  - 分类和阶段筛选基于当前页前端数据过滤，跨页精确筛选后续可单独接入后端查询参数

## 2026-06-18（生产中心侧栏视觉对齐）
- 变更摘要：按参考设计补齐左侧菜单栏的深色工作台视觉。
- 影响范围：Web / 公共 AppShell 侧栏
- 行为变化：
  - 侧栏增加品牌区、深色导航底色、分组分隔线和更明确的激活态
  - 底部增加资源使用卡片，匹配参考图中的侧栏信息层级
  - 桌面端隐藏顶部 Header 重复品牌 Logo，避免与侧栏品牌重复
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/_sidebar.html`、`scripts/static/css/base.css` 和本条记录
- 风险与注意事项：
  - 本次改动公共侧栏样式，会影响所有使用 AppShell 的页面；未改页面业务逻辑和接口

## 2026-06-19（生产中心红框问题修正）
- 变更摘要：修正生产中心页面顶部/侧栏割裂、操作按钮可读性和列表排序问题。
- 影响范围：Web / 公共 AppShell / 生产中心 / 队列列表读取
- 行为变化：
  - 左侧菜单栏从视口顶部开始，顶部 Header 只占右侧主内容区域，减少上下割裂
  - 任务操作区将暂停/重试/终止等状态操作前移，查看详情放在末尾
  - 终止任务图标改为更明确的 `octagon-x`，操作 tooltip 改为快速出现的自定义提示
  - 查看按钮固定宽度，避免“查看”文案溢出按钮
  - 生产队列列表按 `created_at` 倒序后再分页，新提交任务优先显示在前面
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/base.html`、`scripts/static/css/base.css`、`scripts/static/css/production_center.css`、`scripts/static/js/production_center.js`、`scripts/queue_manager.py` 和本条记录
- 风险与注意事项：
  - `get_queue()` 排序改为全局倒序，所有复用该函数的列表类页面/API 都会看到最新任务优先

## 2026-06-17（生产测试问题热修）
- 变更摘要：修复生产测试中发现的队列重复消费、生产中心刷新、提交过渡和任务详情标题清理问题。
- 影响范围：队列 / Docker Worker / 生产中心 / 选题池 / 任务详情 / 笔记生成
- 行为变化：
  - 队列入队跳过重复 `record_id`，状态更新会同步所有同 ID 记录，避免重复 pending 任务被 worker 反复消费
  - Docker Worker 遇到当前 PID 的残留锁会自动清理后重新获取，降低容器重建后的卡锁概率
  - 生产中心列表和统计改为 5 秒轮询刷新
  - 选题池提交生产成功后保留 loading 过渡直到跳转生产中心
  - 任务详情标题输入框不再带 `标题：`、`标题:`、`【标题】` 包装前缀，正文框不再重复标题行
  - 小红书笔记生成去除重复段落，并放宽人设、冲突、情绪字段截断长度
- 配置变更（.env）：无
- 数据迁移/回填动作：清理本地测试队列中重复的 `recvcjDKunVhgv` 运行态记录，保留信息更完整的一条并标记为已完成
- 回滚方式：回退队列幂等、worker 锁、前端刷新/过渡、标题清理、笔记生成长度策略和本条记录
- 风险与注意事项：
  - 当前修复避免后续重复消费；已生成的历史短笔记不会自动重写，需要重新生成才会使用新的正文长度策略

## 2026-06-17（参考笔记与反馈闭环接入）
- 变更摘要：将历史高分参考笔记和近期修改反馈接入后端生成链路。
- 影响范围：Worker / Web API / 飞书读取 / 模型提示词上下文
- 行为变化：
  - 新增 `scripts/generation_context.py`，统一收集可选生成上下文；飞书不可用或无数据时降级为空上下文，不阻断生成
  - `deconstruct_worker.py` 调用 `analyze_work()` 前自动注入参考笔记和近期反馈，并记录上下文条数
  - `POST /api/task/<task_id>/regenerate-note` 和 `POST /api/note/<rid>/regenerate` 重新生成时注入当前任务修改日志、飞书近期修改记录和高分参考笔记
  - `feishu_client.get_top_notes()` 补充读取正文与标签字段，提升 few-shot 样本完整度
  - 重新生成接口返回 `generation_context` 计数，便于验收确认上下文已进入模型层
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/generation_context.py`、worker、任务详情 API、note API、`feishu_client.py`、相关测试和本条记录
- 风险与注意事项：
  - 本次不改页面、不改队列/飞书数据结构、不触发真实模型费用
  - 飞书字段名仍按现有候选字段兼容读取；若线上表字段不同，需要后续补充字段映射

## 2026-06-17（Docker 拆文 worker 常驻化）
- 变更摘要：将 Docker `deconstruct-runner` 从一次性主流程入口改为常驻队列消费入口。
- 影响范围：Docker / Worker / 运维文档
- 行为变化：
  - `deconstruct-runner` 执行 `python scripts/deconstruct_worker.py`，默认随 compose 启动并 `restart: unless-stopped`
  - 空队列下 worker 保持运行，每 60 秒输出一次等待日志；有 pending 任务时进入现有 `process_one()` 消费流程
  - worker 日志补充启动信息、任务 ID、状态变更和异常原因，并继续写入 `logs/deconstruct_worker.log`
  - Docker Web 暴露端口调整为宿主机 `8080` 转发到容器内 `8101`，匹配验收命令
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：将 `docker-compose.yml` 的 `deconstruct-runner` command 改回旧入口，并恢复 `restart: "no"` / run-once profile；回退 worker 日志与锁等待改动
- 风险与注意事项：
  - 本次不引入 Redis/RabbitMQ，不改 JSONL 队列结构，不改 Web 页面和模型 prompt
  - 如已有其他 worker 正在运行，新 runner 会等待队列锁释放

## 2026-06-16（任务详情页密度压实优化）
- 变更摘要：执行任务详情页第二轮视觉压实，提升首屏信息密度并减少无效留白。
- 影响范围：Web / 任务详情页
- 行为变化：
  - 页面容器更充分使用 app shell 内容区宽度，减少居中留白
  - 顶部概览调整为封面身份、文本型任务信息条、状态操作三列结构
  - 进度轴高度压缩，等待/当前/完成/失败状态更清晰，阶段说明单行截断
  - Tab 与内容区合并为同一个工作面板，降低割裂感
  - 笔记区三栏固定为 `300px minmax(0, 1fr) 280px`，收敛图片和正文输入高度
  - 底部操作栏压实，并保留自动刷新与最近保存状态位
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/task_detail.html`、`scripts/static/css/task_detail.css`、`scripts/static/js/task_detail.js`、`docs/planning/V2_PLAN.md` 和本条记录
- 风险与注意事项：
  - 本次不改后端 API、不改数据结构、不改 `web_app_legacy.py`
  - CSS 仍在既有页面样式末尾追加覆盖，后续可单独安排样式文件瘦身

## 2026-06-16（任务详情页工作台优化）
- 变更摘要：优化任务详情页为更清晰的任务详情工作台，补齐 5 秒自动刷新和编辑区保护。
- 影响范围：Web / 任务详情页
- 行为变化：
  - 顶部概览展示封面、作品信息、状态、进度百分比、创建时间、耗时、重试次数、刷新提示和手动刷新
  - 进度轴保留 7 阶段数据，区分已完成、当前、等待、失败/终止状态
  - Tab 顺序调整为笔记内容、拆文结果、AI评分、修改记录
  - 笔记内容整理为图片预览、编辑区、AI 建议/关键词/字数统计三栏，保留其他图片缩略图
  - 自动刷新每 5 秒更新非编辑区；标题、正文、标签存在焦点或未保存草稿时不覆盖编辑区
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web/templates/task_detail.html`、`scripts/static/css/task_detail.css`、`scripts/static/js/task_detail.js`、`docs/planning/V2_PLAN.md` 和本条记录
- 风险与注意事项：
  - 本次不改后端 API、不改数据结构、不改 `web_app_legacy.py`
  - 重新生成、重新评分接口仅验证按钮 URL 映射，未真实触发模型调用

## 2026-06-16（V2 生产链路闭环）
- 变更摘要：打通 worker AI 评分、任务详情保存草稿、重新评分、重新生成笔记与修改日志闭环。
- 影响范围：Worker / Web API / 队列 / 飞书笔记库
- 行为变化：
  - `deconstruct_worker.py` 在笔记生成后调用 `quality_scorer.score_note()`，评分失败时写入降级评分且不阻断主流程
  - 队列记录支持保存 dict 格式 `quality_score`、`modification_log`、飞书主表和小红书笔记库 record_id
  - `POST /api/task/<task_id>/rescore` 写回队列评分
  - `POST /api/task/<task_id>/save-draft` 写回队列草稿和本地修改日志；存在 `xhs_record_id` 且飞书可用时同步小红书笔记库
  - `POST /api/task/<task_id>/regenerate-note` 重新拆解生成笔记并写回队列
  - `docs/planning/V2_PLAN.md` 将生产链路闭环任务标记为完成
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退本次涉及的 worker、队列、任务详情 API、笔记 API、任务详情 JS 和文档变更
- 风险与注意事项：
  - 本次不做低分自动重生成，不重构 legacy 页面，不改 Docker 结构
  - 历史队列记录若没有 `xhs_record_id`，保存草稿仍会写队列，但不会同步飞书修改日志

## 2026-06-16（V2 稳定性基线）
- 变更摘要：修复 Web WSGI 启动入口，并为拆文队列增加轻量状态归一化。
- 影响范围：Web / 队列 / Docker 启动链路
- 行为变化：
  - `scripts/web_app.py` 暴露模块级 `app`，匹配 `gunicorn scripts.web_app:app`
  - `scripts/queue_manager.py` 新增 `normalize_status()`，把旧阶段状态映射到 `pending` / `processing` / `review` / `completed` / `failed`
  - 队列查询、统计和待处理任务选择兼容旧状态，不强制迁移历史 JSONL
  - `docs/planning/V2_PLAN.md` 将稳定性基线任务标记为完成
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退 `scripts/web_app.py`、`scripts/queue_manager.py`、`docs/planning/V2_PLAN.md` 和本条记录
- 风险与注意事项：
  - 本次不接 AI 评分闭环，不改任务详情页，不重构 legacy 页面
  - 历史 JSONL 中的原始 `status` 字段保持不变，仅在读取层归一化

## 2026-06-16（docs 结构整理）
- 变更摘要：规整 `docs/` 目录结构，新增文档总入口 `docs/INDEX.md`，按总览、规划、规范、运维四类归档文档。
- 影响范围：文档 / 协作流程
- 行为变化：
  - 项目总览与历史文档移动到 `docs/overview/`
  - V2 规划、页面设计与 schema 文档移动到 `docs/planning/`
  - 开发、协作、UI、截图交付规范移动到 `docs/guides/`
  - 运维、部署、ECS 检查清单保留在 `docs/operations/`
  - 主线程任务单继续放在 `docs/operations/planning/`
  - 后续新增全局文档必须同步更新 `docs/INDEX.md`
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：回退本次文档移动、`docs/INDEX.md`、路径引用修正和本条变更记录
- 风险与注意事项：
  - 本次只调整文档结构与引用，不修改业务代码
  - 历史任务单中的文档路径已同步改为新目录

## 2026-06-16
- 变更摘要：新增截图/设计图交付模板，并将 V2 接手后的稳定性、生产链路闭环、legacy 迁移拆成主线程可下发任务单。
- 影响范围：文档 / 协作流程
- 行为变化：
  - 新增 `docs/guides/SCREENSHOT_HANDOFF_TEMPLATE.md`，规范截图交付信息、执行线程工作流与验收方式
  - 新增 `task-v2-stability-baseline.md` / `task-v2-production-loop.md` / `task-v2-legacy-migration.md`
  - `docs/planning/V2_PLAN.md` 增加主线程任务池
  - `docs/guides/线程协作规范.md` 增加截图/设计图开发开场模板
  - `docs/guides/线程协作规范.md` 补充 Codex 额度与上下文控制规则，吸收旧项目 `CODEX_GIT_THREAD_PROTOCOL.md` 中适用于本项目的部分
- 配置变更（.env）：无
- 数据迁移/回填动作：无
- 回滚方式：删除新增文档并回退 `V2_PLAN.md` / `线程协作规范.md` / `CHANGELOG.md` 对应段落
- 风险与注意事项：
  - 本次只落文档计划，不修改业务代码
  - 当前代码仍存在未提交修改：`scripts/deconstruct_daily.py`、`scripts/model_adapter.py`

## 2026-03-02
- 变更摘要：增加“选题库-初筛”维护能力（schema 初始化 + 抓取写入 + Web 触发与监控）；Web UI 多次可用性与布局修复（500 修复、表单防挤压、溢出处理、列表可读性提升）。
- 影响范围：Web / 飞书表结构 / 抓取脚本
- 行为变化：
  - Web 新增 tab：选题库初筛；支持“按排行抓取/按类型(关键词)抓取”，后台异步执行并记录任务/结果日志
  - 初筛抓取：晋江关键词搜索走官方 AJAX；番茄关键词搜索暂用“排行榜池筛选”兜底
  - Web：任务状态、最近结果、最近写入预览；修复模板变量冲突导致的 500；优化表单布局与表格溢出
- 配置变更（.env）：
  - 新增/确认：`FEISHU_TOPIC_PRESCREEN_TABLE_ID`
- 数据迁移/回填动作：
  - 初筛表字段初始化（必要字段补齐）
  - 新抓取记录写入初筛表（历史数据可由人工删除）
- 回滚方式：
  - 关闭初筛功能：不使用 `prescreen_*` 脚本或隐藏 Web tab（代码回滚至上一次提交）
  - 若误写入：按“抓取批次”字段在飞书中过滤后批量删除
- 风险与注意事项：
  - 起点反爬未解决，仍为缺口
  - 番茄关键词搜索为兜底方案，覆盖不保证全量
  - 新增 Docker Compose 部署文件（`Dockerfile`/`docker-compose.yml`），需确认云主机 `.env` 完整后再启动
  - 新增 1.1 分析旁路脚本（`note_metrics_import.py` / `hot_model_report.py`），需先配置新表 ID

## 2026-03-03
- 变更摘要：统一“笔记结果库/实验台账/爆款因子库”关联键规范，新增实验台账维护脚本与 Web 实验参数透传。
- 影响范围：分析流程 / Web / 飞书表结构 / 配置
- 行为变化：
  - 统一键：`实验ID`（experiment_id）+ `笔记唯一键`（note_uid）
  - `note_metrics_import.py` 支持写入：`实验ID`、`实验版本(A/B/NA)`、`实验变量`
  - `hot_model_report.py` 支持 `--experiment-id` 按实验过滤，并同步因子时写入 `实验ID`
  - `web_app.py` 分析页新增实验参数输入：导入可填 实验ID/版本/变量；周报可填 实验ID 过滤
  - 新增 `experiment_ledger_upsert.py`，按实验ID upsert “实验台账”
- 配置变更（.env）：
  - 新增：`FEISHU_EXPERIMENT_LEDGER_TABLE_ID`
- 数据迁移/回填动作：
  - `note_analysis_schema.py` 增加实验字段初始化（若配置实验台账表则自动补字段）
- 回滚方式：
  - 不配置 `FEISHU_EXPERIMENT_LEDGER_TABLE_ID` 即可停用实验台账，不影响 1.0 与分析旁路基础流程
  - 周报不传 `--experiment-id` 即回到全量统计
- 风险与注意事项：
  - 单次实验仍应“一次只改一个变量”，否则实验结论不可解释

## 2026-03-03（续）
- 变更摘要：新增“账号7日快照”多-sheet导入链路；小红书笔记内容与提示词一致性修复；笔记初稿模板升级为移动端友好且更有“活人感”。
- 影响范围：分析流程 / Web / 飞书表结构 / 内容生成
- 行为变化：
  - 新增 `account_7d_import.py`：支持解析“近7日观看数据.xlsx”全部 sheet（总体+趋势）并入库
  - 分析页新增“7日观看快照上传（账号层）”入口
  - `账号7日快照`新增字段：`数据类型`、`趋势指标`、`趋势日期`、`趋势数值`、`趋势来源sheet`
  - 账号级新增派生指标：`观看率(%)`、`7日波动系数`
  - 小红书内容生成优化：初稿不再附带长提示词、段落改短、语气更偏真诚种草
  - 新增一致性修复脚本：`repair_xhs_record.py` / `repair_xhs_batch.py`
- 配置变更（.env）：
  - 新增：`FEISHU_ACCOUNT_7D_TABLE_ID`
- 数据迁移/回填动作：
  - `note_analysis_schema.py` 已补齐“账号7日快照”字段
  - 已完成一次真实导入（1条总体 + 42条趋势）
  - 已对风险小红书记录执行体检与修复
- 回滚方式：
  - 不配置 `FEISHU_ACCOUNT_7D_TABLE_ID` 即停用账号7日入库，不影响主流程
  - 不调用 repair 脚本即可停用一致性自动修复
- 风险与注意事项：
  - 当前 7日导入使用逐条 upsert，重复导入时耗时较长（后续可优化为“先拉键再批量写”）

## 2026-03-01
- 变更摘要：生图异步化与回填 worker、飞书 filter/view 提速与去重、Web 统计与队列面板、小红书笔记库“是否发布笔记”可编辑同步。
- 影响范围：主流程 / 生图 / Web / 飞书表结构
- 行为变化：
  - 主流程可入队生图任务，worker 异步回填，降低主流程失败面
  - 飞书查询优先 server-side filter，减少全表扫描与重复插入
  - Web：tab/分页/概览环形图；队列状态与最近回填结果面板
  - 小红书笔记库：支持展示与修改“是否发布笔记”，并同步回飞书
- 配置变更（.env）：
  - `IMAGE_GEN_ASYNC=true` 推荐开启
- 数据迁移/回填动作：
  - 新增队列日志文件：`logs/image_jobs.jsonl` 等
- 回滚方式：
  - 关闭异步：`IMAGE_GEN_ASYNC=false`（回到同步生图）
  - Web 回滚：停止服务并切回旧版本脚本
- 风险与注意事项：
  - 生图风控/限流时，建议加 sleep 与重试，并优先英文提示词

## 2026-03-05
- 变更摘要：确认 2.0 重构正式启动，新增“按周实施 + 验收点”推进机制；统一 2.0 目标为“稳定主干、可持续迭代”。
- 影响范围：项目架构 / Web / 工作流编排 / 文档治理
- 行为变化：
  - 由“功能追加模式”切换为“结构化重构模式”
  - 每周实施必须包含：任务清单、验收点、风险、回滚说明
  - 视觉验收统一采用“工作台结构（左侧固定菜单）+ 表格主视图”口径
- 配置变更（.env）：
  - 无新增必填项（本次为规划与实施方式变更）
- 数据迁移/回填动作：
  - 无（Week 1 仅做架构拆分与页面骨架，不改业务口径）
- 回滚方式：
  - 继续保留 `scripts/web_app.py.bak_*` 文件，若 2.0 页面不符合预期可快速恢复
- 风险与注意事项：
  - 本机存在多项目端口并行（8000 与 8101），验收前必须确认目标端口

## 2026-03-05（续）
- 变更摘要：Week1 开始落地“入口瘦身 + 服务层抽离 + 系统状态 API”。
- 影响范围：Web 架构 / 运行可观测性
- 行为变化：
  - `scripts/web_app.py` 继续作为薄入口，统一从 `scripts.web.app:create_app()` 启动。
  - 新增服务层：`scripts/web/services/local_runs.py`，抽离本地运行记录与生图队列统计逻辑。
  - 新增服务层：`scripts/web/services/xhs_fields.py`，抽离小红书缺项判定、本地 MD 查找、字段转笔记文本逻辑。
  - 新增服务层：`scripts/web/services/xhs_candidates.py`，抽离候选版本缓存读写。
  - 新增服务层：`scripts/web/services/xhs_facts.py`，抽离事实卡聚合、事实文本化、事实覆盖逻辑。
  - 新增服务层：`scripts/web/services/prescreen_status.py`，抽离初筛任务状态与最近写入读取逻辑。
  - `scripts/web_app_legacy.py` 对应函数改为调用服务层，行为不变。
  - 新增接口：
    - `GET /_health`
    - `GET /api/system/local-summary`
    - `GET /api/system/xhs-overview`
    - `GET /api/system/prescreen-status`
    - `GET /api/system/analysis-status`
- 配置变更（.env）：
  - 无新增项
- 数据迁移/回填动作：
  - 无
- 回滚方式：
  - 入口回滚：恢复 `scripts/web_app.py.bak_*` 或切回 `scripts/web_app_legacy.py` 直接启动。
  - API 回滚：移除 `scripts/web/routes/system_api.py` 注册即可，不影响原页面。
- 风险与注意事项：
  - 当前仍依赖 `web_app_legacy` 作为主渲染入口，后续需要按模块继续迁移路由与模板。
