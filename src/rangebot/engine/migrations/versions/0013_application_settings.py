"""Add backend-owned application settings."""

from alembic import op
import sqlalchemy as sa


revision = "0013_application_settings"
down_revision = "0012_exchange_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("ui_language", sa.String(length=8), nullable=False),
        sa.Column("dashboard_layout_json", sa.Text(), nullable=False),
        sa.Column("dashboard_filters_json", sa.Text(), nullable=False),
        sa.Column("sidebar_preferences_json", sa.Text(), nullable=False),
        sa.Column("application_preferences_json", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("application_settings")
