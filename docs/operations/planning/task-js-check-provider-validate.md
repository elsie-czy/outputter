## 当前线程：措施2 — JS 语法检查门禁 + 措施3 — Provider 启动校验

> 主线程下发 | 两个小措施合并一个线程 | 完成后解决"JS静默崩溃"和"Provider路由缺失"根因

---

=== **背景** ===

**问题 1**：`task_detail.js` 里一个语法错误导致整个 JS 文件无法加载，所有渲染功能同时崩溃，且无任何提示。需要加语法检查门禁。

**问题 2**：`.env` 配置了 `IMAGE_PROVIDER=siliconflow` 但 `image_provider.py` 不认识这个值，静默降级到 `MockGenerator`，生图全是占位图而没有报错。

=== **改动范围** ===

| 文件 | 变更 | 说明 |
|------|------|------|
| `scripts/web/app.py` | **修改** | `create_app()` 中增加启动时配置校验函数调用 |
| `scripts/check_js.sh` | **新建** | JS 语法检查脚本 |
| `scripts/image_provider.py` | **修改** | 未知 provider 时抛出明确错误而非静默降级 |
| `docs/planning/V2_PLAN.md` | **修改** | 更新进度 |

---

=== **技术要点** ===

### 措施 2A：JS 语法检查脚本

```bash
#!/bin/bash
# scripts/check_js.sh
# 检查所有 JS 文件语法，node 已安装在本机

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JS_DIR="$SCRIPT_DIR/static/js"
ERRORS=0

for f in "$JS_DIR"/*.js; do
  if ! node -c "$f" 2>/dev/null; then
    echo "❌ $f 语法错误"
    ((ERRORS++))
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "共 $ERRORS 个 JS 文件有语法错误，请修复后重试"
  exit 1
fi
echo "✅ 所有 JS 文件语法检查通过"
exit 0
```

### 措施 2B：启动校验

在 `scripts/web/app.py` 的 `create_app()` 末尾添加：

```python
def _validate_on_startup():
    """启动时校验关键配置"""
    import os
    # 1. 图片 Provider
    provider = os.getenv("IMAGE_PROVIDER", "").strip().lower()
    valid_providers = {"jimeng", "siliconflow", "mock"}
    if provider and provider not in valid_providers:
        print(f"[WARN] IMAGE_PROVIDER={provider} 未知，有效值: {valid_providers}，已降级为 mock")
    if not provider:
        print("[WARN] IMAGE_PROVIDER 未设置，图片生成将不可用")
    
    # 2. 模型 Provider
    model = os.getenv("MODEL_PROVIDER", "").strip().lower()
    valid_models = {"local", "openai", "chatglm", "glm", "zhipu", "qwen", "dashscope", "deepseek", "moonshot", "kimi"}
    if model and model not in valid_models:
        print(f"[WARN] MODEL_PROVIDER={model} 未知")
    
    # 3. JS 语法检查
    import subprocess
    import os as _os
    check_script = _os.path.join(_os.path.dirname(__file__), "..", "check_js.sh")
    if _os.path.exists(check_script):
        result = subprocess.run(["bash", check_script], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] JS 语法检查失败:")
            print(result.stderr.strip())
            print("[WARN] 服务已启动，但前端 JS 可能无法正常工作")

def create_app():
    ...
    _validate_on_startup()
    return legacy_app
```

### 措施 3：image_provider 未知值报错

修改 `scripts/image_provider.py` 的 `get_image_generator()` 函数：

```python
def get_image_generator() -> ImageGeneratorBase:
    provider = os.getenv("IMAGE_PROVIDER", "jimeng").strip().lower()

    if provider in ("jimeng", "siliconflow"):
        return JimengGenerator()
    elif provider == "mock":
        return MockGenerator()
    else:
        valid = "jimeng, siliconflow, mock"
        raise RuntimeError(
            f"未知的 IMAGE_PROVIDER: {provider}，有效值: {valid}。"
            f"请检查 .env 文件中的 IMAGE_PROVIDER 配置。"
        )
```

**关键变化**：原来 `else: return MockGenerator()` 静默降级，改为 `raise RuntimeError(...)` 明确报错。

---

=== **验证** ===

```bash
# 1. JS 语法检查
bash scripts/check_js.sh
# 预期: ✅ 所有 JS 文件语法检查通过

# 2. 启动 Flask 看校验输出
source .venv/bin/activate && python scripts/web_app.py
# 预期: 启动日志中看到 [WARN/INFO] 配置校验信息
# 如果有 JS 错误，会看到 [ERROR] 并提示

# 3. 测试 Provider 报错
# 临时设置 IMAGE_PROVIDER=unknown
IMAGE_PROVIDER=unknown python3 -c "
from scripts.image_provider import get_image_generator
try:
    get_image_generator()
    print('❌ 应该报错但没报')
except RuntimeError as e:
    print('✓ 正确报错:', e)
"
```

=== **分支** ===

```bash
cd /Users/lalalaba/Desktop/personal-supertool
git checkout main && git pull --ff-only origin main
git checkout -b feature/js-check-provider-validate
```

### 结束时执行

```bash
git add -A
git commit -m "feat: JS语法检查门禁 + Provider启动校验 + 未知值报错"
git push origin feature/js-check-provider-validate
```

=== **禁止事项** ===

- ❌ 不修改 .env 文件（不提交密钥）
- ❌ 不改变现有业务逻辑
- ❌ 校验仅打印警告，不阻止服务启动
