from scripts.web.routes import register_routes
from scripts.web_app_legacy import app as legacy_app


def create_app():
    # Keep legacy handlers mounted while we gradually migrate routes/services/templates.
    register_routes(legacy_app)
    return legacy_app
