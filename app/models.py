# filename: app/models.py
from datetime import datetime
import math
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def ensure_optional_account_schema():
    """Create account tables and add nullable ownership to older SQLite DBs."""
    from sqlalchemy import inspect, text

    db.create_all()
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("user_locations")}
    if "user_id" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE user_locations ADD COLUMN user_id INTEGER"))
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "settings" not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN settings JSON"))


class UserLocation(db.Model):
    """Stores a single rooftop estimation run: the address, the drawn
    polygon, and the resulting solar estimate."""

    __tablename__ = "user_locations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    address = db.Column(db.String(512), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    # GeoJSON polygon of the drawn rooftop, stored as JSON text (SQLite has
    # no native JSON type, SQLAlchemy's JSON type handles serialization).
    polygon_geojson = db.Column(db.JSON, nullable=True)
    # List of non-usable patches (water tanks, staircase rooms, AC units,
    # existing coverings) drawn inside the rooftop boundary, each a GeoJSON
    # polygon. Subtracted from roof_area_sqm to get usable_area_sqm.
    obstructions_geojson = db.Column(db.JSON, nullable=True)

    system_size = db.Column(db.Float, nullable=False, default=0.0)       # kWp
    annual_generation = db.Column(db.Float, nullable=False, default=0.0)  # kWh/year
    monthly_data = db.Column(db.JSON, nullable=True)                     # {"Jan": kWh, ...}

    # Cached financial figures so the report/PDF can be regenerated without
    # recomputation.
    roof_area_sqm = db.Column(db.Float, nullable=True)          # gross rooftop area
    obstructed_area_sqm = db.Column(db.Float, nullable=True)    # non-usable area subtracted
    usable_area_sqm = db.Column(db.Float, nullable=True)        # roof_area_sqm - obstructed_area_sqm
    system_cost = db.Column(db.Float, nullable=True)
    subsidy_amount = db.Column(db.Float, nullable=True)
    net_investment = db.Column(db.Float, nullable=True)
    monthly_savings = db.Column(db.Float, nullable=True)
    co2_reduction_tons = db.Column(db.Float, nullable=True)
    irradiance_source = db.Column(db.String(32), nullable=True)  # nasa_power / pvgis / mock_fallback

    # Orientation & battery
    orientation_deg = db.Column(db.Float, nullable=True)
    orientation_label = db.Column(db.String(32), nullable=True)
    orientation_factor = db.Column(db.Float, nullable=True)
    recommended_tilt_deg = db.Column(db.Float, nullable=True)
    battery_kwh = db.Column(db.Float, nullable=True, default=0.0)
    battery_cost = db.Column(db.Float, nullable=True, default=0.0)

    # Extra performance metrics (cached for report/PDF)
    specific_yield = db.Column(db.Float, nullable=True)       # kWh/kWp/year
    capacity_factor = db.Column(db.Float, nullable=True)      # %
    lcoe = db.Column(db.Float, nullable=True)                 # ₹/kWh
    lifetime_kwh = db.Column(db.Float, nullable=True)
    self_consumption_frac = db.Column(db.Float, nullable=True)
    payback_years = db.Column(db.Float, nullable=True)
    # Flexible bag for any extra numbers / labels
    extras = db.Column(db.JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        annual_generation = self.annual_generation
        if isinstance(annual_generation, bool):
            annual_generation = None
        else:
            try:
                annual_generation = float(annual_generation)
            except (OverflowError, TypeError, ValueError):
                annual_generation = None
            if (
                annual_generation is not None
                and (not math.isfinite(annual_generation) or annual_generation < 0)
            ):
                annual_generation = None

        from app.solar_logic import (
            calculate_co2_avoided_tonnes,
            normalize_annual_generation_kwh,
        )

        annual_generation = normalize_annual_generation_kwh(self.annual_generation)

        return {
            "id": self.id,
            "user_id": self.user_id,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "polygon_geojson": self.polygon_geojson,
            "obstructions_geojson": self.obstructions_geojson,
            "system_size": round(self.system_size, 2),
            "annual_generation": round(annual_generation, 2) if annual_generation is not None else None,
            "monthly_data": self.monthly_data,
            "roof_area_sqm": round(self.roof_area_sqm or 0, 2),
            "obstructed_area_sqm": round(self.obstructed_area_sqm or 0, 2),
            "usable_area_sqm": round(self.usable_area_sqm or (self.roof_area_sqm or 0), 2),
            "system_cost": round(self.system_cost or 0, 2),
            "subsidy_amount": round(self.subsidy_amount or 0, 2),
            "net_investment": round(self.net_investment or 0, 2),
            "monthly_savings": round(self.monthly_savings or 0, 2),
            "co2_reduction_tons": calculate_co2_avoided_tonnes(annual_generation),
            "irradiance_source": self.irradiance_source,
            "orientation_deg": self.orientation_deg,
            "orientation_label": self.orientation_label,
            "orientation_factor": self.orientation_factor,
            "recommended_tilt_deg": self.recommended_tilt_deg,
            "battery_kwh": self.battery_kwh or 0,
            "battery_cost": round(self.battery_cost or 0, 2),
            "specific_yield": self.specific_yield,
            "capacity_factor": self.capacity_factor,
            "lcoe": self.lcoe,
            "lifetime_kwh": self.lifetime_kwh,
            "self_consumption_frac": self.self_consumption_frac,
            "payback_years": self.payback_years,
            "extras": self.extras,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(db.Model):
    """Optional account owner for saved solar assessments."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(320), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    settings = db.Column(db.JSON, nullable=True, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    locations = db.relationship("UserLocation", backref="owner", lazy=True)


class SolarProvider(db.Model):
    __tablename__ = "solar_providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    website = db.Column(db.String(512), nullable=True)
    service_regions = db.Column(db.JSON, nullable=False, default=list)
    provider_type = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    solutions = db.relationship("SolarSolution", backref="provider", lazy=True, cascade="all, delete-orphan")


class SolarSolution(db.Model):
    __tablename__ = "solar_solutions"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("solar_providers.id"), nullable=False, index=True)
    system_size_kw = db.Column(db.Float, nullable=False)
    panel_brand = db.Column(db.String(120), nullable=True)
    panel_model = db.Column(db.String(160), nullable=True)
    panel_type = db.Column(db.String(80), nullable=True)
    panel_efficiency = db.Column(db.Float, nullable=True)
    number_of_panels = db.Column(db.Integer, nullable=True)
    inverter_brand = db.Column(db.String(120), nullable=True)
    inverter_model = db.Column(db.String(160), nullable=True)
    inverter_type = db.Column(db.String(80), nullable=True)
    panel_warranty_years = db.Column(db.Float, nullable=True)
    performance_warranty_years = db.Column(db.Float, nullable=True)
    inverter_warranty_years = db.Column(db.Float, nullable=True)
    installation_included = db.Column(db.Boolean, nullable=True)
    mounting_included = db.Column(db.Boolean, nullable=True)
    amc_available = db.Column(db.Boolean, nullable=True)
    financing_available = db.Column(db.Boolean, nullable=True)
    indicative_price_min = db.Column(db.Float, nullable=True)
    indicative_price_max = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(8), nullable=False, default="INR")
    data_status = db.Column(db.String(24), nullable=False, default="INDICATIVE")
    source = db.Column(db.String(512), nullable=False)
    last_updated = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class SavedComparison(db.Model):
    __tablename__ = "saved_comparisons"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("user_locations.id"), nullable=True)
    solution_ids = db.Column(db.JSON, nullable=False, default=list)
    priority = db.Column(db.String(40), nullable=False, default="overall")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def seed_solar_solutions():
    """Seed a small, replaceable prototype catalogue with honest provenance."""
    if SolarProvider.query.count() or SolarSolution.query.count():
        return
    from datetime import date

    records = [
        ("SunGrid India", "Indicative residential rooftop package catalogue for prototype comparison.", ["Delhi", "Haryana", "Punjab", "Rajasthan", "Uttar Pradesh"], "EPC", 5.0, "Waaree", "540 W module", "Mono PERC", 20.5, 10, "Solis", "S5-GR3P", "String", 12, 25, 10, True, True, True, True, 285000, 335000),
        ("HelioWorks", "Indicative rooftop package catalogue; verify serviceability before procurement.", ["Delhi", "Maharashtra", "Gujarat", "Karnataka", "Tamil Nadu"], "Installer network", 5.5, "Adani Solar", "TOPCon 550 W", "TOPCon", 22.1, 10, "GoodWe", "XS", "String", 12, 30, 10, True, True, True, True, 315000, 375000),
        ("BrightRoof Energy", "Indicative solution record for an India-wide availability check.", [], "Marketplace listing", 6.0, "Vikram Solar", "Suryavajra 550 W", "Mono PERC", 21.3, 11, "Growatt", "MIN 6000TL", "String", 12, 25, 10, None, None, True, False, 300000, 360000),
    ]
    for name, description, regions, provider_type, size, brand, model, panel_type, efficiency, panels, inverter_brand, inverter_model, inverter_type, panel_warranty, performance_warranty, inverter_warranty, installation, mounting, amc, financing, price_min, price_max in records:
        provider = SolarProvider(name=name, description=description, service_regions=regions, provider_type=provider_type)
        provider.solutions.append(SolarSolution(
            system_size_kw=size, panel_brand=brand, panel_model=model, panel_type=panel_type,
            panel_efficiency=efficiency, number_of_panels=panels, inverter_brand=inverter_brand,
            inverter_model=inverter_model, inverter_type=inverter_type,
            panel_warranty_years=panel_warranty, performance_warranty_years=performance_warranty,
            inverter_warranty_years=inverter_warranty, installation_included=installation,
            mounting_included=mounting, amc_available=amc, financing_available=financing,
            indicative_price_min=price_min, indicative_price_max=price_max, data_status="INDICATIVE",
            source="Solar Setu SIH prototype catalogue (manually curated; provider verification required)",
            last_updated=date(2026, 9, 1),
        ))
        db.session.add(provider)
    db.session.commit()


def seed_reference_data():
    """Populate the prototype tariff and subsidy reference data once."""
    if TariffTable.query.count() == 0:
        db.session.add_all([
            TariffTable(state="Delhi", utility_name="BSES Rajdhani", rate_per_kwh=10.0),
            TariffTable(state="Uttar Pradesh", utility_name="UPPCL", rate_per_kwh=6.5),
            TariffTable(state="Maharashtra", utility_name="MSEDCL", rate_per_kwh=8.2),
            TariffTable(state="Karnataka", utility_name="BESCOM", rate_per_kwh=7.8),
            TariffTable(state="Tamil Nadu", utility_name="TANGEDCO", rate_per_kwh=6.9),
            TariffTable(state="Gujarat", utility_name="UGVCL", rate_per_kwh=9.5),
            TariffTable(state="West Bengal", utility_name="WBSEDCL", rate_per_kwh=9.8),
            TariffTable(state="Rajasthan", utility_name="JVVNL", rate_per_kwh=9.5),
        ])

    if SubsidyScheme.query.count() == 0:
        db.session.add_all([
            SubsidyScheme(min_kw=0, max_kw=2, subsidy_amount=60000),
            SubsidyScheme(min_kw=2, max_kw=3, subsidy_amount=78000),
            SubsidyScheme(min_kw=3, max_kw=1000, subsidy_amount=78000),
        ])

    db.session.commit()


class TariffTable(db.Model):
    """Per-state / per-utility electricity tariff, used to convert kWh
    generated into ₹ savings."""

    __tablename__ = "tariff_table"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(128), nullable=False)
    utility_name = db.Column(db.String(128), nullable=False)
    rate_per_kwh = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "state": self.state,
            "utility_name": self.utility_name,
            "rate_per_kwh": self.rate_per_kwh,
        }


class SubsidyScheme(db.Model):
    """PM Surya Ghar subsidy slabs, keyed by system size range (kW)."""

    __tablename__ = "subsidy_scheme"

    id = db.Column(db.Integer, primary_key=True)
    min_kw = db.Column(db.Float, nullable=False)
    max_kw = db.Column(db.Float, nullable=False)
    subsidy_amount = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "min_kw": self.min_kw,
            "max_kw": self.max_kw,
            "subsidy_amount": self.subsidy_amount,
        }
