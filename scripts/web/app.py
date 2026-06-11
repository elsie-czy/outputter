from scripts.web.routes import register_routes
from scripts.web_app_legacy import app as legacy_app
import os


def create_app():
    # 配置 V2 模板目录和静态资源目录
    base = os.path.dirname(__file__)
    legacy_app.template_folder = os.path.join(base, "templates")
    legacy_app.static_folder = os.path.join(base, "..", "static")
    legacy_app.static_url_path = "/static"

    register_routes(legacy_app)
    return legacy_app
