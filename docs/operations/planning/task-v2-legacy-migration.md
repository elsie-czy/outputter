## 当前线程：Sprint V2.x — legacy 迁移与文件瘦身

> 主线程下发 | 执行线程独立开发 | 小步迁移 | 不改变业务口径

---

=== **背景** ===

`scripts/web_app_legacy.py` 仍有 2878 行，`deconstruct_daily.py`、`production_center.css`、`task_detail.html` 等文件也已超过规范建议。该线程不是做新功能，而是逐步降低维护成本，确保后续页面按 V2 架构开发。

---

=== **开工前必读** ===

| # | 文件 | 为什么读 |
|---|------|----------|
| 1 | `docs/guides/开发规范手册.md` | 文件长度与模块拆分规范 |
| 2 | `docs/guides/项目目录结构规范.md` | V2 目录职责 |
| 3 | `docs/guides/ui-rules.md` | 样式迁移时保持 UI 规范 |
| 4 | `scripts/web_app_legacy.py` | 识别待迁移函数 |
| 5 | `scripts/web/routes/` | 现有 Blueprint 结构 |
| 6 | `scripts/web/services/` | 现有服务层结构 |

---

=== **原则** ===

1. 不往 `web_app_legacy.py` 增加新逻辑。
2. 每次只迁移一个功能域。
3. 迁移前后 URL、API 返回结构保持兼容。
4. 迁移后保留回滚路径。
5. 每个被迁移函数必须有对应验证命令或页面验证。

---

=== **建议拆分顺序** ===

| 阶段 | 目标 | 说明 |
|------|------|------|
| 1 | 只读 API 迁移 | 风险最低，先迁移列表、状态、预览类接口 |
| 2 | 写操作 API 迁移 | 再迁移保存、发布状态、修复触发等接口 |
| 3 | 模板剥离 | 将 legacy 内嵌 HTML 迁入 `scripts/web/templates/` |
| 4 | 服务层抽取 | 将飞书读写、字段转换、日志读取放入 `scripts/web/services/` |
| 5 | 删除或冻结 legacy 路由 | 确认 V2 覆盖后，只保留兼容入口 |

---

=== **第一批建议任务** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/web_app_legacy.py` | 只删已迁移重复代码 | 不新增功能 |
| `scripts/web/routes/xhs_api.py` | 承接小红书笔记库 API | 保持返回结构 |
| `scripts/web/services/xhs_fields.py` | 承接字段转换 | 已存在，继续补齐 |
| `scripts/web/services/xhs_preview_data.py` | 承接预览数据 | 已存在，继续补齐 |
| `docs/planning/V2_PLAN.md` | 更新迁移进度 | 标记已迁移范围 |

---

=== **文件瘦身目标** ===

| 文件 | 当前行数 | 目标 |
|------|----------|------|
| `scripts/web_app_legacy.py` | 2878 | 不再增长，逐步降到 1000 以下 |
| `scripts/deconstruct_daily.py` | 1092 | 拆出 note builder / image prompt builder / feishu sync |
| `scripts/static/css/production_center.css` | 734 | 拆出表格、统计卡、弹窗样式 |
| `scripts/web/templates/task_detail.html` | 301 | 抽取组件或局部模板 |

---

=== **验证** ===

```bash
source .venv/bin/activate
bash scripts/check_js.sh
python scripts/web_app.py
curl http://127.0.0.1:8080/_health
```

页面验证：

- `/`
- `/deconstruct`
- `/topic-pool`
- `/production-center`
- `/task/<已有任务ID>`

---

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main
git pull --ff-only origin main
git checkout -b refactor/v2-legacy-migration
```

结束时：

```bash
git add -A
git commit -m "refactor: V2 legacy迁移与文件瘦身"
git push origin refactor/v2-legacy-migration
```

