# Solar Setu

Solar Setu is a Flask rooftop solar estimator with optional accounts, saved reports, provider comparisons, Surya AI, and PDF reports.

## Environment

Copy `.env.example` to `.env` for local development. Use deployment-platform environment variables in production. Never commit `.env`.

Required or supported variables:

```text
DATABASE_URL=postgresql://username:password@host:5432/database_name
SECRET_KEY=replace_with_a_long_random_value
GEMINI_API_KEY=replace_with_your_gemini_api_key
AI_PROVIDER=gemini
AI_MODEL=gemini-2.0-flash
```

`AI_API_URL` is optional for an OpenAI-compatible provider. The application does not store AI credentials in the database.

For local development without PostgreSQL, omit `DATABASE_URL`; the app uses the existing `solar_app.db` SQLite file. That fallback is not suitable for production.

## Local setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Open `http://127.0.0.1:5000`. The `/health` endpoint returns `{"status":"ok"}` when the database connection is available.

## PostgreSQL setup

Install PostgreSQL locally or create a managed PostgreSQL database. Create a database, then set `DATABASE_URL` to its connection URL. Do not put credentials in source code.

Apply the schema with Flask-Migrate:

```powershell
$env:DATABASE_URL = "postgresql://username:password@localhost:5432/solar_setu"
flask --app run:app db upgrade
```

For future model changes, review the generated migration before applying it:

```powershell
flask --app run:app db migrate -m "describe the schema change"
flask --app run:app db upgrade
```

The first migration creates `users`, `user_locations`, `saved_comparisons`, `solar_providers`, `solar_solutions`, `tariff_table`, and `subsidy_scheme`. Reference catalogue data is seeded after the schema exists.

## Import existing SQLite data

Keep `solar_app.db` as a backup. Do not open it for writing during migration. Create the PostgreSQL schema first, then run:

```powershell
$env:DATABASE_URL = "postgresql://username:password@host:5432/solar_setu"
flask --app run:app db upgrade
python -m scripts.migrate_sqlite_to_postgres --sqlite solar_app.db
```

The importer preserves IDs and JSON values, inserts parent rows before child rows, repairs PostgreSQL ID sequences, checks all important table counts, and checks report/user and solution/provider relationships. It aborts on a mismatch and never deletes or modifies the SQLite source.

## Production

The included Docker image installs WeasyPrint's native libraries, applies migrations, and starts Gunicorn:

```text
flask --app run:app db upgrade && gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 run:app
```

Set these deployment variables:

```text
DATABASE_URL=<managed PostgreSQL URL>
SECRET_KEY=<strong random secret>
GEMINI_API_KEY=<rotated Gemini key>
AI_PROVIDER=gemini
AI_MODEL=gemini-2.0-flash
```

For Render, choose a Docker Web Service. The Dockerfile uses the platform's `PORT` value automatically. Configure `/health` as the health-check path when the platform supports it.
