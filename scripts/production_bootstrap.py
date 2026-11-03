"""Run production migrations and verify required tables before Gunicorn starts."""

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

# When this file is launched as "python scripts/production_bootstrap.py",
# Python puts scripts/ (not the repository root) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from flask_migrate import stamp, upgrade

from app import create_app
from app.models import db, seed_application_reference_data


REQUIRED_TABLES = {
    "users",
    "user_locations",
    "solar_providers",
    "solar_solutions",
    "saved_comparisons",
    "tariff_table",
    "subsidy_scheme",
    "solar_companies",
    "company_service_areas",
    "company_products",
    "company_verifications",
    "quotation_requests",
}


def database_label(database_url):
    parsed = urlsplit(database_url)
    return f"{parsed.scheme}://{parsed.hostname or 'unknown'}/{parsed.path.lstrip('/') or 'database'}"


def stamp_legacy_schema(app, db, directory):
    """Mark an already-created Solar Setu schema at 0001 without changing it."""
    table_names = set(inspect(db.engine).get_table_names())
    if "users" not in table_names or "user_locations" not in table_names:
        return False

    if "alembic_version" in table_names:
        with db.engine.connect() as connection:
            versions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if versions:
            return False

    stamp(directory=directory, revision="0001_initial_schema")
    print("Preserved existing application tables; stamped legacy schema at 0001_initial_schema.")
    return True


def main():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required in production.")
    if database_url.startswith("sqlite:") or database_url.startswith("sqlite:///"):
        raise SystemExit("SQLite is not supported for production startup.")

    app = create_app(skip_seed=True)
    with app.app_context():
        stamp_legacy_schema(app, db, "migrations")
        upgrade(directory="migrations")
        tables = set(inspect(db.engine).get_table_names())
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise SystemExit(
                f"Database migration verification failed. Missing tables: {', '.join(missing)}"
            )
        seed_application_reference_data()
        print(f"Database migration verified: {database_label(database_url)}")
        print(f"Verified application tables: {len(REQUIRED_TABLES)}")

    port = os.environ.get("PORT", "5000").strip() or "5000"
    gunicorn_args = [
        "gunicorn",
        "--bind",
        f"0.0.0.0:{port}",
        "--workers",
        "2",
        "--timeout",
        "120",
        "--worker-class",
        "sync",
        "wsgi:app",
    ]
    print(f"Starting Gunicorn on 0.0.0.0:{port}")
    os.execvp("gunicorn", gunicorn_args)


if __name__ == "__main__":
    main()
