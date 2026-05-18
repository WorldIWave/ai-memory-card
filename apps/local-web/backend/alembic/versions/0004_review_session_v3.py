# Input: 0003 版本数据库结构与 Alembic upgrade/downgrade 调用  |  Output: 复习 session v3 所需表、列与索引
# Output: 为 cardreviewstate、review_log 和 review_session 补齐同日复习与撤销链路的持久化结构
# Role: 这是把旧单次 submit 流程扩展成 session v3 核心数据模型的迁移脚本
# Use: 只应通过 Alembic 执行；修改字段时要同步 review/session 相关 schema、service 和测试
"""review session v3

Revision ID: 0004_review_session_v3
Revises: 0003_folder_and_review_log
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_review_session_v3"
down_revision = "0003_folder_and_review_log"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
    if not _has_column(table_name, column_name):
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def upgrade():
    _add_column_if_missing("cardreviewstate", "learning_state", "learning_state TEXT NOT NULL DEFAULT 'new'")
    _add_column_if_missing("cardreviewstate", "learning_step", "learning_step INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing("cardreviewstate", "session_due_at", "session_due_at DATETIME")
    _add_column_if_missing(
        "cardreviewstate",
        "session_repeats_today",
        "session_repeats_today INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "cardreviewstate",
        "hard_attempts_today",
        "hard_attempts_today INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing("cardreviewstate", "last_session_date", "last_session_date DATE")

    _add_column_if_missing("review_log", "session_id", "session_id TEXT")
    _add_column_if_missing("review_log", "trigger_type", "trigger_type TEXT NOT NULL DEFAULT 'scheduled'")
    _add_column_if_missing("review_log", "state_before", "state_before JSON")
    _add_column_if_missing("review_log", "state_after", "state_after JSON")
    _add_column_if_missing("review_log", "is_undone", "is_undone BOOLEAN NOT NULL DEFAULT 0")
    _add_column_if_missing("review_log", "undone_at", "undone_at DATETIME")
    if not _has_index("review_log", "ix_review_log_session_id"):
        op.create_index("ix_review_log_session_id", "review_log", ["session_id"])

    if not _has_table("review_session"):
        op.create_table(
            "review_session",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("session_date", sa.Date(), nullable=False),
            sa.Column("scope", sa.Text(), nullable=False),
            sa.Column("deck_id", sa.Integer(), sa.ForeignKey("deck.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        )


def downgrade():
    op.drop_table("review_session")
    op.drop_index("ix_review_log_session_id", table_name="review_log")
    with op.batch_alter_table("review_log") as batch_op:
        batch_op.drop_column("undone_at")
        batch_op.drop_column("is_undone")
        batch_op.drop_column("state_after")
        batch_op.drop_column("state_before")
        batch_op.drop_column("trigger_type")
        batch_op.drop_column("session_id")
    with op.batch_alter_table("cardreviewstate") as batch_op:
        batch_op.drop_column("last_session_date")
        batch_op.drop_column("hard_attempts_today")
        batch_op.drop_column("session_repeats_today")
        batch_op.drop_column("session_due_at")
        batch_op.drop_column("learning_step")
        batch_op.drop_column("learning_state")
