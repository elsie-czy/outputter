# 运维与日常使用

## 1. 推荐运行策略（稳定与提效）
- 主流程：只做拆解、写入飞书、入队生图任务（不阻塞生图）
- 生图回填：独立 worker 异步跑，支持失败重试与结果日志

`.env` 推荐：
- `IMAGE_GEN_ENABLED=true`
- `IMAGE_GEN_ASYNC=true`

## 2. 日常命令
- 主流程：`python scripts/deconstruct_daily.py`
- Web：`python scripts/web_app.py`
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
- 主流程：`logs/run_summary.json` 是否 `status=success`，以及 `errors` 阶段
- 生图队列：`logs/image_jobs.jsonl` 是否持续增长
- worker 是否跟上：`logs/image_jobs.cursor` 是否前进、`logs/image_job_results.jsonl` 是否持续产出

