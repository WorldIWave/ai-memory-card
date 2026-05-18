# Input: 0001_initial_schema 迁移后的数据库  |  Output: card 表新增 deleted_at 列
# Role: 第二版迁移，为 Card 启用软删除能力（deleted_at 为 NULL 表示未删除）
# Note: 文件名保留了更广泛的 system_meta 预留空间，当前仅实现 deleted_at 一列
# Usage: alembic upgrade 0002_soft_delete_and_system_meta 或随 upgrade head 链式执行
from alembic import op
import sqlalchemy as sa

# This revision currently adds only card.deleted_at; the broader filename is
# reserved for the rest of the phase-1 system metadata work.
revision = "0002_soft_delete_and_system_meta"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("card", "deleted_at"):
        op.add_column("card", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    if _has_column("card", "deleted_at"):
        op.drop_column("card", "deleted_at")
