# Input: 0002 迁移后的数据库  |  Output: 新增 folder 表、review_log 表，deck 增加 folder_id
# Role: 第三版迁移，引入文件夹组织结构和复习历史记录，支撑 Library 多级管理
# Note: upgrade 使用原生 SQL（SQLite 兼容），并预插入 id=1 的默认文件夹
# Usage: alembic upgrade 0003_folder_and_review_log 或随 upgrade head 链式执行
"""folder and review_log tables

Revision ID: 0003_folder_and_review_log
Revises: 0002_soft_delete_and_system_meta
Create Date: 2026-04-13
"""
from alembic import op

revision = "0003_folder_and_review_log"
down_revision = "0002_soft_delete_and_system_meta"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE folder (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("INSERT INTO folder (id, name) VALUES (1, '默认文件夹')")
    op.execute("ALTER TABLE deck ADD COLUMN folder_id INTEGER DEFAULT 1")
    op.execute("""
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY,
            card_id INTEGER NOT NULL REFERENCES card(id),
            grade TEXT NOT NULL,
            interval_days REAL,
            ease_factor REAL,
            reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        )
    """)


def downgrade():
    op.drop_table("review_log")
    op.drop_column("deck", "folder_id")
    op.drop_table("folder")
