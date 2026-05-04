from pathlib import Path

from flask import Flask

from gui.backend.http.routes_connection import bp as connection_bp
from gui.backend.http.routes_control import bp as control_bp
from gui.backend.http.routes_data import bp as data_bp
from gui.backend.http.routes_model import bp as model_bp
from gui.backend.http.routes_monitoring import bp as monitoring_bp
from gui.backend.http.routes_pages import bp as pages_bp

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def create_app() -> Flask:
    app = Flask(__name__, template_folder=BASE_DIR / "templates", static_folder=BASE_DIR / "static")
    app.register_blueprint(pages_bp)
    for blueprint in (connection_bp, control_bp, data_bp, model_bp, monitoring_bp):
        app.register_blueprint(blueprint, url_prefix="/api")
    return app
