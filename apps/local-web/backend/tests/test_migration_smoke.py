# Input: alembic.ini 配置 + 临时 SQLite 数据库  |  Output: 断言核心表与字段存在
# Role: 冒烟测试，验证 Alembic 迁移脚本能完整创建 deck/card/cardreviewstate 等表
# Note: 每次测试使用独立临时 DB 文件，测试结束后清理；需在 backend 目录运行
# Usage: pytest tests/test_migration_smoke.py，无需预先建库，自动执行 upgrade head
from pathlib import Path
import os
import tempfile

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlmodel import create_engine

from app.core.config import get_settings


def test_initial_migration_creates_core_tables() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    fd, db_path_str = tempfile.mkstemp(prefix="migration_smoke_", suffix=".db", dir=backend_root)
    os.close(fd)
    db_path = Path(db_path_str)
    database_url = f"sqlite:///{db_path.as_posix()}"

    engine = None
    try:
        os.environ["LMCA_DATABASE_URL"] = database_url
        get_settings.cache_clear()

        alembic_ini = backend_root / "alembic.ini"
        config = Config(str(alembic_ini))
        config.set_main_option("script_location", str(backend_root / "alembic"))

        command.upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        card_columns = {column["name"] for column in inspector.get_columns("card")}
        app_study_settings_columns = {
            column["name"] for column in inspector.get_columns("app_study_settings")
        }

        assert {"deck", "card", "cardreviewstate"}.issubset(tables)
        assert "deleted_at" in card_columns
        assert "scheduler_mode" in app_study_settings_columns
    finally:
        if engine is not None:
            engine.dispose()
        get_settings.cache_clear()
        os.environ.pop("LMCA_DATABASE_URL", None)
        if db_path.exists():
            db_path.unlink()


def test_scheduler_mode_migration_backfills_existing_settings_row() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    fd, db_path_str = tempfile.mkstemp(prefix="migration_smoke_", suffix=".db", dir=backend_root)
    os.close(fd)
    db_path = Path(db_path_str)
    database_url = f"sqlite:///{db_path.as_posix()}"

    engine = None
    try:
        os.environ["LMCA_DATABASE_URL"] = database_url
        get_settings.cache_clear()

        alembic_ini = backend_root / "alembic.ini"
        config = Config(str(alembic_ini))
        config.set_main_option("script_location", str(backend_root / "alembic"))

        command.upgrade(config, "0008_onboarding_seed_state")

        engine = create_engine(database_url)
        with engine.begin() as connection:
            before = connection.execute(
                sa.text("SELECT id, daily_new_limit, daily_review_limit FROM app_study_settings WHERE id = 1")
            ).mappings().one()
            assert before["daily_new_limit"] == 20
            assert before["daily_review_limit"] == 100

        engine.dispose()
        engine = None

        command.upgrade(config, "0009_scheduler_mode_setting")

        engine = create_engine(database_url)
        inspector = sa.inspect(engine)
        app_study_settings_columns = {
            column["name"] for column in inspector.get_columns("app_study_settings")
        }
        with engine.begin() as connection:
            after = connection.execute(
                sa.text("SELECT scheduler_mode FROM app_study_settings WHERE id = 1")
            ).mappings().one()

        assert "scheduler_mode" in app_study_settings_columns
        assert after["scheduler_mode"] == "traditional"
    finally:
        if engine is not None:
            engine.dispose()
        get_settings.cache_clear()
        os.environ.pop("LMCA_DATABASE_URL", None)
        if db_path.exists():
            db_path.unlink()
