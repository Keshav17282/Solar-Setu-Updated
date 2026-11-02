# filename: app/routes.py
import math
import re
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, jsonify, send_file, abort, redirect, url_for, session
from werkzeug.exceptions import HTTPException
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash
import requests

from app.config import Config
from app.models import (
    db, User, UserLocation, TariffTable, SubsidyScheme, SolarSolution, SavedComparison,
    SolarCompany, QuotationRequest,
)
from app.solar_logic import (
    run_full_estimation,
    calculate_co2_avoided_tonnes,
    calculate_environmental_equivalents,
    get_grid_emission_factor_tco2_per_mwh,
    normalize_annual_generation_kwh,
)
from app.carbon_calculator import calculate_carbon_impact
from app.report_generator import generate_pdf_report
from app.services.solar_assistant import ask_surya
from app.security import get_csrf_token, regenerate_csrf_token
from app.services.compare_service import serialize_solution, PRIORITY_LABELS
from app.services.subsidy_service import calculate_subsidy, central_subsidy, state_subsidy

bp = Blueprint("routes", __name__)


@bp.get("/health")
def health():
    """Minimal platform health check without exposing connection details."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok"})
    except Exception:
        db.session.rollback()
        return jsonify({"status": "error"}), 503


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def _safe_next(value):
    if not value:
        return None
    parsed = urlparse(value)
    return value if not parsed.scheme and not parsed.netloc and value.startswith("/") else None


def _coerce_float(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else default
    text = str(value).strip()
    if not text:
        return default
    text = text.replace("₹", "").replace(",", "").replace(" ", "")
    if text.endswith("/kWh"):
        text = text[:-4]
    try:
        numeric = float(text)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _sanitize_json_value(value):
    if isinstance(value, dict):
        return {str(k): _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return value


def _authorized_location(location):
    user = current_user()
    if location.user_id is not None and (not user or location.user_id != user.id):
        abort(403)
    return location


def _complete_pending_save(user):
    location_id = session.pop("pending_save_location_id", None)
    if not location_id:
        return None
    location = db.session.get(UserLocation, location_id)
    if not location or location.user_id not in (None, user.id):
        return None
    location.user_id = user.id
    db.session.commit()
    return location.id


@bp.app_context_processor
def account_context():
    return {
        "current_user": current_user(),
        "csrf_token": get_csrf_token(),
    }


@bp.app_errorhandler(Exception)
def handle_api_exception(error):
    if not request.path.startswith("/api/"):
        if isinstance(error, HTTPException):
            return error
        raise error
    if hasattr(error, "code") and error.code is not None:
        status = error.code
        message = getattr(error, "description", None) or error.name
    else:
        status = 500
        message = "Server error while processing your request."
    return jsonify({"error": message}), status


# ---------------------------------------------------------------- Pages ----

@bp.route("/")
def index():
    user = current_user()
    preferences = dict((user.settings if user else session.get("solar_preferences")) or {})
    return render_template(
        "index.html",
        preferences=preferences,
        grid_emission_factor_tco2_per_mwh=get_grid_emission_factor_tco2_per_mwh(),
    )


@bp.route("/dashboard")
def dashboard():
    user = current_user()
    if user:
        recent = UserLocation.query.filter_by(user_id=user.id).order_by(UserLocation.created_at.desc()).limit(10).all()
    else:
        recent = UserLocation.query.order_by(UserLocation.created_at.desc()).limit(10).all()
    return render_template("dashboard.html", locations=recent)


@bp.route("/profile")
def profile():
    user = current_user()
    if not user:
        return redirect(url_for("routes.login", next=request.path))
    report_count = UserLocation.query.filter_by(user_id=user.id).count()
    return render_template("profile.html", report_count=report_count)


def _account_reports():
    user = current_user()
    if user:
        return UserLocation.query.filter_by(user_id=user.id).order_by(UserLocation.created_at.desc()).all()
    guest_ids = session.get("guest_report_ids", [])
    if not guest_ids:
        return []
    return UserLocation.query.filter(UserLocation.id.in_(guest_ids)).order_by(UserLocation.created_at.desc()).all()


def _comparison_payload(location, priority="overall"):
    solutions = SolarSolution.query.join(SolarSolution.provider).order_by(SolarSolution.system_size_kw.asc()).all()
    if not solutions:
        companies = SolarCompany.query.filter_by(active=True).all()
        priority_names = ("Tata Power Solar Systems Limited", "Adani Solar")
        address = (location.address or "").lower()
        district_aliases = {
            "modinagar": "ghaziabad",
            "muradnagar": "ghaziabad",
        }
        address_district = next(
            (district for city, district in district_aliases.items() if city in address),
            None,
        )
        if address_district:
            address = address + " " + address_district

        def installer_rank(company):
            district = (company.district or "").lower()
            exact_match = bool(district and (district in address or address_district and district == address_district))
            official_brand = company.name in priority_names
            return (
                0 if official_brand else (1 if exact_match else 2),
                0 if exact_match else 1,
                company.name.lower(),
            )

        companies.sort(key=installer_rank)
        exact_or_official = [
            company for company in companies
            if company.name in priority_names or (
                (company.district or "").lower() in address
            )
        ]
        companies = (exact_or_official or companies[:10])[:10]
        serialized_companies = []
        try:
            recommended_kw = float(location.system_size)
        except (TypeError, ValueError, OverflowError):
            recommended_kw = 0
        recommended_kw = recommended_kw if math.isfinite(recommended_kw) else 0
        recommended_kw = recommended_kw if recommended_kw is not None and recommended_kw >= 0 else 0
        try:
            battery_cost = float(location.battery_cost)
        except (TypeError, ValueError, OverflowError):
            battery_cost = 0
        battery_cost = battery_cost if math.isfinite(battery_cost) else 0
        battery_cost = battery_cost if battery_cost is not None and battery_cost >= 0 else 0
        estimate_low = round(recommended_kw * Config.SYSTEM_COST_PER_KW_LOW + battery_cost, 0)
        estimate_high = round(recommended_kw * Config.SYSTEM_COST_PER_KW_HIGH + battery_cost, 0)
        for rank, company in enumerate(companies, start=1):
            district = (company.district or "").strip()
            district_match = bool(district and (
                district.lower() in address
                or district.lower().replace(" ", "") in address.replace(" ", "")
            ))
            planning_factor = 0.96 + (sum(ord(char) for char in company.name) % 9) / 100
            planning_min = round(estimate_low * planning_factor, 0)
            planning_max = round(estimate_high * planning_factor, 0)
            official_source = company.verification_status == "official-source"
            serialized_companies.append({
                "id": company.id,
                "installer_id": company.id,
                "provider": company.name,
                "description": company.description or "UPNEDA approved-firms directory listing.",
                "system_size_kw": location.system_size,
                "catalogue_system_size_kw": location.system_size,
                "panel_brand": None,
                "panel_model": None,
                "panel_type": None,
                "panel_efficiency": None,
                "number_of_panels": None,
                "inverter_brand": None,
                "inverter_model": None,
                "inverter_type": None,
                "panel_warranty_years": None,
                "performance_warranty_years": None,
                "inverter_warranty_years": None,
                "installation_included": None,
                "mounting_included": None,
                "amc_available": None,
                "financing_available": None,
                "price_min": planning_min,
                "price_max": planning_max,
                "currency": "INR",
                "annual_generation": location.annual_generation,
                "annual_savings": (location.monthly_savings or 0) * 12 if location.monthly_savings is not None else None,
                "payback_years": None,
                "data_status": "SOLAR SETU PLANNING ESTIMATE",
                "source": company.source_url or "UPNEDA Approved Firms Directory",
                "last_updated": company.last_verified_at.strftime("%B %Y") if company.last_verified_at else "Date unavailable",
                "availability": "Service area match" if district_match else "Service coverage requires verification",
                "available": district_match,
                "match_score": 75 if district_match else 45,
                "recommendation_rank": rank,
                "recommendation_reasons": [
                    "Official national brand profile." if official_source else "Listed in the official UPNEDA approved-firms directory.",
                    "This price is Solar Setu's planning estimate, not a confirmed vendor quotation.",
                    "District service availability requires confirmation with the firm.",
                ],
                "tradeoffs": [
                    "Quotation, equipment specifications, warranty details and availability are not verified by Solar Setu."
                ],
                "insufficient_data": "Verification pending: service coverage, equipment, warranty and vendor quotation.",
                "badges": [
                    "OFFICIAL SOURCE" if official_source else "UPNEDA DIRECTORY LISTED",
                    "SERVICE AREA MATCH" if district_match else "VERIFY SERVICE COVERAGE",
                ],
            })
        return serialized_companies
    scaled_prices = []
    recommended_kw = location.system_size
    battery_cost = (
        location.battery_cost
        if location.battery_cost is not None
        and math.isfinite(location.battery_cost)
        and location.battery_cost >= 0
        else 0
    )
    if recommended_kw is not None and math.isfinite(recommended_kw) and recommended_kw >= 0:
        for solution in solutions:
            catalogue_kw = solution.system_size_kw
            listed_price = solution.indicative_price_max
            if (
                catalogue_kw is not None and math.isfinite(catalogue_kw) and catalogue_kw > 0
                and listed_price is not None and math.isfinite(listed_price) and listed_price >= 0
            ):
                scaled_prices.append(listed_price * (recommended_kw / catalogue_kw) + battery_cost)
    price_bounds = (min(scaled_prices), max(scaled_prices)) if scaled_prices else None
    serialized = [serialize_solution(solution, location, priority, price_bounds) for solution in solutions]
    serialized.sort(key=lambda item: (-item["match_score"], item["price_min"] or float("inf")))
    unique_serialized = []
    seen_providers = set()
    for item in serialized:
        provider_key = re.sub(r"[^a-z0-9]+", "", (item["provider"] or "").casefold())
        if provider_key in seen_providers:
            continue
        seen_providers.add(provider_key)
        unique_serialized.append(item)
    serialized = unique_serialized
    if serialized:
        lowest_price = min(
            (item["price_max"] for item in serialized if item["price_max"] is not None),
            default=None,
        )
        fastest_payback = min(
            (item["payback_years"] for item in serialized if item["payback_years"] is not None),
            default=None,
        )
        highest_efficiency = max(
            (item["panel_efficiency"] for item in serialized if item["panel_efficiency"] is not None),
            default=None,
        )
        highest_warranty = max(
            (
                (item["performance_warranty_years"] or 0) + (item["inverter_warranty_years"] or 0)
                for item in serialized
                if item["performance_warranty_years"] is not None
                and item["inverter_warranty_years"] is not None
            ),
            default=None,
        )
        for rank, item in enumerate(serialized, start=1):
            reasons = []
            tradeoffs = []
            missing = []
            item["recommendation_rank"] = rank
            item["recommendation_reasons"] = reasons
            item["tradeoffs"] = tradeoffs

            catalogue_kw = item.get("catalogue_system_size_kw")
            requested_kw = item.get("system_size_kw")
            if catalogue_kw is not None and requested_kw is not None:
                reasons.append(
                    f"Listed {catalogue_kw:g} kW package is scaled to your estimated {requested_kw:g} kW system."
                )
            else:
                missing.append("usable catalogue and requested system sizes")

            price_min, price_max = item.get("price_min"), item.get("price_max")
            if price_min is not None and price_max is not None:
                reasons.append(
                    f"Indicative estimated price: ₹{price_min:,.0f}–₹{price_max:,.0f}."
                )
                if lowest_price is not None and price_max > lowest_price:
                    tradeoffs.append(f"Upper-end estimate is ₹{price_max - lowest_price:,.0f} above the lowest listed upper-end estimate.")
            else:
                missing.append("indicative package pricing")

            annual_generation = item.get("annual_generation")
            annual_savings = item.get("annual_savings")
            if annual_generation is not None and annual_savings is not None:
                reasons.append(
                    f"Uses your rooftop estimate of {annual_generation:,.0f} kWh/year and ₹{annual_savings:,.0f} annual bill savings."
                )
            else:
                missing.append("annual generation and savings estimate")

            payback = item.get("payback_years")
            if payback is not None:
                reasons.append(f"Estimated simple payback: {payback:g} years.")
                if fastest_payback is not None and payback > fastest_payback:
                    tradeoffs.append(f"Payback is {payback - fastest_payback:g} years longer than the fastest listed estimate.")
            else:
                missing.append("positive annual savings and usable price for payback")

            efficiency = item.get("panel_efficiency")
            if efficiency is not None:
                reasons.append(f"Listed panel efficiency: {efficiency:g}%.")
                if highest_efficiency is not None and efficiency < highest_efficiency:
                    tradeoffs.append(f"Efficiency is {highest_efficiency - efficiency:g} percentage points below the highest listed option.")
            else:
                missing.append("panel efficiency")

            warranty_values = (
                item.get("performance_warranty_years"),
                item.get("inverter_warranty_years"),
            )
            if all(value is not None for value in warranty_values):
                warranty_total = sum(warranty_values)
                reasons.append(
                    f"Listed performance and inverter warranties total {warranty_total:g} years."
                )
                if highest_warranty is not None and warranty_total < highest_warranty:
                    tradeoffs.append("Warranty total is shorter than the longest listed option.")
            else:
                missing.append("complete performance and inverter warranty terms")

            if item.get("available"):
                reasons.append("Listed service regions match the estimate location.")
            else:
                tradeoffs.append("Regional service availability is not confirmed.")

            if priority == "payback":
                reasons.append("Ranking priority: faster estimated payback.")
            elif priority == "upfront_cost":
                reasons.append("Ranking priority: lower indicative upfront price.")
            elif priority == "savings":
                reasons.append(
                    "Annual savings use the same rooftop estimate for each option; provider-specific savings data is unavailable, so this criterion cannot distinguish the options."
                )
            if missing:
                item["insufficient_data"] = "Insufficient data: " + ", ".join(missing) + "."

        serialized[0]["badges"] = (
            ["TOP MATCH · DATA LIMITED"]
            if serialized[0].get("insufficient_data")
            else ["TOP MATCH"]
        )
        for item in serialized:
            item.setdefault("badges", [])
            if lowest_price is not None and item["price_max"] == lowest_price:
                item["badges"].append("BEST VALUE")
            if highest_efficiency is not None and item["panel_efficiency"] == highest_efficiency:
                item["badges"].append("HIGH EFFICIENCY")
            if item["available"]:
                item["badges"].append("AVAILABLE IN YOUR REGION")
    return serialized


def _savings_data(reports, selected=None):
    report = selected or (reports[0] if reports else None)
    monthly = report.monthly_savings if report else None
    annual = monthly * 12 if monthly is not None else None
    long_term = annual * 25 if annual is not None else None
    payback = report.payback_years if report else None
    if payback is None and report and annual:
        payback = report.net_investment / annual if report.net_investment else None
    co2_reduction_tons = (
        calculate_co2_avoided_tonnes(report.annual_generation) if report else None
    )
    annual_generation = (
        normalize_annual_generation_kwh(report.annual_generation) if report else None
    )

    def valid_nonnegative(value):
        if isinstance(value, bool):
            return None
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        return numeric if math.isfinite(numeric) and numeric >= 0 else None

    gross_cost = None
    subsidy_assumption = None
    calculator_annual_savings = None
    if report:
        system_cost = valid_nonnegative(report.system_cost)
        battery_cost = valid_nonnegative(report.battery_cost)
        if system_cost is not None and battery_cost is not None:
            gross_cost = system_cost + battery_cost
        subsidy_assumption = valid_nonnegative(report.subsidy_amount)
        if gross_cost is not None and subsidy_assumption is not None:
            subsidy_assumption = min(subsidy_assumption, gross_cost)
        monthly_savings_value = valid_nonnegative(report.monthly_savings)
        if monthly_savings_value is not None:
            calculator_annual_savings = monthly_savings_value * 12
    net_cost = (
        gross_cost - subsidy_assumption
        if gross_cost is not None and subsidy_assumption is not None
        else None
    )
    calculator_payback = (
        round(net_cost / calculator_annual_savings, 1)
        if net_cost is not None and net_cost > 0
        and calculator_annual_savings is not None and calculator_annual_savings > 0
        else None
    )
    return {
        "report": report,
        "co2_reduction_tons": co2_reduction_tons,
        "annual_generation": annual_generation,
        "calculator": {
            "gross_cost": gross_cost,
            "subsidy_assumption": subsidy_assumption if subsidy_assumption is not None else 0,
            "annual_savings": calculator_annual_savings,
            "net_cost": net_cost,
            "payback_years": calculator_payback,
        },
        "monthly": monthly,
        "annual": annual,
        "long_term": long_term,
        "payback": payback,
        "reports": reports,
    }


@bp.route("/savings")
def savings():
    reports = _account_reports()
    selected = None
    location_id = request.args.get("location_id", type=int)
    if location_id:
        candidate = db.session.get(UserLocation, location_id)
        if candidate:
            _authorized_location(candidate)
            if candidate in reports or (current_user() and candidate.user_id == current_user().id):
                selected = candidate
    data = _savings_data(reports, selected)
    return render_template("savings.html", savings=data, is_guest=not bool(current_user()))


@bp.route("/subsidy-guide")
def subsidy_guide():
    import json
    from pathlib import Path
    config_path = Path(__file__).resolve().parent / "data" / "subsidy_rates.json"
    with config_path.open("r", encoding="utf-8") as handle:
        subsidy_config = json.load(handle)
    table = [
        {
            "capacity": capacity,
            "central": central_subsidy(capacity),
            "up_additional": state_subsidy("Uttar Pradesh", capacity),
            "combined": central_subsidy(capacity) + state_subsidy("Uttar Pradesh", capacity),
        }
        for capacity in (1, 2, 3, 5)
    ]
    return render_template(
        "subsidy_guide.html",
        subsidy_config=subsidy_config,
        subsidy_table=table,
    )


@bp.post("/api/subsidy/calculate")
def calculate_subsidy_api():
    payload = request.get_json(silent=True) or {}
    try:
        result = calculate_subsidy(
            payload.get("state"),
            payload.get("capacity"),
            payload.get("category"),
            payload.get("configuration"),
        )
        return jsonify({"success": True, "result": result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@bp.route("/compare")
def compare():
    reports = _account_reports()
    selected = None
    location_id = request.args.get("location_id", type=int)
    if location_id:
        candidate = db.session.get(UserLocation, location_id)
        if candidate:
            _authorized_location(candidate)
            if candidate in reports:
                selected = candidate
    selected = selected or (reports[0] if reports else None)
    priority = request.args.get("priority", "overall")
    if priority not in PRIORITY_LABELS:
        priority = "overall"
    solutions = _comparison_payload(selected, priority) if selected else []
    return render_template("compare.html", location=selected, solutions=solutions, priority=priority, priority_labels=PRIORITY_LABELS)


@bp.get("/installers")
def installers():
    search = clean_text = (request.args.get("q") or "").strip()
    district = (request.args.get("district") or "").strip()
    verification = (request.args.get("verification") or "").strip()
    query = SolarCompany.query.filter_by(active=True)
    if search:
        query = query.filter(SolarCompany.name.ilike(f"%{search}%"))
    if district and district.lower() != "all":
        query = query.filter(SolarCompany.district.ilike(f"%{district}%"))
    if verification and verification.lower() != "all":
        query = query.filter(SolarCompany.verification_status == verification)
    companies = query.order_by(SolarCompany.district.asc(), SolarCompany.name.asc()).limit(200).all()
    districts = [row[0] for row in db.session.query(SolarCompany.district).filter(
        SolarCompany.active.is_(True), SolarCompany.district.isnot(None)
    ).distinct().order_by(SolarCompany.district.asc()).all()]
    return render_template("installers.html", companies=companies, districts=districts, search=search,
                           selected_district=district, selected_verification=verification)


@bp.get("/installers/<int:company_id>")
def installer_detail(company_id):
    company = SolarCompany.query.filter_by(id=company_id, active=True).first_or_404()
    location = None
    location_id = request.args.get("location_id", type=int)
    if location_id:
        location = db.session.get(UserLocation, location_id)
        if location:
            _authorized_location(location)
    return render_template("installer_detail.html", company=company, location=location)


def _normalize_indian_mobile(value):
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    return digits if len(digits) == 10 and digits[0] in "6789" else None


@bp.post("/installers/<int:company_id>/quotation")
def request_quotation(company_id):
    company = SolarCompany.query.filter_by(id=company_id, active=True).first_or_404()
    payload = request.form
    customer_name = (payload.get("customer_name") or "").strip()
    mobile = _normalize_indian_mobile(payload.get("mobile"))
    email = (payload.get("email") or "").strip()
    address = (payload.get("installation_address") or "").strip()
    if len(customer_name) < 2:
        return render_template("installer_detail.html", company=company, quotation_error="Enter your full name.", quotation=True), 400
    if not mobile:
        return render_template("installer_detail.html", company=company, quotation_error="Enter a valid 10-digit Indian mobile number.", quotation=True), 400
    if len(address) < 10:
        return render_template("installer_detail.html", company=company, quotation_error="Enter the complete installation address.", quotation=True), 400
    try:
        system_size = float(payload.get("system_size_kw") or 0) or None
        monthly_bill = float(payload.get("monthly_bill") or 0) or None
    except ValueError:
        return render_template("installer_detail.html", company=company, quotation_error="System size and monthly bill must be valid numbers.", quotation=True), 400
    if system_size is not None and system_size <= 0:
        return render_template("installer_detail.html", company=company, quotation_error="System size must be greater than zero.", quotation=True), 400
    lead = QuotationRequest(
        company_id=company.id,
        customer_name=customer_name,
        mobile=mobile,
        email=email or None,
        installation_address=address,
        district=(payload.get("district") or company.district or "").strip() or None,
        system_size_kw=system_size,
        battery_required=(payload.get("battery_required") == "yes"),
        monthly_bill=monthly_bill,
        preferred_timeline=(payload.get("preferred_timeline") or "").strip() or None,
    )
    db.session.add(lead)
    db.session.commit()
    return render_template("installer_detail.html", company=company, quotation_success=True,
                           quotation_reference=f"SS-Q{lead.id:06d}")


@bp.post("/api/comparisons")
def save_comparison():
    user = current_user()
    if not user:
        return jsonify({"error": "Create a free account to save this comparison."}), 401
    payload = request.get_json(silent=True) or {}
    ids = payload.get("solution_ids") or []
    if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or not all(isinstance(value, int) for value in ids):
        return jsonify({"error": "Select between one and three solutions."}), 400
    valid_ids = {solution.id for solution in SolarSolution.query.filter(SolarSolution.id.in_(ids)).all()}
    if set(ids) != valid_ids:
        return jsonify({"error": "One or more selected solutions are unavailable."}), 400
    location_id = payload.get("location_id")
    location = db.session.get(UserLocation, location_id) if location_id else None
    if location and location.user_id != user.id:
        abort(403)
    comparison = SavedComparison(user_id=user.id, location_id=location.id if location else None, solution_ids=ids, priority=payload.get("priority", "overall"))
    db.session.add(comparison)
    db.session.commit()
    return jsonify({"id": comparison.id})


@bp.get("/comparisons")
def saved_comparisons():
    user = current_user()
    if not user:
        return redirect(url_for("routes.login", next=request.path))
    comparisons = SavedComparison.query.filter_by(user_id=user.id).order_by(SavedComparison.created_at.desc()).all()
    return render_template("saved_comparisons.html", comparisons=comparisons)


@bp.route("/settings", methods=["GET", "POST"])
def settings():
    user = current_user()
    stored = dict((user.settings if user else session.get("solar_preferences")) or {})
    message = None
    if request.method == "POST":
        stored = {
            "property_type": request.form.get("property_type", "residential"),
            "orientation": request.form.get("orientation", "auto"),
            "goal": request.form.get("goal", "maximum_savings"),
            "budget": request.form.get("budget", "") ,
            "report_updates": request.form.get("report_updates") == "on",
            "savings_insights": request.form.get("savings_insights") == "on",
            "solar_tips": request.form.get("solar_tips") == "on",
            "theme": "light",
        }
        if user:
            user.settings = stored
            db.session.commit()
        else:
            session["solar_preferences"] = stored
        message = "Your preferences were saved."
    return render_template("settings.html", preferences=stored, message=message)


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("routes.dashboard"))
    next_url = _safe_next(request.args.get("next") or request.form.get("next"))
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(name) < 2 or len(name) > 120:
            error = "Enter your full name."
        elif not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists. Try logging in."
        else:
            pending_id = session.get("pending_save_location_id")
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session.clear()
            session["user_id"] = user.id
            regenerate_csrf_token()
            if pending_id:
                session["pending_save_location_id"] = pending_id
            saved_id = _complete_pending_save(user)
            return redirect(url_for("routes.report", location_id=saved_id) if saved_id else (next_url or url_for("routes.profile")))
    return render_template("auth.html", mode="signup", error=error, next_url=next_url)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("routes.dashboard"))
    next_url = _safe_next(request.args.get("next") or request.form.get("next"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            error = "Email or password is incorrect."
        else:
            pending_id = session.get("pending_save_location_id")
            session.clear()
            session["user_id"] = user.id
            regenerate_csrf_token()
            if pending_id:
                session["pending_save_location_id"] = pending_id
            saved_id = _complete_pending_save(user)
            return redirect(url_for("routes.report", location_id=saved_id) if saved_id else (next_url or url_for("routes.dashboard")))
    return render_template("auth.html", mode="login", error=error, next_url=next_url)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("routes.index"))


@bp.post("/report/<int:location_id>/save")
def save_report(location_id):
    location = UserLocation.query.get_or_404(location_id)
    user = current_user()
    if not user:
        session["pending_save_location_id"] = location.id
        return redirect(url_for("routes.signup", next=url_for("routes.report", location_id=location.id)))
    if location.user_id not in (None, user.id):
        abort(403)
    location.user_id = user.id
    db.session.commit()
    return redirect(url_for("routes.report", location_id=location.id))


@bp.route("/report/<int:location_id>")
def report(location_id):
    location = UserLocation.query.get_or_404(location_id)
    _authorized_location(location)
    loc_dict = location.to_dict()
    # Recalculate emissions for existing rows from their stored annual generation.
    extras = loc_dict.get("extras") or {}
    loc_dict["co2_reduction_tons"] = calculate_co2_avoided_tonnes(
        loc_dict.get("annual_generation")
    )
    loc_dict["grid_emission_factor_tco2_per_mwh"] = get_grid_emission_factor_tco2_per_mwh()
    loc_dict["environmental_equivalents"] = (
        calculate_environmental_equivalents(loc_dict["co2_reduction_tons"])
        if loc_dict["co2_reduction_tons"] is not None
        else None
    )
    if not loc_dict.get("payback_years") and loc_dict.get("monthly_savings"):
        loc_dict["payback_years"] = round(
            loc_dict["net_investment"] / (loc_dict["monthly_savings"] * 12), 1
        )
    loc_dict["cashflow_25yr"] = extras.get("cashflow_25yr")
    for key in (
        "inverter", "inverter_type", "bill_sizing", "roof_capacity_kw",
        "sizing_method", "rule_of_thumb_monthly_units", "rule_of_thumb_annual_units",
        "property_type", "needs_backup", "planning_notes", "system_cost_low",
        "system_cost_high", "annual_om", "performance_ratio", "peak_sun_hours_assumed",
        "daily_units_per_kw_range", "dc_note", "cost_per_kw",
    ):
        if key in extras and extras[key] is not None:
            loc_dict[key] = extras[key]
        else:
            loc_dict[key] = None
    return render_template("report.html", loc=loc_dict)


# ------------------------------------------------------------- REST API ----

@bp.route("/api/geocode")
def api_geocode():
    """Geocode a free-text address.

    Tries Nominatim (OpenStreetMap) first with parameters tuned for
    niche Indian places (colleges, societies, buildings), then falls
    back to Photon (Komoot) which often surfaces smaller OSM POIs.
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    results = []
    source = "none"
    headers = {
        "User-Agent": "RooftopSolarEstimator/1.1 (educational prototype; contact: local)",
        "Accept-Language": "en-IN,en,hi",
    }

    # --- Primary: Nominatim (detailed, India-biased) ---
    try:
        resp = requests.get(
            Config.NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "limit": 12,
                "countrycodes": "in",
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 1,
                "dedupe": 1,
            },
            headers=headers,
            timeout=max(Config.REQUEST_TIMEOUT, 10),
        )
        resp.raise_for_status()
        for r in resp.json():
            display = r.get("display_name") or query
            # Prefer a tighter label when address parts exist
            addr = r.get("address") or {}
            parts = [
                addr.get("building") or addr.get("amenity") or addr.get("office")
                or addr.get("shop") or addr.get("tourism") or addr.get("leisure"),
                addr.get("road") or addr.get("neighbourhood") or addr.get("suburb"),
                addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county"),
                addr.get("state"),
            ]
            short = ", ".join(p for p in parts if p)
            results.append({
                "display_name": display,
                "label": short or display,
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": r.get("type") or r.get("class") or "",
                "importance": r.get("importance"),
            })
        if results:
            source = "nominatim"
    except Exception:
        pass

    # --- Secondary: Photon (good for niche / incomplete OSM names) ---
    if len(results) < 3:
        try:
            resp = requests.get(
                "https://photon.komoot.io/api/",
                params={
                    "q": query,
                    "limit": 10,
                    "lang": "en",
                    "lat": 22.0,   # bias toward India
                    "lon": 78.0,
                },
                headers=headers,
                timeout=max(Config.REQUEST_TIMEOUT, 10),
            )
            resp.raise_for_status()
            features = (resp.json() or {}).get("features") or []
            seen = {(round(r["lat"], 5), round(r["lon"], 5)) for r in results}
            for f in features:
                props = f.get("properties") or {}
                geom = f.get("geometry") or {}
                coords = geom.get("coordinates") or [None, None]
                lon, lat = coords[0], coords[1]
                if lat is None or lon is None:
                    continue
                # Prefer India / nearby when country is known
                country = (props.get("country") or props.get("countrycode") or "").lower()
                if country and country not in ("india", "in", "भारत"):
                    # still allow if query is clearly local and we have few hits
                    if len(results) >= 5:
                        continue
                key = (round(float(lat), 5), round(float(lon), 5))
                if key in seen:
                    continue
                seen.add(key)
                name_parts = [
                    props.get("name"),
                    props.get("street"),
                    props.get("locality") or props.get("district") or props.get("city"),
                    props.get("state"),
                    props.get("country"),
                ]
                display = ", ".join(p for p in name_parts if p) or query
                results.append({
                    "display_name": display,
                    "label": display,
                    "lat": float(lat),
                    "lon": float(lon),
                    "type": props.get("osm_value") or props.get("type") or "",
                    "importance": None,
                })
            if results and source == "none":
                source = "photon"
            elif results:
                source = f"{source}+photon"
        except Exception:
            pass

    if not results:
        # Last-resort mock so the UI never goes empty during demos / offline
        return jsonify({
            "results": [{
                "display_name": f"{query} (geocoding unavailable — try a fuller address)",
                "label": query,
                "lat": 28.6139,
                "lon": 77.2090,
                "type": "mock",
            }],
            "source": "mock_fallback",
        })

    return jsonify({"results": results[:12], "source": source})


@bp.route("/api/reverse-geocode")
def api_reverse_geocode():
    """Reverse-geocode a lat/lon (used for 'use current location')."""
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    if lat is None or lon is None:
        return jsonify({"error": "Missing lat/lon"}), 400

    headers = {
        "User-Agent": "RooftopSolarEstimator/1.1 (educational prototype; contact: local)",
        "Accept-Language": "en-IN,en,hi",
    }
    try:
        resp = requests.get(
            Config.NOMINATIM_REVERSE_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 18,  # building-level when available
            },
            headers=headers,
            timeout=max(Config.REQUEST_TIMEOUT, 10),
        )
        resp.raise_for_status()
        data = resp.json()
        return jsonify({
            "address": data.get("display_name", "Unknown location"),
            "source": "nominatim",
            "lat": lat,
            "lon": lon,
        })
    except Exception:
        return jsonify({
            "address": "Current location (address lookup unavailable)",
            "source": "mock_fallback",
            "lat": lat,
            "lon": lon,
        })



@bp.route("/api/parse-maps-url")
def api_parse_maps_url():
    """Extract lat/lng (and optional place name) from a Google Maps URL.

    Supports common formats:
      • https://www.google.com/maps/@lat,lng,zoom
      • https://www.google.com/maps/place/.../@lat,lng,zoom
      • https://www.google.com/maps?q=lat,lng
      • https://maps.google.com/?q=lat,lng
      • https://maps.app.goo.gl/...  (short links — followed once)
      • https://goo.gl/maps/...
      • query=lat,lng  /  !3dLAT!4dLNG  place data
    """
    import re
    from urllib.parse import urlparse, parse_qs, unquote

    raw = (request.args.get("url") or "").strip()
    if not raw:
        return jsonify({"error": "Missing url parameter"}), 400

    # Allow bare coordinates pasted by accident
    bare = re.match(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", raw)
    if bare:
        lat, lon = float(bare.group(1)), float(bare.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            address = _reverse_address(lat, lon)
            return jsonify({"lat": lat, "lon": lon, "address": address, "source": "coordinates"})
        return jsonify({"error": "Coordinates out of range"}), 400

    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw

    final_url = raw
    # Expand short Google links (one hop)
    try:
        if re.search(r"(maps\.app\.goo\.gl|goo\.gl/maps|g\.page)/", raw, re.I):
            resp = requests.get(
                raw,
                headers={"User-Agent": "RooftopSolarEstimator/1.1"},
                timeout=max(Config.REQUEST_TIMEOUT, 10),
                allow_redirects=True,
            )
            final_url = str(resp.url or raw)
    except Exception:
        final_url = raw

    lat = lon = None
    place_hint = None

    # Prefer the place MARKER coordinates (!3dLAT!4dLNG) over the camera
    # center (@lat,lng). Google Maps share links often center the viewport
    # slightly away from the actual pin; !3d/!4d is the pin itself.
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", final_url)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))

    # data=!4m...!8m2!3dLAT!4dLNG sometimes appears more than once — take last
    if lat is None:
        all_pins = re.findall(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", final_url)
        if all_pins:
            lat, lon = float(all_pins[-1][0]), float(all_pins[-1][1])

    # @lat,lng,zoom — camera / viewport center (fallback)
    if lat is None:
        m = re.search(r"@(-?\d+\.?\d*),\s*(-?\d+\.?\d*)(?:,\d+\.?\d*[a-z]?)?", final_url, re.I)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))

    # query params: q= / query= / ll=
    if lat is None:
        try:
            parsed = urlparse(final_url)
            qs = parse_qs(parsed.query)
            for key in ("q", "query", "ll", "center"):
                vals = qs.get(key) or []
                if not vals:
                    continue
                val = unquote(vals[0])
                cm = re.search(r"(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)", val)
                if cm:
                    lat, lon = float(cm.group(1)), float(cm.group(2))
                    # leftover text before coords can be a place name
                    text = val[: cm.start()].strip(" ,+")
                    if text and not re.match(r"^-?\d", text):
                        place_hint = text
                    break
                # q=Place+Name without coords — geocode later
                if key in ("q", "query") and val and not re.search(r"-?\d+\.\d+", val):
                    place_hint = val.replace("+", " ")
        except Exception:
            pass

    # /maps/place/Place+Name/
    if place_hint is None:
        m = re.search(r"/maps/place/([^/@]+)", final_url)
        if m:
            place_hint = unquote(m.group(1).replace("+", " ")).strip()

    # /dir/... destinations sometimes
    if lat is None:
        m = re.search(r"/dir/[^/]*/(-?\d+\.?\d*),\s*(-?\d+\.?\d*)", final_url)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))

    if lat is None or lon is None:
        # Fall back: if we only have a place name, geocode it
        if place_hint:
            try:
                resp = requests.get(
                    Config.NOMINATIM_URL,
                    params={
                        "q": place_hint,
                        "format": "json",
                        "limit": 1,
                        "countrycodes": "in",
                    },
                    headers={"User-Agent": "RooftopSolarEstimator/1.1"},
                    timeout=max(Config.REQUEST_TIMEOUT, 10),
                )
                resp.raise_for_status()
                rows = resp.json() or []
                if rows:
                    lat = float(rows[0]["lat"])
                    lon = float(rows[0]["lon"])
                    address = rows[0].get("display_name") or place_hint
                    return jsonify({
                        "lat": lat,
                        "lon": lon,
                        "address": address,
                        "source": "maps_url_geocoded",
                        "resolved_url": final_url,
                    })
            except Exception:
                pass
        return jsonify({
            "error": (
                "Could not read coordinates from this link. "
                "Open the place in Google Maps, copy the link from the browser "
                "address bar (or Share → Copy link), and try again."
            )
        }), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"error": "Coordinates out of range"}), 400

    address = place_hint or _reverse_address(lat, lon)
    # Prefer reverse-geocoded full address when we only had a short hint
    if place_hint and len(place_hint) < 12:
        full = _reverse_address(lat, lon)
        if full:
            address = full

    return jsonify({
        "lat": lat,
        "lon": lon,
        "address": address or f"{lat:.6f}, {lon:.6f}",
        "source": "maps_url",
        "resolved_url": final_url,
    })


def _reverse_address(lat, lon):
    """Best-effort reverse geocode for Maps URL / coordinate paste."""
    try:
        resp = requests.get(
            Config.NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "json", "zoom": 18},
            headers={"User-Agent": "RooftopSolarEstimator/1.1"},
            timeout=max(Config.REQUEST_TIMEOUT, 8),
        )
        resp.raise_for_status()
        return (resp.json() or {}).get("display_name")
    except Exception:
        return None


@bp.route("/api/estimate", methods=["POST"])
def api_estimate():
    """
    Main estimation endpoint. Expects JSON:
    {
      "address": str,
      "latitude": float,
      "longitude": float,
      "polygon": [[lat, lng], [lat, lng], ...],
      "obstructions": optional list of polygons,
      "orientation": "auto" | degrees (0=N … 180=S),
      "battery_kwh": float (0 = no battery),
      "state": str (optional, for tariff lookup)
    }
    Runs the full solar_logic pipeline, persists a UserLocation row, and
    returns the computed estimate.
    """
    payload = request.get_json(silent=True) or {}

    address = payload.get("address", "Unknown address")
    latitude = _coerce_float(payload.get("latitude"))
    longitude = _coerce_float(payload.get("longitude"))
    polygon = payload.get("polygon", [])
    obstructions = payload.get("obstructions", [])
    state = payload.get("state")
    orientation = payload.get("orientation", "auto")
    battery_kwh = _coerce_float(payload.get("battery_kwh"), 0.0)
    essential_load_kw = _coerce_float(payload.get("essential_load_kw"))
    backup_hours = _coerce_float(payload.get("backup_hours"))
    battery_technology = payload.get("battery_technology") or "lfp"
    monthly_bill = _coerce_float(payload.get("monthly_bill"))
    property_type = payload.get("property_type") or "residential"
    needs_backup = bool(payload.get("needs_backup"))
    inverter_preference = payload.get("inverter_preference") or "auto"

    if latitude is None or longitude is None:
        return jsonify({"error": "latitude and longitude are required"}), 400
    if not isinstance(polygon, list) or len(polygon) < 3:
        return jsonify({"error": "A rooftop polygon with at least 3 points is required"}), 400
    for point in polygon:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return jsonify({"error": "Each rooftop point must include latitude and longitude values."}), 400
        lat = _coerce_float(point[0])
        lng = _coerce_float(point[1])
        if lat is None or lng is None:
            return jsonify({"error": "Roof polygon coordinates must be valid latitude/longitude numbers."}), 400
    if not isinstance(obstructions, list):
        obstructions = []

    tariff = _lookup_tariff(state)
    # Prefer explicit tariff from bill calculator when provided
    if payload.get("tariff_per_kwh"):
        try:
            tariff = float(payload["tariff_per_kwh"])
        except (TypeError, ValueError):
            pass

    try:
        result = run_full_estimation(
            latitude=latitude,
            longitude=longitude,
            coordinates=polygon,
            obstructions=obstructions,
            tariff_per_kwh=tariff,
            orientation=orientation,
            battery_kwh=battery_kwh,
            monthly_bill=monthly_bill,
            property_type=property_type,
            needs_backup=needs_backup,
            inverter_preference=inverter_preference,
            essential_load_kw=essential_load_kw,
            backup_hours=backup_hours,
            battery_technology=battery_technology,
        )
    except Exception as exc:
        return jsonify({"error": f"Estimation engine failed: {exc}"}), 500

    try:
        owner = current_user()
        location = UserLocation(
            user_id=owner.id if owner else None,
            address=address,
            latitude=latitude,
            longitude=longitude,
            polygon_geojson={"type": "Polygon", "coordinates": [polygon]},
            obstructions_geojson={"type": "MultiPolygon", "coordinates": [[o] for o in obstructions]} if obstructions else None,
            system_size=result["system_size"],
            annual_generation=result["annual_generation"],
            monthly_data=result["monthly_data"],
            roof_area_sqm=result["roof_area_sqm"],
            obstructed_area_sqm=result["obstructed_area_sqm"],
            usable_area_sqm=result["usable_area_sqm"],
            system_cost=result["system_cost"],
            subsidy_amount=result["subsidy_amount"],
            net_investment=result["net_investment"],
            monthly_savings=result["monthly_savings"],
            co2_reduction_tons=result["co2_reduction_tons"],
            irradiance_source=result["irradiance_source"],
            orientation_deg=result.get("orientation_deg"),
            orientation_label=result.get("orientation_label"),
            orientation_factor=result.get("orientation_factor"),
            recommended_tilt_deg=result.get("recommended_tilt_deg"),
            battery_kwh=result.get("battery_kwh", 0),
            battery_cost=result.get("battery_cost", 0),
            specific_yield=result.get("specific_yield"),
            capacity_factor=result.get("capacity_factor"),
            lcoe=result.get("lcoe"),
            lifetime_kwh=result.get("lifetime_kwh"),
            self_consumption_frac=result.get("self_consumption_frac"),
            payback_years=result.get("payback_years"),
            extras={
                "orientation_source": result.get("orientation_source"),
                "cashflow_25yr": result.get("cashflow_25yr"),
                "environmental_equivalents": result.get("environmental_equivalents"),
                "inverter": result.get("inverter"),
                "inverter_type": result.get("inverter_type"),
                "bill_sizing": result.get("bill_sizing"),
                "roof_capacity_kw": result.get("roof_capacity_kw"),
                "sizing_method": result.get("sizing_method"),
                "rule_of_thumb_monthly_units": result.get("rule_of_thumb_monthly_units"),
                "rule_of_thumb_annual_units": result.get("rule_of_thumb_annual_units"),
                "property_type": result.get("property_type"),
                "needs_backup": result.get("needs_backup"),
                "planning_notes": result.get("planning_notes"),
                "system_cost_low": result.get("system_cost_low"),
                "system_cost_high": result.get("system_cost_high"),
                "annual_om": result.get("annual_om"),
                "performance_ratio": result.get("performance_ratio"),
                "peak_sun_hours_assumed": result.get("peak_sun_hours_assumed"),
                "daily_units_per_kw_range": result.get("daily_units_per_kw_range"),
                "battery_technology": battery_technology,
                "battery_recommendation": result.get("battery_recommendation"),
                "dc_note": result.get("dc_note"),
                "cost_per_kw": result.get("cost_per_kw"),
            },
        )
        db.session.add(location)
        db.session.commit()
        if not owner:
            guest_ids = session.get("guest_report_ids", [])
            session["guest_report_ids"] = (guest_ids + [location.id])[-10:]
    except Exception as exc:
        db.session.rollback()
        # Keep a clear message for legacy local databases without suggesting data deletion.
        err_msg = str(exc)
        if "no such column" in err_msg.lower() or "has no column" in err_msg.lower():
            return jsonify({
                "error": (
                    "Database schema is outdated. Apply the current migration or "
                    "use a backed-up database before retrying."
                )
            }), 500
        return jsonify({"error": f"Could not save estimate: {exc}"}), 500
    
    response = _sanitize_json_value(result.copy())
    response["location_id"] = location.id
    response["redirect_url"] = f"/report/{location.id}"
    return jsonify(response)


@bp.route("/api/locations")
def api_locations():
    """List saved locations (used by dashboard's 'My Reports' / 'Saved Locations')."""
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    locations = UserLocation.query.filter_by(user_id=user.id).order_by(UserLocation.created_at.desc()).all()
    return jsonify([loc.to_dict() for loc in locations])


@bp.route("/api/locations/<int:location_id>")
def api_location_detail(location_id):
    location = UserLocation.query.get_or_404(location_id)
    _authorized_location(location)
    return jsonify(location.to_dict())


@bp.route("/api/solar-assistant", methods=["POST"])
def api_solar_assistant():
    """Answer a Surya question using the current, client-supplied report context."""
    payload = request.get_json(silent=True) or {}
    reply, status = ask_surya(payload.get("message"), payload.get("context"))
    return jsonify({"reply": reply}), status


@bp.get("/api/compare/<int:location_id>")
def api_compare(location_id):
    location = UserLocation.query.get_or_404(location_id)
    _authorized_location(location)
    priority = request.args.get("priority", "overall")
    if priority not in PRIORITY_LABELS:
        priority = "overall"
    return jsonify({"location": location.to_dict(), "solutions": _comparison_payload(location, priority), "priority": priority})


@bp.route("/report/<int:location_id>/pdf")
def download_pdf(location_id):
    location = UserLocation.query.get_or_404(location_id)
    _authorized_location(location)
    try:
        pdf_buffer = generate_pdf_report(location)
    except Exception as exc:
        # WeasyPrint may need cairo/pango; ReportLab is the pure-Python fallback.
        return jsonify({
            "error": (
                "PDF generation failed. Install reportlab (`pip install reportlab`) "
                "or system packages for WeasyPrint. "
                f"Details: {exc}"
            )
        }), 500

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"solar_report_{location_id}.pdf",
        max_age=0,
    )


# ------------------------------------------------------------- helpers -----

def _lookup_tariff(state):
    if state:
        row = TariffTable.query.filter_by(state=state).first()
        if row:
            return row.rate_per_kwh
    return Config.DEFAULT_TARIFF
