from __future__ import annotations
from flask import Flask

from .dashboard import bp as dashboard_bp
from .companies import bp as companies_bp
from .chains import bp as chains_bp
from .stores import bp as stores_bp
from .ops import bp as ops_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(companies_bp)
    app.register_blueprint(chains_bp)
    app.register_blueprint(stores_bp)
    app.register_blueprint(ops_bp)
    return app

