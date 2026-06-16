## 当前线程：Sprint V2.0 — 稳定性基线修复

> 主线程下发 | 执行线程独立开发 | 只修稳定性与启动链路 | 不做新功能

---

=== **背景** ===

项目已经进入 V2 生产工作台阶段，但存在几个会影响后续开发的基础问题：Docker/Gunicorn 启动目标不匹配、队列状态命名混用、部分文件超长、当前未提交改动未归档说明。该线程目标是先把可运行基线稳住，为后续生产链路闭环和页面开发建立可靠地面。

---

=== **开工前必读** ===

| # | 文件 | 为什么读 |
|---|------|----------|
| 1 | `docs/guides/开发规范手册.md` | 代码、文件长度、错误处理规范 |
| 2 | `docs/guides/线程协作规范.md` | 分支、交接摘要、文档同步要求 |
| 3 | `docs/guides/项目目录结构规范.md` | 目录职责和新增文件位置 |
| 4 | `docs/planning/V2_PLAN.md` | V2 目标和任务状态 |
| 5 | `docker-compose.yml` | 当前容器启动方式 |
| 6 | `scripts/web_app.py` / `scripts/web/app.py` | Web 启动入口 |

---

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/web_app.py` | 修改 | 增加模块级 `app = create_app()`，保证 `gunicorn scripts.web_app:app` 可启动 |
| `docker-compose.yml` | 修改 | 确认 web 使用正确 app target；runner 后续可切 worker，但本线程只修启动错误 |
| `scripts/queue_manager.py` | 小改 | 增加状态归一化函数，不大改业务 |
| `docs/planning/V2_PLAN.md` | 修改 | 记录稳定性基线任务状态 |
| `docs/CHANGELOG.md` | 修改 | 记录本次稳定性修复 |

---

=== **技术要点** ===

### 1. 修复 Web WSGI 入口

当前 `docker-compose.yml` 使用：

```yaml
gunicorn -w 2 -b 0.0.0.0:8101 scripts.web_app:app
```

但 `scripts/web_app.py` 目前只有 `main()`，没有模块级 `app`。应改为：

```python
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
app = create_app()

def main():
    host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.getenv("WEB_PORT", "8080"))
    app.run(host=host, port=port, debug=False)
```

注意：避免重复创建 app 导致 Blueprint 重复注册。`register_routes()` 已有幂等判断。

### 2. 状态归一化

新增一个轻量函数，例如：

```python
def normalize_status(status: str) -> str:
    mapping = {
        "waiting": "pending",
        "pending": "pending",
        "retry": "pending",
        "processing": "processing",
        "deconstructing": "processing",
        "generating_note": "processing",
        "ai_scoring": "processing",
        "generating_image": "processing",
        "human_review": "review",
        "done": "completed",
        "completed": "completed",
        "failed": "failed",
    }
    return mapping.get(str(status or "").strip(), "pending")
```

本线程只新增兼容层，不强制迁移历史 JSONL 数据。

### 3. 不处理范围

- 不重构 `web_app_legacy.py`
- 不接入 AI 评分闭环
- 不修改页面视觉
- 不处理当前未提交的 `deconstruct_daily.py` / `model_adapter.py` 内容，除非主线程明确确认

---

=== **验证** ===

```bash
source .venv/bin/activate
bash scripts/check_js.sh
python scripts/web_app.py
curl http://127.0.0.1:8080/_health
```

如需验证 Docker：

```bash
docker compose config
docker compose up -d web
docker compose ps
docker compose logs web
```

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b hotfix/v2-stability-baseline
```

结束时：

```bash
git add -A
git commit -m "fix: V2 稳定性基线 — 修复Web启动入口与状态归一化"
git push origin hotfix/v2-stability-baseline
```

---

=== **交接摘要必须包含** ===

1. Web 本地启动是否成功
2. `/_health` 是否成功
3. Docker 是否验证，若未验证说明原因
4. 状态归一化影响范围
5. 未处理风险

