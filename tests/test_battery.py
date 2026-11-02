import pytest

from app.services.battery_service import battery_cost, recommend_battery_capacity


def test_no_backup_recommends_zero():
    result = recommend_battery_capacity(needs_backup=False)
    assert result["recommended_kwh"] == 0


@pytest.mark.parametrize("load,hours,expected", [(1, 5, 10), (2, 4, 10)])
def test_load_and_duration_sizing(load, hours, expected):
    result = recommend_battery_capacity(needs_backup=True, essential_load_kw=load,
                                        backup_hours=hours, technology="lfp")
    assert result["recommended_kwh"] == expected


def test_different_durations_change_capacity():
    short = recommend_battery_capacity(True, 1, 2, "lfp")
    long = recommend_battery_capacity(True, 1, 5, "lfp")
    assert long["recommended_kwh"] > short["recommended_kwh"]


def test_technology_assumptions_change_capacity():
    lfp = recommend_battery_capacity(True, 2, 4, "lfp")
    lead = recommend_battery_capacity(True, 2, 4, "lead-acid")
    assert lead["recommended_kwh"] > lfp["recommended_kwh"]


@pytest.mark.parametrize("load,hours", [(None, 5), (-1, 5), (1, -2), ("bad", 5)])
def test_invalid_inputs_are_rejected(load, hours):
    with pytest.raises(ValueError):
        recommend_battery_capacity(True, load, hours, "lfp")


def test_solar_kw_does_not_select_battery():
    assert recommend_battery_capacity(False)["recommended_kwh"] == 0


def test_lfp_cost_range_is_capacity_based():
    small = battery_cost(5, "lfp")
    large = battery_cost(10, "lfp")
    assert small["minimum_cost"] == 75000
    assert small["maximum_cost"] == 95000
    assert large["minimum_cost"] > small["minimum_cost"]


def test_non_lfp_requires_vendor_quote():
    assert battery_cost(10, "nmc")["vendor_quote_required"] is True
