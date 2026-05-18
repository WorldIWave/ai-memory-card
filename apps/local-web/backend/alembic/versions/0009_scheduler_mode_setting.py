# Input: app_study_settings table from 0008 | Output: scheduler_mode persisted setting column
# Role: Adds the global scheduler mode switch for traditional vs AI/RL scheduling
# Note: Existing rows are normalized to traditional so the application always has a concrete mode
# Usage: Executed by alembic upgrade head during backend startup
"""scheduler mode setting

Revision ID: 0009_scheduler_mode_setting
Revises: 0008_onboarding_seed_state
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_scheduler_mode_setting"
down_revision = "0008_onboarding_seed_state"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_study_settings",
        sa.Column("scheduler_mode", sa.String(), nullable=False, server_default="traditional"),
    )
    op.execute(
        sa.text(
            "UPDATE app_study_settings "
            "SET scheduler_mode = 'traditional' "
            "WHERE scheduler_mode IS NULL OR scheduler_mode = ''"
        )
    )


def downgrade():
    op.drop_column("app_study_settings", "scheduler_mode")
