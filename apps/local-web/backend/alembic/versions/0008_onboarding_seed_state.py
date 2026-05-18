# Input: 0007 database schema | Output: app_seed_state table for one-time first-run seed tracking
# Role: Records which built-in seed flows have already been handled so user-deleted tutorial content stays deleted
# Note: The table stores seed keys, not application settings; service code owns the idempotency semantics
# Usage: Executed by alembic upgrade head during backend startup
"""onboarding seed state

Revision ID: 0008_onboarding_seed_state
Revises: 0007_knowledge_units
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_onboarding_seed_state"
down_revision = "0007_knowledge_units"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_seed_state",
        sa.Column("seed_key", sa.String(), primary_key=True),
        sa.Column("seed_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade():
    op.drop_table("app_seed_state")
