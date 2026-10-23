# filename: app/config.py
import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    """Base configuration. Structured so swapping SQLite -> PostgreSQL is a
    one-line change (just set SQLALCHEMY_DATABASE_URI via env var in prod)."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # Prototype uses SQLite. For PostgreSQL in production, set DATABASE_URL, e.g.
    # postgresql+psycopg2://user:password@host:5432/solar_db
    DATABASE_URL = os.environ.get("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    elif DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_DATABASE_URI = DATABASE_URL or f"sqlite:///{os.path.join(BASE_DIR, 'solar_app.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }

    # External API endpoints
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
    PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc"
    NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"

    # Domain constants — aligned with India PV planning guide (Aug 2026)
    SQM_PER_KWP = 10.0          # ~1 kWp per 10 m² usable shadow-free roof
    # Illustrative CEA CO2 Baseline Database Version 22.0 (Excel database),
    # financial year 2025–26; grid-average factor in tCO2/MWh.
    # Not a certified rooftop-solar methodology or guaranteed carbon-credit factor.
    GRID_EMISSION_FACTOR_TCO2_PER_MWH = 0.8226
    # Residential installed cost band ~₹55k–85k/kW; use mid for estimates
    SYSTEM_COST_PER_KW = 65000
    SYSTEM_COST_PER_KW_LOW = 55000
    SYSTEM_COST_PER_KW_HIGH = 85000
    # Commercial EPC often ~₹35k–50k/kW at larger scale
    COMMERCIAL_COST_PER_KW = 42000
    BATTERY_COST_PER_KWH = 9000  # residential LFP planning figure

    # Energy: ~4–5.5 units/day per kWp on suitable days; PR 0.75–0.85
    DEFAULT_TARIFF = 10.0
    DAILY_UNITS_PER_KW_LOW = 4.0
    DAILY_UNITS_PER_KW_HIGH = 5.5
    MONTHLY_UNITS_PER_KW = 135.0      # ~4.5 units/day × 30
    ANNUAL_UNITS_PER_KW = 135.0 * 12  # ~1620 kWh/kWp/year
    DEFAULT_PERFORMANCE_RATIO = 0.80
    DEFAULT_PEAK_SUN_HOURS = 5.0

    # PM Surya Ghar central assistance (published structure):
    # ₹30,000/kW for first 2 kW; ₹18,000 for the additional kW from 2–3 kW; max ₹78,000
    SUBSIDY_PER_KW_FIRST_2 = 30000.0
    SUBSIDY_EXTRA_2_TO_3 = 18000.0
    SUBSIDY_CAP = 78000.0

    # Battery preliminary: nominal kWh = critical_kWh / (DoD × RTE)
    BATTERY_DEFAULT_DOD = 0.80
    BATTERY_DEFAULT_RTE = 0.90

    # O&M planning reserve (~1–1.5% of system cost / year typical)
    OM_PERCENT_PER_YEAR = 0.012

    REQUEST_TIMEOUT = 6  # seconds, before falling back to mock data
