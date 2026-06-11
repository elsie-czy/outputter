from scripts.web.routes.health import bp as health_bp
from scripts.web.routes.system_api import bp as system_api_bp
from scripts.web.routes.xhs_api import bp as xhs_api_bp


def register_routes(app):
    # Idempotent register to tolerate app factory being called multiple times.
    if "web_health" not in app.blueprints:
        app.register_blueprint(health_bp)
    if "web_system_api" not in app.blueprints:
        app.register_blueprint(system_api_bp)
    if "web_xhs_api" not in app.blueprints:
        app.register_blueprint(xhs_api_bp)
