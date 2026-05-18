# Input: 空数据库  |  Output: 创建 deck、card、cardreviewstate 三张核心表
# Role: 初始迁移版本，建立整个应用的基础表结构，down_revision=None 表示链头
# Note: 此版本不含 card.deleted_at（由 0002 补充）和 folder 表（由 0003 补充）
# Usage: alembic upgrade 0001_initial_schema 或随 upgrade head 链式执行
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deck",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("default_scheduler_type", sa.String(), nullable=False, server_default="sm2_basic"),
        sa.Column("visibility", sa.String(), nullable=False, server_default="normal"),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "card",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("deck.id"), nullable=False),
        sa.Column("knowledge_unit_ref_id", sa.Integer(), nullable=True),
        sa.Column("card_type", sa.String(), nullable=False),
        sa.Column("front", sa.String(), nullable=False),
        sa.Column("back", sa.String(), nullable=False),
        sa.Column("hint", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("render_format", sa.String(), nullable=False, server_default="markdown"),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("ai_lock_status", sa.String(), nullable=False, server_default="user_locked"),
        sa.Column("last_ai_task_id", sa.Integer(), nullable=True),
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_card_deck_id", "card", ["deck_id"])
    op.create_index("ix_card_knowledge_unit_ref_id", "card", ["knowledge_unit_ref_id"])
    op.create_index("ix_card_last_ai_task_id", "card", ["last_ai_task_id"])

    op.create_table(
        "cardreviewstate",
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("card.id"), primary_key=True),
        sa.Column("scheduler_type", sa.String(), nullable=False, server_default="sm2_basic"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("interval_days", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("repetition_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("next_due_at", sa.DateTime(), nullable=True),
        sa.Column("stability_score", sa.Float(), nullable=True),
        sa.Column("difficulty_score", sa.Float(), nullable=True),
        sa.Column("scheduler_state_blob", sa.JSON(), nullable=False),
        sa.Column("last_scheduler_decision_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("cardreviewstate")
    op.drop_index("ix_card_last_ai_task_id", table_name="card")
    op.drop_index("ix_card_knowledge_unit_ref_id", table_name="card")
    op.drop_index("ix_card_deck_id", table_name="card")
    op.drop_table("card")
    op.drop_table("deck")
