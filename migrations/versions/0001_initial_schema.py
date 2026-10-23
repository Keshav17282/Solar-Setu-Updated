"""Create the Solar Setu schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "user_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("address", sa.String(length=512), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("polygon_geojson", sa.JSON(), nullable=True),
        sa.Column("obstructions_geojson", sa.JSON(), nullable=True),
        sa.Column("system_size", sa.Float(), nullable=False),
        sa.Column("annual_generation", sa.Float(), nullable=False),
        sa.Column("monthly_data", sa.JSON(), nullable=True),
        sa.Column("roof_area_sqm", sa.Float(), nullable=True),
        sa.Column("obstructed_area_sqm", sa.Float(), nullable=True),
        sa.Column("usable_area_sqm", sa.Float(), nullable=True),
        sa.Column("system_cost", sa.Float(), nullable=True),
        sa.Column("subsidy_amount", sa.Float(), nullable=True),
        sa.Column("net_investment", sa.Float(), nullable=True),
        sa.Column("monthly_savings", sa.Float(), nullable=True),
        sa.Column("co2_reduction_tons", sa.Float(), nullable=True),
        sa.Column("irradiance_source", sa.String(length=32), nullable=True),
        sa.Column("orientation_deg", sa.Float(), nullable=True),
        sa.Column("orientation_label", sa.String(length=32), nullable=True),
        sa.Column("orientation_factor", sa.Float(), nullable=True),
        sa.Column("recommended_tilt_deg", sa.Float(), nullable=True),
        sa.Column("battery_kwh", sa.Float(), nullable=True),
        sa.Column("battery_cost", sa.Float(), nullable=True),
        sa.Column("specific_yield", sa.Float(), nullable=True),
        sa.Column("capacity_factor", sa.Float(), nullable=True),
        sa.Column("lcoe", sa.Float(), nullable=True),
        sa.Column("lifetime_kwh", sa.Float(), nullable=True),
        sa.Column("self_consumption_frac", sa.Float(), nullable=True),
        sa.Column("payback_years", sa.Float(), nullable=True),
        sa.Column("extras", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_user_locations_user_id", "user_locations", ["user_id"], unique=False)
    op.create_table(
        "solar_providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("service_regions", sa.JSON(), nullable=False),
        sa.Column("provider_type", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "solar_solutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("system_size_kw", sa.Float(), nullable=False),
        sa.Column("panel_brand", sa.String(length=120), nullable=True),
        sa.Column("panel_model", sa.String(length=160), nullable=True),
        sa.Column("panel_type", sa.String(length=80), nullable=True),
        sa.Column("panel_efficiency", sa.Float(), nullable=True),
        sa.Column("number_of_panels", sa.Integer(), nullable=True),
        sa.Column("inverter_brand", sa.String(length=120), nullable=True),
        sa.Column("inverter_model", sa.String(length=160), nullable=True),
        sa.Column("inverter_type", sa.String(length=80), nullable=True),
        sa.Column("panel_warranty_years", sa.Float(), nullable=True),
        sa.Column("performance_warranty_years", sa.Float(), nullable=True),
        sa.Column("inverter_warranty_years", sa.Float(), nullable=True),
        sa.Column("installation_included", sa.Boolean(), nullable=True),
        sa.Column("mounting_included", sa.Boolean(), nullable=True),
        sa.Column("amc_available", sa.Boolean(), nullable=True),
        sa.Column("financing_available", sa.Boolean(), nullable=True),
        sa.Column("indicative_price_min", sa.Float(), nullable=True),
        sa.Column("indicative_price_max", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("data_status", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("last_updated", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["solar_providers.id"]),
    )
    op.create_index("ix_solar_solutions_provider_id", "solar_solutions", ["provider_id"], unique=False)
    op.create_table(
        "saved_comparisons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=True),
        sa.Column("solution_ids", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["user_locations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_saved_comparisons_user_id", "saved_comparisons", ["user_id"], unique=False)
    op.create_table(
        "tariff_table",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("utility_name", sa.String(length=128), nullable=False),
        sa.Column("rate_per_kwh", sa.Float(), nullable=False),
    )
    op.create_table(
        "subsidy_scheme",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("min_kw", sa.Float(), nullable=False),
        sa.Column("max_kw", sa.Float(), nullable=False),
        sa.Column("subsidy_amount", sa.Float(), nullable=False),
    )


def downgrade():
    op.drop_table("subsidy_scheme")
    op.drop_table("tariff_table")
    op.drop_index("ix_saved_comparisons_user_id", table_name="saved_comparisons")
    op.drop_table("saved_comparisons")
    op.drop_index("ix_solar_solutions_provider_id", table_name="solar_solutions")
    op.drop_table("solar_solutions")
    op.drop_table("solar_providers")
    op.drop_index("ix_user_locations_user_id", table_name="user_locations")
    op.drop_table("user_locations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
