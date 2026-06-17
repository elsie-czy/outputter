# 运维与日常使用

## 1. 推荐运行策略（稳定与提效）
- 拆文 worker：常驻消费 `data/queue/deconstruct_queue.jsonl`，有 pending 任务时顺序处理，空队列时等待
- 生图回填：独立 worker 异步跑，支持失败重试与结果日志

`.env` 推荐：
- `IMAGE_GEN_ENABLED=true`
- `IMAGE_GEN_ASYNC=true`

## 2. 日常命令
- Web：`python scripts/web_app.py`
- 拆文 worker（本地手动常驻运行）：`python scripts/deconstruct_worker.py`
- Docker Web：`docker compose up -d web`，宿主机访问 `http://127.0.0.1:8080`
- Docker 拆文 worker：`docker compose up -d deconstruct-runner`
- 生图 worker（消费队列增量）：`python scripts/jimeng_worker.py jobs`
- 生图 worker（补缺口扫描）：`python scripts/jimeng_worker.py missing`

## 3. 回填与限流建议
即梦与飞书附件上传都可能限流或风控：
- worker 可调参数：`python scripts/jimeng_worker.py jobs <limit> <max_retries> <sleep_sec>`
  - `limit`：本次最多处理多少条记录（0 表示不限制）
  - `max_retries`：单条记录失败重试次数（默认 2）
  - `sleep_sec`：每个字段生成之间的 sleep（可用于降低风控/限流）

## 4. 回滚与安全
- 文档与代码中不要写入任何真实密钥
- 如果需要临时关闭生图：`.env` 设置 `IMAGE_GEN_ENABLED=false`
- 如果需要临时只跑主流程不回填：保持 `IMAGE_GEN_ASYNC=true`

## 5. 关键监控点
- 拆文 worker：`logs/deconstruct_worker.log` 是否持续记录启动、等待、任务 ID、状态变更和异常原因
- 拆文队列：`data/queue/deconstruct_queue.jsonl` 中 pending/processing/done/failed 是否符合预期
- 生图队列：`logs/image_jobs.jsonl` 是否持续增长
- worker 是否跟上：`logs/image_jobs.cursor` 是否前进、`logs/image_job_results.jsonl` 是否持续产出
