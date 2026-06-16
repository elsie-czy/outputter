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
