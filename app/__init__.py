# filename: app/__init__.py
from flask import Flask
from flask_migrate import Migrate
from sqlalchemy import inspect
from app.config import Config
from app.models import db, ensure_optional_account_schema, seed_reference_data, seed_solar_solutions, seed_real_installers
from app.security import validate_csrf_request


def create_app(skip_seed=False):
    app = Flask(__name__)
    app.config.from_object(Config)
    app.before_request(validate_csrf_request)

    db.init_app(app)
    Migrate(app, db)

    with app.app_context():
        if not app.config.get("DATABASE_URL"):
            ensure_optional_account_schema()
        tables = set(inspect(db.engine).get_table_names())
        marketplace_tables_ready = {
            "solar_companies",
            "company_service_areas",
            "company_products",
            "company_verifications",
            "quotation_requests",
        }.issubset(tables)
        core_tables_ready = "users" in tables and "user_locations" in tables
        if (
            not skip_seed
            and core_tables_ready
            and marketplace_tables_ready
            and (not app.config.get("DATABASE_URL") or "users" in tables)
        ):
            seed_solar_solutions()
            seed_real_installers()
            seed_reference_data()

    from app.routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    return app
