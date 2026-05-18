# Input: 0005 版本数据库结构与 Alembic upgrade/downgrade 调用  |  Output: app_study_settings 单例表和默认种子行
# Output: 落地全局 daily_new_limit 与 daily_review_limit，供 session 调度和设置页共用
# Role: 这是把学习设置从硬编码转成后端可持久化配置的迁移脚本
# Use: 只应通过 Alembic 执行；业务层默认约定单例主键为 1，改动时要同步 service
"""global study settings

Revision ID: 0006_global_study_settings
Revises: 0005_learning_event_core_loop
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_global_study_settings"
down_revision = "0005_learning_event_core_loop"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_study_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("daily_new_limit", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("daily_review_limit", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.execute(
        sa.text(
            "INSERT INTO app_study_settings (id, daily_new_limit, daily_review_limit, created_at, updated_at) "
            "VALUES (1, 20, 100, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )


def downgrade():
    op.drop_table("app_study_settings")
