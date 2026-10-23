def calculate_carbon_impact(
    annual_generation_kwh,
    grid_emission_factor
):
    annual_generation_mwh = annual_generation_kwh / 1000

    co2_avoided_tonnes = (
        annual_generation_mwh * grid_emission_factor
    )

    return {
        "co2_avoided_tonnes": round(co2_avoided_tonnes, 3),
        "credit_eligibility": "Not automatically eligible"
    }