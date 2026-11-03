import pytest

from app.services.subsidy_service import (
    calculate_subsidy,
    central_subsidy,
    enrich_saved_report_financials,
    state_subsidy,
)


@pytest.mark.parametrize(("capacity", "expected"), [
    (1, 30000),
    (1.5, 45000),
    (2, 60000),
    (2.5, 69000),
    (3, 78000),
    (4, 78000),
    (5, 78000),
])
def test_central_subsidy(capacity, expected):
    assert central_subsidy(capacity) == expected


@pytest.mark.parametrize(("capacity", "expected"), [
    (1, 15000),
    (2, 30000),
    (3, 30000),
    (5, 30000),
])
def test_up_subsidy(capacity, expected):
    assert state_subsidy("Uttar Pradesh", capacity) == expected


def test_commercial_is_not_residential_cfa_eligible():
    result = calculate_subsidy("Uttar Pradesh", 3, "commercial", "on-grid")
    assert not result["eligible"]
    assert result["central_subsidy"] == 78000
    assert result["final_estimated_subsidy"] == 0


@pytest.mark.parametrize(("configuration", "expected"), [
    ("off-grid", "Verify eligibility on the official portal"),
    ("hybrid", "Verify eligibility on the official portal"),
])
def test_uncertain_configuration(configuration, expected):
    result = calculate_subsidy("Uttar Pradesh", 3, "residential", configuration)
    assert not result["eligible"]
    assert result["eligibility_status"] == expected


@pytest.mark.parametrize("capacity", [-1, 0, 11])
def test_invalid_capacity(capacity):
    with pytest.raises(ValueError):
        calculate_subsidy("Uttar Pradesh", capacity, "residential", "on-grid")


def test_report_39_kw_up_grid_connected():
    result = calculate_subsidy(
        "Modinagar, Uttar Pradesh",
        3.9,
        "residential",
        "hybrid",
        saved_inverter="Hybrid inverter, Works with solar, battery and grid",
    )
    assert result["central_subsidy"] == 78000
    assert result["state_additional_subsidy"] == 30000
    assert result["final_estimated_subsidy"] == 108000


@pytest.mark.parametrize(("capacity", "central", "state", "total"), [
    (2, 60000, 30000, 90000),
    (1, 30000, 15000, 45000),
])
def test_up_report_totals(capacity, central, state, total):
    result = calculate_subsidy("UP", capacity, "residential", "on-grid")
    assert result["central_subsidy"] == central
    assert result["state_additional_subsidy"] == state
    assert result["final_estimated_subsidy"] == total


def test_other_state_gets_central_only():
    result = calculate_subsidy("Maharashtra", 3.9, "residential", "on-grid")
    assert result["central_subsidy"] == 78000
    assert result["state_additional_subsidy"] == 0
    assert result["final_estimated_subsidy"] == 78000


def test_hybrid_without_established_grid_connection_requires_verification():
    result = calculate_subsidy("Uttar Pradesh", 3.9, "residential", "hybrid")
    assert result["eligibility_status"] == "Verify eligibility on the official portal"
    assert result["final_estimated_subsidy"] == 0


def test_missing_location_category_or_configuration_requires_verification():
    for args in (
        (None, 3, "residential", "on-grid"),
        ("Uttar Pradesh", 3, None, "on-grid"),
        ("Uttar Pradesh", 3, "residential", None),
    ):
        result = calculate_subsidy(*args)
        assert result["eligibility_status"] in (
            "Verify eligibility on the official portal",
            "Not eligible for residential CFA",
        )
        assert result["final_estimated_subsidy"] == 0


@pytest.mark.parametrize(("capacity", "central", "state", "combined"), [
    (1, 30000, 15000, 45000),
    (2, 60000, 30000, 90000),
    (3, 78000, 30000, 108000),
    (3.9, 78000, 30000, 108000),
    (5, 78000, 30000, 108000),
])
def test_up_capacity_subsidy_matrix(capacity, central, state, combined):
    result = calculate_subsidy(
        "Lucknow, Uttar Pradesh", capacity, "residential", "on-grid"
    )
    assert result["central_subsidy"] == central
    assert result["state_additional_subsidy"] == state
    assert result["final_estimated_subsidy"] == combined


@pytest.mark.parametrize("category", ["commercial", "industrial"])
def test_non_residential_categories_get_no_cfa(category):
    result = calculate_subsidy("Uttar Pradesh", 3, category, "on-grid")
    assert result["eligible"] is False
    assert result["final_estimated_subsidy"] == 0


def test_saved_report_explicit_values_are_separate_from_battery():
    report = enrich_saved_report_financials({
        "address": "Lucknow, Uttar Pradesh",
        "system_size": 3.9,
        "system_cost": 250000,
        "battery_kwh": 8,
        "battery_cost": 40000,
        "monthly_savings": 5000,
        "extras": {
            "consumer_category": "residential",
            "system_configuration": "on-grid",
            "grid_connected": True,
            "state": "Uttar Pradesh",
        },
    })
    assert report["central_subsidy_amount"] == 78000
    assert report["state_subsidy_amount"] == 30000
    assert report["total_estimated_subsidy"] == 108000
    assert report["net_investment"] == 182000


def test_missing_saved_report_fields_name_exact_input():
    result = calculate_subsidy(None, 3, None, None)
    assert "state" in result["explanation"]
    assert "consumer category" in result["explanation"]
    assert "system configuration" in result["explanation"]
