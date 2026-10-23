from math import isfinite


PRIORITY_LABELS = {
    "overall": "Best Overall Value",
    "upfront_cost": "Lower Upfront Cost",
    "payback": "Faster Estimated Payback",
    "savings": "Higher Estimated Savings (same rooftop estimate)",
    "generation": "Panel Efficiency (Generation Proxy)",
    "warranty": "Long Warranty",
    "sustainability": "Sustainability",
}


def location_terms(address):
    value = (address or "").lower()
    return {part.strip() for part in value.replace(",", " ").split() if len(part.strip()) > 2}


def _finite_nonnegative(value):
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def serves_region(provider, address):
    regions = provider.service_regions or []
    if not regions:
        return False, "Availability to be verified"
    terms = location_terms(address)
    matched = any(any(region.lower() in terms or region.lower() in (address or "").lower() for region in regions) for _ in [0])
    return matched, "Available in your region" if matched else "Availability to be verified"


def _normalized(value, low, high):
    value = _finite_nonnegative(value)
    low = _finite_nonnegative(low)
    high = _finite_nonnegative(high)
    if (
        value is None or low is None or high is None
        or high <= low
    ):
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def score_solution(
    solution, recommended_kw, address, priority="overall", price_bounds=None,
    payback_years=None, estimated_price=None,
):
    available, _ = serves_region(solution.provider, address)
    catalogue_size = _finite_nonnegative(solution.system_size_kw)
    recommended_kw = _finite_nonnegative(recommended_kw)
    size_match = (
        max(0.0, 1.0 - abs(catalogue_size - recommended_kw) / max(recommended_kw, 1.0))
        if catalogue_size is not None and recommended_kw is not None
        else 0.5
    )
    prices = price_bounds or (None, None)
    price_value = estimated_price
    price_score = (
        1.0 - _normalized(price_value, prices[0], prices[1])
        if _finite_nonnegative(price_value) is not None and all(value is not None for value in prices)
        else 0.5
    )
    efficiency = _normalized(solution.panel_efficiency, 18, 23)
    warranty_values = (solution.performance_warranty_years, solution.inverter_warranty_years)
    warranty = (
        _normalized(sum(warranty_values), 25, 40)
        if all(_finite_nonnegative(value) is not None for value in warranty_values)
        and all(value is not None for value in warranty_values)
        else 0.5
    )
    payback_years = _finite_nonnegative(payback_years)
    payback_score = (
        1.0 / (1.0 + payback_years)
        if payback_years is not None and payback_years >= 0
        else 0.5
    )
    priority_bonus = {
        "upfront_cost": price_score, "payback": payback_score,
        "savings": 0.5,
        "generation": efficiency, "warranty": warranty,
        "sustainability": efficiency, "overall": (price_score + efficiency + warranty) / 3,
    }.get(priority, (price_score + efficiency + warranty) / 3)
    score = 0.35 * size_match + 0.18 * price_score + 0.15 * efficiency + 0.15 * warranty + 0.12 * priority_bonus + 0.05 * float(available)
    return round(max(0, min(100, score * 100)))


def serialize_solution(solution, analysis, priority="overall", price_bounds=None):
    recommended_kw = _finite_nonnegative(analysis.system_size)
    address = analysis.address
    available, availability = serves_region(solution.provider, address)
    catalogue_size = _finite_nonnegative(solution.system_size_kw)
    size_scale = recommended_kw / catalogue_size if recommended_kw is not None and catalogue_size is not None and catalogue_size > 0 else None
    battery_cost = _finite_nonnegative(analysis.battery_cost)
    battery_cost = battery_cost if battery_cost is not None else 0
    listed_min = _finite_nonnegative(solution.indicative_price_min)
    listed_max = _finite_nonnegative(solution.indicative_price_max)
    price_min = round(listed_min * size_scale + battery_cost) if listed_min is not None and size_scale is not None else None
    price_max = round(listed_max * size_scale + battery_cost) if listed_max is not None and size_scale is not None else None
    number_of_panels = max(1, round(solution.number_of_panels * size_scale)) if solution.number_of_panels is not None and size_scale is not None else None
    monthly_savings = _finite_nonnegative(analysis.monthly_savings)
    annual_savings = round(monthly_savings * 12, 2) if monthly_savings is not None else None
    subsidy = _finite_nonnegative(analysis.subsidy_amount)
    net_price_estimate = max(price_max - subsidy, 0) if price_max is not None and subsidy is not None else None
    payback_years = round(net_price_estimate / annual_savings, 1) if net_price_estimate is not None and net_price_estimate > 0 and annual_savings is not None and annual_savings > 0 else None
    annual_generation = _finite_nonnegative(analysis.annual_generation)
    return {
        "id": solution.id, "provider": solution.provider.name, "description": solution.provider.description,
        "system_size_kw": recommended_kw, "catalogue_system_size_kw": solution.system_size_kw, "panel_brand": solution.panel_brand, "panel_model": solution.panel_model,
        "panel_type": solution.panel_type, "panel_efficiency": solution.panel_efficiency, "number_of_panels": number_of_panels,
        "inverter_brand": solution.inverter_brand, "inverter_model": solution.inverter_model, "inverter_type": solution.inverter_type,
        "panel_warranty_years": solution.panel_warranty_years, "performance_warranty_years": solution.performance_warranty_years,
        "inverter_warranty_years": solution.inverter_warranty_years, "installation_included": solution.installation_included,
        "mounting_included": solution.mounting_included, "amc_available": solution.amc_available, "financing_available": solution.financing_available,
        "price_min": price_min, "price_max": price_max, "currency": solution.currency,
        "annual_generation": annual_generation, "annual_savings": annual_savings, "payback_years": payback_years,
        "data_status": solution.data_status, "source": solution.source, "last_updated": solution.last_updated.strftime("%B %Y"),
        "availability": availability, "available": available,
        "match_score": score_solution(
            solution, recommended_kw, address, priority, price_bounds,
            payback_years, price_max,
        ),
    }