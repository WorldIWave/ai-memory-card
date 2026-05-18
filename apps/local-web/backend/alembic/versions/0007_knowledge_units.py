# Input: 0006 database schema | Output: knowledge_unit table for local AI-generated unit storage
# Role: Persists RAG knowledge units so generated cards can reference their source concepts
# Note: card.knowledge_unit_ref_id already exists from the initial schema; this migration adds the target table
# Usage: Executed by alembic upgrade head during backend startup
"""knowledge units

Revision ID: 0007_knowledge_units
Revises: 0006_global_study_settings
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_knowledge_units"
down_revision = "0006_global_study_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_unit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("deck.id"), nullable=False),
        sa.Column("provider_unit_id", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False, server_default=""),
        sa.Column("source_document", sa.String(), nullable=True),
        sa.Column("source_span", sa.JSON(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_knowledge_unit_deck_id", "knowledge_unit", ["deck_id"])
    op.create_index("ix_knowledge_unit_provider_unit_id", "knowledge_unit", ["provider_unit_id"])


def downgrade():
    op.drop_index("ix_knowledge_unit_provider_unit_id", table_name="knowledge_unit")
    op.drop_index("ix_knowledge_unit_deck_id", table_name="knowledge_unit")
    op.drop_table("knowledge_unit")
