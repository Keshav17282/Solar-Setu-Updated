# filename: app/__init__.py
from flask import Flask
from flask_migrate import Migrate
from sqlalchemy import inspect
from app.config import Config
from app.models import db, ensure_optional_account_schema, seed_reference_data, seed_solar_solutions


def create_app(skip_seed=False):
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    Migrate(app, db)

    with app.app_context():
        if not app.config.get("DATABASE_URL"):
            ensure_optional_account_schema()
        if not skip_seed and (not app.config.get("DATABASE_URL") or inspect(db.engine).has_table("users")):
            seed_solar_solutions()
            seed_reference_data()

    from app.routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app
