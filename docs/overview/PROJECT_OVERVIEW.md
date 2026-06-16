# personal-supertool 项目说明（迁移用）

## 1. 项目目的
本项目用于将“网文选题 -> 拆解分析 -> 生成小红书图文笔记（含配图提示词/图片） -> 写回飞书多维表格 -> Web 预览/复制”的流程自动化，降低人工整理成本，提高批量产出效率，并将可复用的“套路/人设/冲突/情绪/金句”等资产沉淀到关联库。

核心产出包括：
- 主表：作品拆解结论（核心冲突/情绪钩子/情节节点等）
- 小红书笔记库：小红书包装字段、配图提示词、笔记初稿附件、（可选）即梦生图附件
- 关联库：开篇套路库、人物设定库、冲突设计库、情绪触发库、金句库（可复用资产）
- Web：查看与预览记录、一键复制小红书笔记内容、查看最近运行状态

## 0. 迭代里程碑（迁移期间功能演进摘要）
以下为 2026-02-27 至 2026-03-03 期间（迁移后）的主要“功能迭代与优化点”，用于迁移/交接时快速理解现状：

- 飞书写入稳定性
  - 修复字段类型不匹配导致的写入失败（例如 Number 字段必须写数值，不可写字符串）
  - 统一 select/multi-select 写入策略，避免写入不可读的 option id（优先写 option 名称，并做 option 校验/clamp）
- 模型侧（仅国内）
  - 适配国内 OpenAI-compatible 接口（Qwen 等），并提供可切换模型配置入口
  - 对小红书笔记生成追加“合规约束”提示：避免引流嫌疑/违规内容
- 生图链路（即梦）
  - prompt 规则升级：英文提示词优先、禁止文字水印、明确男女主性别与时代一致性、每个提示词生成 2 张备选
  - 生图异步化：主流程只入队，worker 异步回填，降低整体耗时与失败面
  - 缓存 prompt_hash 生成结果，省钱省时并可复现
- Web 产品化
  - 主页改为“小红书内容生成工具🔧”，增加 tab：概览 / 本地执行记录 / 小红书笔记库 / 选题库初筛
  - 小红书笔记库：展示并可编辑“是否发布笔记”，同步回飞书
  - 概览：增加发布占比环形图、任务数、队列状态等统计
  - 生图队列监控：读取 `logs/image_jobs.cursor` 与 `logs/image_job_results.jsonl` 展示最近回填结果
  - 初筛抓取页：支持“按排行抓取/按类型(关键词)抓取”，并展示最近任务状态、最近写入预览
  - 分析页：新增“7日观看快照上传（账号层）”，支持多-sheet 报表上传
- 分析数据层（1.1）
  - 统一关联键：`实验ID` + `笔记唯一键`
  - 新增“实验台账”维护脚本与按实验过滤周报
  - 新增“账号7日快照”表导入（总体+趋势）
  - 新增账号级派生指标：`观看率(%)`、`7日波动系数`
- 内容质量优化
  - 小红书笔记初稿模板升级为“移动端友好 + 活人感种草口吻”
  - 增加小红书记录一致性体检/批量修复脚本（提示词漂移、时代冲突、附件缺失）
- 选题库-初筛（接管维护）
  - 初始化字段（schema）并维护字段映射，确保每次抓取尽可能填全字段
  - 数据抓取：已接入番茄排行榜与晋江 TopTen；晋江支持关键词搜索（AJAX）；番茄关键词搜索目前使用“排行榜池筛选”兜底

版本标记：
- v1.0（可打版基线）：2026-03-02
- v1.1（分析与实验协同）：2026-03-03

## 2. 可实现的效果（对外可见）
- 从飞书“选题库”按规则拉取待拆解作品
- 调用大模型（目前为 Qwen OpenAI-compatible 接口）输出结构化拆解 JSON
- 生成小红书图文笔记 Markdown 初稿，并作为附件上传到飞书“小红书笔记库”
- 生成配图提示词（已升级为英文优先，约束性别、时代一致、禁止文字水印），写入“生成配图提示词1~5”
- 调用即梦生图，生成每条提示词 2 张备选图，并写入“即梦生图1~5”（附件字段）
- 同步维护关联库（upsert 防重复）：开篇/人物/冲突/情绪/金句
- 生成运行摘要与错误日志，Web 首页展示最近运行状态
- 维护“选题库-初筛”：从平台抓取高潜作品写入初筛表，供人工审核入库
- 导入“近7日观看数据”多-sheet报表，维护账号层趋势数据

## 3. 业务流程（端到端）
1. 选题拉取
   - 来源：飞书“选题库”
   - 过滤：是否拆解 != 已拆解
2. 搜索补全（可选）
   - 按“搜索要素/作品名”等补齐平台、分类、简介、字数等
3. 拆解分析
   - 大模型输出结构化 JSON：开篇套路、人物设定、三层冲突、情绪触发、金句、小红书包装、配图提示词
4. 落地文件（本地）
   - 拆解报告：`outputs/拆解报告/<日期>_<作品_作者>_拆解报告.md`
   - 小红书笔记：`outputs/小红书笔记_v3/<作品_作者>/<作品名称>-小红书笔记初稿.md`
   - 实验记录：`outputs/实验记录/<日期>_实验记录.md`
5. 写回飞书
   - 主表：写拆解核心字段（并做去重/幂等更新）
   - 小红书笔记库：写包装字段、写配图提示词、上传笔记 Markdown 附件
6. 关联库同步（可复用资产沉淀）
   - 开篇套路库、人物设定库、冲突设计库、情绪触发库、金句库：写入/更新并回链主表字段
7. 生图与回填（两种模式）
   - 同步模式：主流程直接生图并回填（耗时较长，失败会影响主流程）
   - 异步模式：主流程只“入队”，由 worker 回填（推荐）
8. 选题库-初筛抓取（新增）
   - 入口：Web “选题库初筛” tab 或脚本运行
   - 模式：按排行抓取 / 按类型(关键词)抓取
   - 写入：飞书“选题库-初筛”表（包含推荐热度/收藏/书评/是否完结/简介/入选维度等）
9. 分析数据导入与复盘（新增）
   - 笔记级：上传创作者平台导出，写入“笔记结果库”
   - 账号级：上传“近7日观看数据”（多-sheet），写入“账号7日快照”
   - 周报：按全量或实验ID生成，并可同步“爆款因子库”

## 4. 技术架构概览
- 语言与运行：Python（当前环境为项目自带 `.venv`）
- 外部依赖：
  - 飞书开放平台 API（多维表格/附件上传）
  - 大模型：Qwen（DashScope OpenAI-compatible `/chat/completions`）
  - 生图：即梦（火山引擎 Visual API 异步任务提交/轮询）
- 主要脚本：
  - `scripts/deconstruct_daily.py`：主流程 orchestrator（选题->分析->写主表->写小红书笔记库->关联库同步->日志）
  - `scripts/model_adapter.py`：模型适配（OpenAI-compatible），支持多端点/重试
  - `scripts/related_sync.py`：关联库 upsert 防重复、字段填充与回链主表
  - `scripts/image_generator.py`：即梦生图（提交/轮询、签名兼容、prompt_hash 本地缓存）
  - `scripts/jimeng_worker.py`：异步回填 worker（消费队列/补缺口、带游标/锁/重试/结果日志）
  - `scripts/web_app.py`：Web UI（列表、筛选、预览、一键复制、最近运行状态）
  - `scripts/feishu_client.py`：飞书 API 客户端（支持服务端 filter 查询、附件上传）
  - `scripts/prescreen_schema.py`：初始化“选题库-初筛”字段（建表字段/补字段）
  - `scripts/prescreen_fetch_insert.py`：抓取平台数据并 upsert 写入“选题库-初筛”
  - `scripts/topic_prescreen_maintain.py`：对初筛表做补全/维度提取/数值化等维护
  - `scripts/note_metrics_import.py`：导入创作者平台 xlsx 到“笔记结果库”（1.1 分析旁路）
  - `scripts/hot_model_report.py`：基于结果库输出“爆款基因周报”，可选同步到“爆款因子库”
  - `scripts/experiment_ledger_upsert.py`：按实验ID维护“实验台账”（A/B 设计、结论、样本）
  - `scripts/account_7d_import.py`：导入“近7日观看数据”多-sheet报表（总体+趋势）到“账号7日快照”
  - `scripts/repair_xhs_record.py`：单条小红书记录修复（提示词+初稿附件）
  - `scripts/repair_xhs_batch.py`：小红书库一致性批量体检/修复

## 5. 飞书数据结构（表与字段约定）
表 ID 在 `scripts/feishu_config.py` 的 `related_table_ids` 中配置。

### 5.1 主表（拆解记录表）
用途：保存拆解结论的“最终结果”，用于筛选、检索和业务回溯。

典型字段（示例）：作品名称、作者、平台、分类、简介、字数（万）、核心冲突、情绪钩子、情节节点摘要、金句Top5、女主/男主设定等。

### 5.2 小红书笔记库
用途：保存小红书包装、提示词、附件（笔记初稿、即梦图片）。

关键字段：
- `生成配图提示词1~5`：配图提示词（英文优先）
- `即梦生图1~5`：附件列，每列 2 张备选图（需要先在飞书表中创建）
- `小红书笔记初稿`：笔记 Markdown 附件

### 5.3 关联库（资产沉淀）
开篇套路库/人物设定库/冲突设计库/情绪触发库/金句库：用于沉淀可复用的“写作资产”。
当前逻辑为 upsert：按业务唯一键查找存在则更新，不存在才创建，避免重复膨胀。

## 6. 运行方式（常用）
### 6.1 主流程
- 运行：`python scripts/deconstruct_daily.py`
- 输入：通过 `.env` 控制（是否从飞书选题库拉取、是否跳过已有、是否生图、是否异步等）

### 6.2 Web
- 运行：`python scripts/web_app.py`
- 端口：`.env` 的 `WEB_PORT`

### 6.3 异步生图回填（推荐）
1. `.env` 设置：`IMAGE_GEN_ENABLED=true` + `IMAGE_GEN_ASYNC=true`
2. 主流程跑批：只会入队到 `logs/image_jobs.jsonl`
3. 回填执行：
   - 消费队列：`python scripts/jimeng_worker.py jobs`
   - 补缺口：`python scripts/jimeng_worker.py missing`

### 6.4 初筛抓取
- 初始化字段（只需一次，或字段变动时运行）：`python scripts/prescreen_schema.py`
- 抓取并写入（排行）：`python scripts/prescreen_fetch_insert.py --mode rank --sources fanqie,jjwxc --limit 60 --batch YYYY-MM-DD`
- 抓取并写入（关键词）：`python scripts/prescreen_fetch_insert.py --mode search --query 末世 --sources jjwxc,fanqie --limit 30 --batch YYYY-MM-DD`

## 7. 关键配置（.env）
说明：请勿在文档中写入真实密钥。

### 7.1 飞书
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- `FEISHU_NOTE_METRICS_TABLE_ID`
- `FEISHU_HOT_FACTORS_TABLE_ID`
- `FEISHU_EXPERIMENT_LEDGER_TABLE_ID`
- `FEISHU_ACCOUNT_7D_TABLE_ID`
- `FEISHU_MAIN_TABLE_ID`
- `FEISHU_TOPIC_PRESCREEN_TABLE_ID`（选题库-初筛 table_id）

### 7.2 模型（Qwen）
- `MODEL_PROVIDER=qwen`
- `QWEN_API_KEY`
- `QWEN_BASE_URLS`（仅国内端点建议：`https://dashscope.aliyuncs.com/compatible-mode/v1`）
- `QWEN_MODEL=qwen-plus`

### 7.3 即梦生图
- `IMAGE_GEN_ENABLED=true|false`
- `IMAGE_GEN_ASYNC=true|false`（推荐 true）
- `JIMENG_BASE_URL=https://visual.volcengineapi.com`
- `JIMENG_ACCESS_KEY_ID` / `JIMENG_SECRET_ACCESS_KEY`
- `JIMENG_ACTION=CVSync2AsyncSubmitTask`
- `JIMENG_POLL_ACTION=CVSync2AsyncGetResult`
- `JIMENG_VERSION=2022-08-31`
- `JIMENG_REQ_KEY=jimeng_t2i_v30`（已验证可用的 req_key）
- `JIMENG_CACHE_ENABLED=true`（prompt_hash 本地缓存）

## 8. 日志与可观测性
- `logs/run_summary.json`：最近一次主流程的状态/耗时/错误
- `logs/records.jsonl`：Web 用的运行记录（路径、record_id、prompts 等）
- `logs/sync_errors.jsonl`：飞书同步阶段错误
- `logs/image_jobs.jsonl`：异步生图队列
- `logs/image_jobs.cursor`：队列消费游标
- `logs/image_job_results.jsonl`：异步回填结果记录
- `logs/prescreen_web_jobs.jsonl`：Web 发起的初筛抓取任务队列
- `logs/prescreen_web_job_results.jsonl`：Web 发起的初筛抓取任务结果
- `logs/prescreen_ingest.jsonl`：初筛抓取写入记录（脚本侧）
- `logs/prescreen_ingest_errors.jsonl`：初筛写入错误（脚本侧）

## 9. 常见问题与排障
### 9.1 DashScope TLS/SSL 问题
在 macOS + LibreSSL 环境下可能出现握手不稳定。现状已通过端点与请求策略规避过一次问题。

### 9.2 即梦风控
常见错误：
- `50413 Post Text Risk Not Pass`：提示词触发文本风控（已在流程中加入英文 fallback/降敏重试策略）
- `50511 Post Img Risk Not Pass`：生成图片触发风控（通常需要更保守提示词或降级为通用提示）

### 9.3 飞书重复数据
关联库与主表已加入 upsert 与服务端过滤查询，减少重复插入。

### 9.4 平台抓取限制
- 起点：存在反爬（HTTP 202 等），当前未接入稳定抓取；建议后续以“榜单导出/第三方聚合”或人工补齐为主
- 番茄：关键词搜索接口在前端签名链路上较重，当前“按类型搜索”使用排行榜池筛选兜底（可用但非全量）

## 10. 迁移清单（Checklist）
- 安装 Python/创建 venv/安装依赖（至少 `requests/flask/python-dateutil`）
- 配置 `.env`（飞书、Qwen、即梦）
- 确认飞书表结构与字段存在（尤其是小红书笔记库的 `生成配图提示词1~5`、`即梦生图1~5`、`小红书笔记初稿`）
- 先跑 1 条主流程验证（不开生图），再开启异步生图回填

## 11. 2.0 重构计划（执行中）
目标：在不影响 1.0 每日产出的前提下，完成“架构分层 + 数据契约 + 事实闸门 + 实验闭环”。

### 11.1 分阶段安排（4 周）
- Week 1：架构分层与 UI 骨架统一（不改业务口径）
- Week 2：飞书契约校验与关联修复中心
- Week 3：事实一致性闸门与采纳闸门
- Week 4：分析闭环、测试与运维固化

### 11.2 Week 1 工作要点（细化）
1. Web 架构拆分
- 将 `scripts/web_app.py` 拆为：
  - `scripts/web/routes/`（页面与动作路由）
  - `scripts/web/services/`（飞书读写、任务执行、业务编排）
  - `scripts/web/templates/`（模板文件）
- `scripts/web_app.py` 只保留 app bootstrap 与注册蓝图。

2. 状态定义统一
- 新增统一状态枚举：`idle/queued/running/success/failed/blocked`
- 统一用于：页面展示、异步任务、修复任务、分析任务。

3. 页面骨架统一
- 全站统一工作台结构：左侧固定菜单 + 中央主工作区 + 右侧辅助区。
- local/xhs 页保持表格主视图（操作列可见），确保可快速批量操作。

4. 日志口径统一
- 所有任务日志统一字段：`job_id`、`kind`、`status`、`summary`、`error`、`ts`。
- 保留原日志文件，新增口径仅做兼容扩展，不破坏已有读取。

5. 安全与回滚
- 每次改造前保留 `web_app.py.bak_*` 备份。
- 保证“失败可回退到 1.0 页面”。

### 11.3 Week 1 验收点（必须全部通过）
1. 结构验收
- 代码中已出现 `routes/services/templates` 三层目录并被真实引用。
- `web_app.py` 明显瘦身（仅启动和注册逻辑，不再承载大段模板与业务逻辑）。

2. 功能验收
- 五个 tab（概览/本地/笔记库/初筛/分析）均可正常访问，无 500。
- 现有主流程能力不退化：筛选、预览、重生、发布、抓取、分析入口可用。

3. 体验验收
- 左侧菜单固定贴边、滚动不动；内容区滚动独立。
- local/xhs 为表格视图，操作按钮可直接执行。
- 每页有明确主操作提示（用户 5 秒内能判断下一步）。

4. 运维验收
- 端口与项目对应关系清晰（避免 8000/8101 混淆）。
- 提供回滚命令并验证可恢复。

5. 文档验收
- `docs/overview/DAILY_COLLAB_NOTES.md`、`docs/CHANGELOG.md`、`docs/overview/PROJECT_OVERVIEW.md` 同步更新。
