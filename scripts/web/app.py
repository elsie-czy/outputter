from scripts.web.routes import register_routes
from scripts.web_app_legacy import app as legacy_app
import os
import subprocess


def _validate_on_startup():
    """启动时校验关键配置"""
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
    check_script = os.path.join(os.path.dirname(__file__), "..", "check_js.sh")
    if os.path.exists(check_script):
        result = subprocess.run(["bash", check_script], capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] JS 语法检查失败:")
            print(result.stderr.strip())
            print("[WARN] 服务已启动，但前端 JS 可能无法正常工作")


def create_app():
    # 配置 V2 模板目录和静态资源目录
    base = os.path.dirname(__file__)
    legacy_app.template_folder = os.path.join(base, "templates")
    legacy_app.static_folder = os.path.join(base, "..", "static")
    legacy_app.static_url_path = "/static"

    register_routes(legacy_app)
    _validate_on_startup()
    return legacy_app
