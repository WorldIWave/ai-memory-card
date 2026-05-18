# Input: 0004 版本数据库结构与 Alembic upgrade/downgrade 调用  |  Output: learning_event 表及其查询索引
# Output: 为笔记、报错、后续学习事件时间线提供统一事件存储结构
# Role: 这是把“独立学习事件”纳入核心学习闭环的数据层迁移脚本
# Use: 只应通过 Alembic 执行；新增 event_type 或查询模式时要同步 service/schema/前端活动面板
"""learning event core loop

Revision ID: 0005_learning_event_core_loop
Revises: 0004_review_session_v3
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_learning_event_core_loop"
down_revision = "0004_review_session_v3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "learning_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("card_id", sa.Integer(), sa.ForeignKey("card.id"), nullable=False),
        sa.Column("deck_id", sa.Integer(), sa.ForeignKey("deck.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learning_event_card_id", "learning_event", ["card_id"])
    op.create_index("ix_learning_event_deck_id", "learning_event", ["deck_id"])
    op.create_index("ix_learning_event_event_type", "learning_event", ["event_type"])
    op.create_index("ix_learning_event_created_at", "learning_event", ["created_at"])


def downgrade():
    op.drop_index("ix_learning_event_created_at", table_name="learning_event")
    op.drop_index("ix_learning_event_event_type", table_name="learning_event")
    op.drop_index("ix_learning_event_deck_id", table_name="learning_event")
    op.drop_index("ix_learning_event_card_id", table_name="learning_event")
    op.drop_table("learning_event")
