import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load(name):
    with (DATA_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _number(value, field):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} is required and must be a number.")
    if number < 0:
        raise ValueError(f"{field} cannot be negative.")
    return number


def round_to_practical_size(required_nominal_kwh, practical_sizes):
    if required_nominal_kwh <= 0:
        return 0.0
    for size in practical_sizes:
        if size >= required_nominal_kwh:
            return float(size)
    ceiling = max(practical_sizes)
    if required_nominal_kwh > ceiling:
        return float((int(required_nominal_kwh / 5) + (1 if required_nominal_kwh % 5 else 0)) * 5)
    return float(ceiling)


def recommend_battery_capacity(needs_backup=False, essential_load_kw=None,
                               backup_hours=None, technology="lfp",
                               user_selected_kwh=None, daily_consumption_kwh=None):
    if not needs_backup:
        return {
            "recommended_kwh": 0.0, "usable_requirement_kwh": 0.0,
            "nominal_requirement_kwh": 0.0, "technology": technology,
            "source": "backup_not_required", "provisional": False,
            "assumption_note": "No battery is recommended because backup is not required.",
        }

    technology_config = _load("battery_technology.json")
    normalized = str(technology or "lfp").lower().replace("_", "-")
    if normalized not in technology_config["technologies"]:
        raise ValueError("Select a supported battery technology.")
    tech = technology_config["technologies"][normalized]

    if essential_load_kw not in (None, "") and backup_hours not in (None, ""):
        load = _number(essential_load_kw, "Essential load")
        hours = _number(backup_hours, "Backup duration")
        if load == 0 or hours == 0:
            raise ValueError("Essential load and backup duration must be greater than zero when backup is required.")
        required_usable = load * hours
        source = "load_and_duration"
        provisional = False
    elif user_selected_kwh not in (None, ""):
        selected = _number(user_selected_kwh, "Selected battery capacity")
        return {
            "recommended_kwh": selected, "usable_requirement_kwh": None,
            "nominal_requirement_kwh": None, "technology": normalized,
            "source": "user_selected_legacy", "provisional": True,
            "assumption_note": "Provisional legacy selection; essential load and backup duration were not available.",
        }
    else:
        raise ValueError("Enter essential load and backup duration, or provide a provisional battery selection.")

    nominal = required_usable / (tech["depth_of_discharge"] * tech["round_trip_efficiency"])
    recommended = round_to_practical_size(nominal, tech["practical_sizes_kwh"])
    return {
        "recommended_kwh": recommended,
        "usable_requirement_kwh": round(required_usable, 2),
        "nominal_requirement_kwh": round(nominal, 2),
        "technology": normalized,
        "source": source,
        "provisional": provisional,
        "assumption_note": (
            f"Engineering assumption: {tech['label']} nominal capacity uses "
            f"{tech['depth_of_discharge']:.0%} depth of discharge and "
            f"{tech['round_trip_efficiency']:.0%} round-trip efficiency."
        ),
    }


def battery_cost(capacity_kwh, technology="lfp"):
    capacity = _number(capacity_kwh, "Battery capacity")
    if capacity == 0:
        return {
            "technology": technology, "capacity_kwh": 0,
            "minimum_cost": 0, "maximum_cost": 0, "estimated_cost": 0,
            "market_estimate": False, "vendor_quote_required": False,
        }
    config = _load("battery_pricing.json")["technologies"]
    normalized = str(technology or "lfp").lower().replace("_", "-")
    pricing = config.get(normalized)
    if not pricing or pricing["minimum_per_kwh"] is None or pricing["maximum_per_kwh"] is None:
        return {
            "technology": normalized, "capacity_kwh": capacity,
            "minimum_cost": None, "maximum_cost": None, "estimated_cost": None,
            "market_estimate": False, "vendor_quote_required": True,
        }
    minimum = round(capacity * pricing["minimum_per_kwh"], 2)
    maximum = round(capacity * pricing["maximum_per_kwh"], 2)
    return {
        "technology": normalized, "capacity_kwh": capacity,
        "minimum_cost": minimum, "maximum_cost": maximum,
        "estimated_cost": round((minimum + maximum) / 2, 2),
        "market_estimate": True, "vendor_quote_required": False,
        "pricing_basis": "Installed residential market estimate; not an official government rate.",
    }
