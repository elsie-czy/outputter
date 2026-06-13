## 当前线程：措施1 — 数据格式归一化层

> 主线程下发 | 最高优先级 | 完成后解决"数据格式断层"根因

---

=== **背景** ===

当前系统存在严重的数据格式断层问题：

```
飞书主表:  字段名中文({开篇套路类型→"KP215"})  |  值类型: feishu option ID/数组
worker缓存: 原始飞书字段 or 可分析JSON           |  值类型: 混杂
前端API:   驼峰英文(openings/characters)          |  值类型: 数组/对象
前端渲染:  JS对象(result.openings)               |  值类型: 数组
```

三层之间没有统一契约，缓存命中时全页面白屏。需要建一个全项目唯一的数据格式转换入口。

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/data_normalizer.py` | **新建** | 数据格式归一化模块，全项目唯一入口 |
| `scripts/web/routes/task_detail_page.py` | **修改** | deconstruct_result 转换改用 normalizer |
| `scripts/deconstruct_worker.py` | **修改** | `_feishu_to_analysis_format` 改用 normalizer |
| `docs/V2_PLAN.md` | **修改** | 更新进度，新增"稳定性措施"章节 |

=== **技术要点** ===

### 1. data_normalizer.py 结构

```python
"""
数据格式归一化模块
全项目唯一入口：所有 feishu 字段 → 统一 JSON 格式的转换都在这里。
"""

def normalize_feishu_record(fields: dict, source: str = "main") -> dict:
    """
    将飞书记录字段转为统一 analysis JSON 格式
    
    source: "main" → 飞书主表字段
            "xhs"  → 小红书笔记库字段
    
    返回格式:
    {
        "openings": ["套路1", "套路2", ...],
        "characters": ["女主：描述", "男主：描述", "亮点配角：描述"],
        "conflicts": ["第一层：描述", "第二层：描述", "第三层：描述"],
        "emotions": ["情绪1", "情绪2", ...],
        "quotes": ["金句1", "金句2", ...],
        "note": {"title": "...", "body": "...", "ctal": "...", "tags": "..."},
    }
    """
    ...

def normalize_feishu_value(val) -> str:
    """
    飞书字段值 → 字符串。
    处理 list/dict/text 等复杂类型，统一返回可读字符串。
    """
    ...

def normalize_for_frontend(normalized: dict) -> dict:
    """
    统一格式 → 前端格式（驼峰英文字段名）
    {
        "openings": [...],
        "characters": [...],
        "conflicts": [...],
        "emotions": [...],
        "quotes": [...],
        "note": {...}
    }
    """
    ...
```

### 2. 字段映射表

飞书主表字段名 → 归一化输出：

```
开篇套路类型        → openings (list[str])
女主设定/男主设定    → characters (list[str], 格式："女主：xxx")
第一/二/三层冲突     → conflicts (list[str])
情绪分析摘要        → emotions (list[str])
金句_Top5_         → quotes (list[str])
```

飞书 XHS 表 → note：

```
小红书标题模板       → note.title
正文开头模板        → note.body
互动话术模板        → note.cta
热门标签推荐        → note.tags
```

### 3. 移除分散的转换函数

- `deconstruct_worker.py` 的 `_feishu_to_analysis_format()` → 删掉，改为调用 `data_normalizer.normalize_feishu_record()`
- `deconstruct_worker.py` 的 `_feishu_val_str()` → 删掉，改为 `data_normalizer.normalize_feishu_value()`
- `task_detail_page.py` 的 `_format_characters()` / `_format_conflicts()` → 改为调用 normalizer

### 4. 修改 task_detail_page.py

```python
# 原来（多个分散函数）:
task["deconstruct_result"] = {
    "openings": deconstruct_result.get("开篇套路", []),
    "characters": _format_characters(...),
    "conflicts": _format_conflicts(...),
    ...
}

# 改为（统一入口）:
from scripts.data_normalizer import normalize_for_frontend
task["deconstruct_result"] = normalize_for_frontend(
    normalize_feishu_record(deconstruct_result, source="main")
)
```

=== **验证** ===

```bash
source .venv/bin/activate
# 单元测试
python3 -c "
from scripts.data_normalizer import normalize_feishu_record, normalize_for_frontend

# 测试1: 飞书主表字段
main = {'开篇套路类型': ['KP215','KP216'], '女主设定': [{'text':'RW178'}]}
r = normalize_feishu_record(main, 'main')
assert 'openings' in r
assert len(r['characters']) >= 1
print('✓ 测试1通过')

# 测试2: XHS表字段
xhs = {'小红书标题模板': ['测试标题'], '正文开头模板': ['正文内容']}
r2 = normalize_feishu_record(xhs, 'xhs')
assert r2.get('note',{}).get('title') == '测试标题'
print('✓ 测试2通过')

# 测试3: 前端格式
f = normalize_for_frontend(r)
assert 'openings' in f
print('✓ 测试3通过')
"

# 启动Flask验证task_detail API
curl -s http://127.0.0.1:8080/api/task/recvc2E90ge6J9 | python3 -c "
import sys,json
d=json.load(sys.stdin)
t=d.get('data',{})
assert t.get('deconstruct_result')
assert 'openings' in t['deconstruct_result']
print('✓ API集成测试通过')
"
```

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main && git pull --ff-only origin main
git checkout -b feature/data-normalizer
```

### 结束时执行

```bash
git add -A
git commit -m "feat: 数据归一化层 — data_normalizer.py 统一飞书字段转JSON格式"
git push origin feature/data-normalizer
```

=== **禁止事项** ===

- ❌ 不修改 feishu_client.py / feishu_config.py
- ❌ 不删除飞书表格任何字段
- ❌ 不改变现有 API 响应格式（前端兼容）
