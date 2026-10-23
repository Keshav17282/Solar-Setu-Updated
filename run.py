# filename: run.py
"""
Entry point: creates the Flask app, initializes the database (creating
tables if they don't exist), seeds mock tariff/subsidy reference data if
empty, and runs the dev server.
"""
from app import create_app
from app.models import db, ensure_optional_account_schema

app = create_app()


if __name__ == "__main__":
    with app.app_context():
        ensure_optional_account_schema()

    # A single process keeps the local demo server reachable from VS Code and
    # avoids the debug reloader starting a child process with a stale state.
    app.run(debug=False, use_reloader=False, host="127.0.0.1", port=5000)

