## 当前线程：Sprint V2.1 — 生产链路闭环

> 主线程下发 | 执行线程独立开发 | 聚焦任务产出闭环 | 不做大规模 UI 重构

---

=== **背景** ===

V2 队列、worker、任务详情页和质量评分模块已经具备雏形，但存在“模块有了、闭环未稳”的问题。该线程目标是打通一条可靠生产链路：

```text
选题入队 → worker 消费 → 拆文 → 笔记生成 → AI评分 → 图片生成 → 任务详情展示 → 保存修改日志
```

---

=== **开工前必读** ===

| # | 文件 | 为什么读 |
|---|------|----------|
| 1 | `docs/V2_PLAN.md` | V2.1 质量闭环目标 |
| 2 | `docs/V2_DECONSTRUCT_CENTER.md` | 任务详情、评分、修改日志设计 |
| 3 | `scripts/deconstruct_worker.py` | 生产链路主入口 |
| 4 | `scripts/queue_manager.py` | 队列状态与结果写入 |
| 5 | `scripts/quality_scorer.py` | AI 评分模块 |
| 6 | `scripts/web/routes/task_detail_page.py` | 任务详情 API |
| 7 | `scripts/web/routes/note_api.py` | 笔记保存/重生成/评分 API |

---

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/deconstruct_worker.py` | 修改 | 在笔记生成后调用 `score_note()`，写入 `quality_score` |
| `scripts/queue_manager.py` | 修改 | 确保 `quality_score` 支持 dict 格式并能持久化 |
| `scripts/web/routes/task_detail_page.py` | 修改 | 接通重新评分、保存草稿、重新生成笔记，不再返回占位成功 |
| `scripts/web/routes/note_api.py` | 修改 | 保存修改后同步更新队列与飞书 |
| `scripts/static/js/task_detail.js` | 修改 | 对接真实 API，展示保存/评分结果 |
| `docs/V2_PLAN.md` | 修改 | 更新 V2.1 闭环任务状态 |
| `docs/CHANGELOG.md` | 修改 | 记录行为变化 |

---

=== **技术要点** ===

### 1. Worker 接入 AI 评分

在 `xhs_note = build_xhs_note(work, analysis)` 后调用：

```python
from scripts.quality_scorer import score_note

score = score_note(xhs_note)
update_status(rid, "ai_scoring", quality_score=score)
```

评分完成后进入后续图片生成阶段。若评分失败，记录 fallback，不阻塞主流程。

### 2. 任务详情 API 去 TODO

以下接口不能继续返回占位成功：

- `POST /api/task/<task_id>/regenerate-note`
- `POST /api/task/<task_id>/rescore`
- `POST /api/task/<task_id>/save-draft`

最低要求：

- `rescore` 调用 `score_note()` 并写回队列
- `save-draft` 更新队列中的 `note_content`，如存在小红书笔记库 record_id 则写飞书
- `regenerate-note` 调用现有 `analyze_work()` + `build_xhs_note()`，写回队列

### 3. 修改日志

保存草稿时必须生成修改日志：

```text
YYYYMMDD HH:MM | 字段: 标题/正文/标签 | 说明: 人工修改 | 评分:N
```

优先通过 `FeishuClient.save_modification_log()` 写入飞书；飞书不可用时至少保存在队列记录里。

### 4. 低分策略先不自动重生成

本线程只做评分与展示，不做低分自动重试。自动重试留给后续任务，避免一次改动过大。

---

=== **验证** ===

```bash
source .venv/bin/activate
bash scripts/check_js.sh
python scripts/web_app.py
curl http://127.0.0.1:8080/_health
```

手动验证：

| # | 操作 | 预期 |
|---|------|------|
| 1 | 打开 `/production-center` | 能看到任务列表 |
| 2 | 打开 `/task/<id>` | 能看到笔记、评分、拆文结果 |
| 3 | 点击重新评分 | `quality_score` 更新 |
| 4 | 修改笔记并保存 | 队列记录更新；飞书配置存在时写飞书 |
| 5 | 重新生成笔记 | 笔记内容更新，不影响其他任务 |

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b feature/v2-production-loop
```

结束时：

```bash
git add -A
git commit -m "feat: 打通V2生产链路评分与笔记保存闭环"
git push origin feature/v2-production-loop
```

