from scripts.web.routes.health import bp as health_bp
from scripts.web.routes.system_api import bp as system_api_bp
from scripts.web.routes.xhs_api import bp as xhs_api_bp
from scripts.web.routes.landing_page import bp as landing_bp
from scripts.web.routes.deconstruct_api import bp as deconstruct_api_bp
from scripts.web.routes.reference_api import bp as reference_api_bp
from scripts.web.routes.note_api import bp as note_api_bp
from scripts.web.routes.image_api import bp as image_api_bp
from scripts.web.routes.topic_pool_page import bp as topic_pool_bp
from scripts.web.routes.production_center_page import bp as production_center_bp
from scripts.web.routes.task_detail_page import bp as task_detail_bp


def register_routes(app):
    # Idempotent register to tolerate app factory being called multiple times.
    if "web_health" not in app.blueprints:
        app.register_blueprint(health_bp)
    if "web_system_api" not in app.blueprints:
        app.register_blueprint(system_api_bp)
    if "web_xhs_api" not in app.blueprints:
        app.register_blueprint(xhs_api_bp)
    if "web_landing" not in app.blueprints:
        app.register_blueprint(landing_bp)
    if "web_deconstruct_api" not in app.blueprints:
        app.register_blueprint(deconstruct_api_bp)
    if "web_reference_api" not in app.blueprints:
        app.register_blueprint(reference_api_bp)
    if "web_note_api" not in app.blueprints:
        app.register_blueprint(note_api_bp)
    if "web_image_api" not in app.blueprints:
        app.register_blueprint(image_api_bp)
    if "web_topic_pool" not in app.blueprints:
        app.register_blueprint(topic_pool_bp)
    if "web_production_center" not in app.blueprints:
        app.register_blueprint(production_center_bp)
    if "web_task_detail" not in app.blueprints:
        app.register_blueprint(task_detail_bp)
