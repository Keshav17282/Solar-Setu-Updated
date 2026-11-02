import json
import re
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "subsidy_rates.json"
MAX_CAPACITY_KW = 10


def _config():
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def central_subsidy(capacity_kw):
    config = _config()["scheme"]["central"]
    capacity = float(capacity_kw)
    first_band = min(max(capacity, 0), config["first_band_kw"]) * config["first_band_rate"]
    second_band = min(max(capacity - config["first_band_kw"], 0), config["second_band_kw"]) * config["second_band_rate"]
    return round(min(first_band + second_band, config["maximum"]), 2)


def detect_state(location_text):
    text = str(location_text or "").strip().lower()
    if not text:
        return None
    if (
        re.search(r"\b(uttar\s+pradesh|uttarpradesh|u\.?p\.?|modinagar)\b", text)
        or text == "up"
    ):
        return "Uttar Pradesh"
    return None


def state_subsidy(state, capacity_kw):
    config = _config()
    provision = config["states"].get(state)
    if not provision:
        return 0.0
    capacity = max(float(capacity_kw), 0)
    amount = capacity * provision["additional_rate_per_kw"]
    return round(min(amount, provision["maximum"]), 2)


def grid_connected_from_configuration(configuration, grid_connected=None, saved_inverter=None):
    if grid_connected is not None:
        return bool(grid_connected)
    normalized = str(configuration or "").strip().lower().replace("_", "-")
    inverter_text = str(saved_inverter or "").lower()
    if normalized in ("on-grid", "ongrid", "grid-connected", "grid tied"):
        return True
    if normalized == "hybrid":
        return "grid" in inverter_text or "hybrid" in inverter_text
    return False


def calculate_subsidy(state, capacity_kw, category="residential", configuration="on-grid",
                      grid_connected=None, saved_inverter=None):
    try:
        capacity = float(capacity_kw)
    except (TypeError, ValueError):
        raise ValueError("Enter a valid system capacity.")
    if capacity < 0:
        raise ValueError("System capacity cannot be negative.")
    if capacity == 0 or capacity > MAX_CAPACITY_KW:
        raise ValueError("System capacity must be greater than 0 and no more than 10 kW.")

    config = _config()
    category = str(category or "").strip().lower()
    configuration = str(configuration or "").strip().lower()
    normalized_state = detect_state(state) if state else None
    normalized_state = normalized_state or str(state or "").strip()
    central = central_subsidy(capacity)
    up_additional = state_subsidy(normalized_state, capacity) if normalized_state == "Uttar Pradesh" else 0.0
    has_grid_connection = grid_connected_from_configuration(configuration, grid_connected, saved_inverter)

    eligible = (
        bool(str(state or "").strip())
        and category in ("residential", "residential grid-connected")
        and configuration in ("on-grid", "grid-connected", "ongrid", "hybrid")
        and has_grid_connection
    )
    if not str(state or "").strip() or not category or not configuration:
        status = "Verify eligibility on the official portal"
        explanation = "Location, property category and grid configuration are required before subsidy eligibility can be established."
    elif category not in ("residential", "residential grid-connected"):
        status = "Not eligible for residential CFA"
        explanation = "The residential PM Surya Ghar CFA is not intended for commercial or industrial systems. Verify other official schemes separately."
    elif configuration == "off-grid" or configuration in ("offgrid", "off-grid system"):
        status = "Verify eligibility on the official portal"
        explanation = "Off-grid systems are not automatically treated as eligible for PM Surya Ghar residential CFA."
    elif configuration == "hybrid" and not has_grid_connection:
        status = "Verify eligibility on the official portal"
        explanation = "A hybrid configuration does not automatically establish residential CFA eligibility. Check the latest official rules."
    elif not eligible:
        status = "Verify eligibility on the official portal"
        explanation = "Confirm the system category and configuration with the national portal, DISCOM and approved vendor."
    else:
        status = "Indicative central eligibility"
        explanation = "Residential grid-connected systems may qualify for central CFA, subject to official approval."

    final_estimate = central + up_additional if eligible else 0.0
    return {
        "capacity_kw": capacity,
        "central_subsidy": central,
        "state_additional_subsidy": up_additional,
        "indicative_combined_subsidy": central + up_additional,
        "final_estimated_subsidy": final_estimate,
        "eligible": eligible,
        "eligibility_status": status,
        "explanation": explanation,
        "up_warning": state == "Uttar Pradesh",
        "warning": (
            "Additional Uttar Pradesh subsidy — subject to current scheme availability, eligibility, allocation and official verification."
            if state == "Uttar Pradesh" else
            "State benefits are not included unless officially verified for this Solar Setu guide. Verify separately with your state authority."
        )
    }


def enrich_saved_report_financials(report_data):
    """Recalculate persisted subsidy-dependent report totals from saved inputs."""
    data = dict(report_data or {})
    extras = data.get("extras") or {}
    category = extras.get("property_type") or data.get("property_type")
    configuration = extras.get("inverter_type") or data.get("inverter_type")
    inverter = extras.get("inverter") or data.get("inverter")
    saved_inverter_text = " ".join(str(value) for value in (
        inverter.get("type") if isinstance(inverter, dict) else inverter,
        inverter.get("best_for") if isinstance(inverter, dict) else "",
        " ".join(inverter.get("advantages", [])) if isinstance(inverter, dict) else "",
    ))

    try:
        result = calculate_subsidy(
            data.get("address"),
            data.get("system_size"),
            category or "residential",
            configuration or "on-grid",
            saved_inverter=saved_inverter_text,
        )
    except ValueError:
        result = {
            "central_subsidy": 0.0,
            "state_additional_subsidy": 0.0,
            "indicative_combined_subsidy": 0.0,
            "final_estimated_subsidy": 0.0,
            "eligible": False,
            "eligibility_status": "Eligibility requires verification",
            "explanation": "Required report inputs are missing or invalid.",
            "warning": "Subsidy eligibility requires verification on the official portal.",
        }

    gross_investment = float(data.get("system_cost") or 0) + float(data.get("battery_cost") or 0)
    total_subsidy = float(result["final_estimated_subsidy"])
    net_investment = round(max(gross_investment - total_subsidy, 0), 2)
    annual_savings = float(data.get("monthly_savings") or 0) * 12

    data.update({
        "subsidy_state": detect_state(data.get("address")),
        "central_subsidy_amount": result["central_subsidy"] if result["eligible"] else 0.0,
        "state_subsidy_amount": result["state_additional_subsidy"] if result["eligible"] else 0.0,
        "total_estimated_subsidy": total_subsidy,
        "subsidy_amount": total_subsidy,
        "subsidy_eligibility_status": result["eligibility_status"],
        "subsidy_explanation": result["explanation"],
        "subsidy_warning": result["warning"],
        "net_investment": net_investment,
    })
    if annual_savings > 0:
        data["payback_years"] = round(net_investment / annual_savings, 1)
    return data
