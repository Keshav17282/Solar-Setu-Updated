"""Add installer marketplace entities.

Revision ID: 0002_installer_marketplace
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_installer_marketplace"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "solar_companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("vendor_code", sa.String(length=64), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("district", sa.String(length=128), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("directory_approved_at", sa.DateTime(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("manually_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("vendor_code", name="uq_solar_companies_vendor_code"),
    )
    op.create_index("ix_solar_companies_name", "solar_companies", "name", unique=False)
    op.create_index("ix_solar_companies_district", "solar_companies", "district", unique=False)
    op.create_index("ix_solar_companies_verification_status", "solar_companies", "verification_status", unique=False)

    op.create_table("company_service_areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("solar_companies.id"), nullable=False),
        sa.Column("district", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=True),
    )
    op.create_table("company_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("solar_companies.id"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("brand", sa.String(length=160), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("technology", sa.String(length=120), nullable=True),
        sa.Column("specifications", sa.JSON(), nullable=True),
        sa.Column("product_warranty_years", sa.Float(), nullable=True),
        sa.Column("performance_warranty_years", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
    )
    op.create_table("company_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("solar_companies.id"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_record_id", sa.String(length=128), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_table("quotation_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("solar_companies.id"), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=False),
        sa.Column("mobile", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("installation_address", sa.Text(), nullable=False),
        sa.Column("district", sa.String(length=128), nullable=True),
        sa.Column("system_size_kw", sa.Float(), nullable=True),
        sa.Column("battery_required", sa.Boolean(), nullable=False),
        sa.Column("monthly_bill", sa.Float(), nullable=True),
        sa.Column("preferred_timeline", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("contact_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_company_service_areas_company_id", "company_service_areas", "company_id")
    op.create_index("ix_company_products_company_id", "company_products", "company_id")
    op.create_index("ix_company_verifications_company_id", "company_verifications", "company_id")
    op.create_index("ix_quotation_requests_company_id", "quotation_requests", "company_id")


def downgrade():
    for table in ("quotation_requests", "company_verifications", "company_products", "company_service_areas", "solar_companies"):
        op.drop_table(table)
