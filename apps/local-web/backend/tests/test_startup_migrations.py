# Input: app.main 模块、alembic command、SQLite 文件系统  |  Output: 无（pytest 断言副作用）
# Role: 验证启动迁移的重试逻辑、错误传播和延迟建表行为
# Note: 使用 monkeypatch 替换 alembic.command.upgrade 和 time.sleep，避免真实 IO
# Usage: pytest tests/test_startup_migrations.py
from __future__ import annotations

from importlib import import_module, reload
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.runtime_paths import RuntimePaths
import app.main as main_module


def test_run_startup_migrations_retries_once_for_sqlite_already_exists_race(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_upgrade(config, revision: str) -> None:
        calls.append(config.get_main_option("sqlalchemy.url"))
        if len(calls) == 1:
            raise sqlite3.OperationalError("table deck already exists")

    monkeypatch.setattr(main_module.command, "upgrade", fake_upgrade)
    monkeypatch.setattr(main_module.time, "sleep", lambda _seconds: None)

    main_module.run_startup_migrations()

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0].startswith("sqlite:///")


def test_run_startup_migrations_propagates_unrelated_operational_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_upgrade(config, revision: str) -> None:
        raise sqlite3.OperationalError("database disk image is malformed")

    monkeypatch.setattr(main_module.command, "upgrade", fake_upgrade)
    monkeypatch.setattr(main_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(sqlite3.OperationalError, match="database disk image is malformed"):
        main_module.run_startup_migrations()


def test_session_import_does_not_create_schema_before_startup_migrations(monkeypatch: pytest.MonkeyPatch) -> None:
    scratch_dir = Path(tempfile.mkdtemp(prefix="startup-race-", dir=Path.cwd()))
    database_path = scratch_dir / "startup-race.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    monkeypatch.setenv("LMCA_DATABASE_URL", database_url)
    get_settings.cache_clear()

    session_module = sys.modules.get("app.db.session")
    if session_module is None:
        session_module = import_module("app.db.session")
    else:
        session_module = reload(session_module)

    try:
        assert Path(session_module.engine.url.database).resolve() == database_path.resolve()
        assert not database_path.exists()
    finally:
        monkeypatch.delenv("LMCA_DATABASE_URL", raising=False)
        get_settings.cache_clear()
        reload(session_module)
        shutil.rmtree(scratch_dir, ignore_errors=True)


def test_lifespan_creates_runtime_directories_before_startup_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scratch_dir = Path(tempfile.mkdtemp(prefix="startup-runtime-dirs-", dir=Path.cwd()))
    app_data_dir = scratch_dir / "desktop-runtime"
    database_path = app_data_dir / "data" / "configured.db"
    log_dir = scratch_dir / "configured-logs"
    cache_dir = scratch_dir / "configured-cache"
    observed: dict[str, bool] = {}

    monkeypatch.setenv("LMCA_APP_DATA_DIR", str(app_data_dir))
    monkeypatch.setenv("LMCA_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("LMCA_LOG_DIR", str(log_dir))
    monkeypatch.setenv("LMCA_CACHE_DIR", str(cache_dir))
    get_settings.cache_clear()

    def fake_run_startup_migrations() -> None:
        runtime_paths = RuntimePaths.from_settings(get_settings())
        observed.update(
            {
                "app_data_dir": runtime_paths.app_data_dir.exists(),
                "data_dir": runtime_paths.data_dir.exists(),
                "backup_dir": runtime_paths.backup_dir.exists(),
                "log_dir": runtime_paths.log_dir.exists(),
                "cache_dir": runtime_paths.cache_dir.exists(),
                "temp_dir": runtime_paths.temp_dir.exists(),
            }
        )

    monkeypatch.setattr(main_module, "run_startup_migrations", fake_run_startup_migrations)

    try:
        with TestClient(main_module.app):
            pass
    finally:
        monkeypatch.delenv("LMCA_APP_DATA_DIR", raising=False)
        monkeypatch.delenv("LMCA_DATABASE_URL", raising=False)
        monkeypatch.delenv("LMCA_LOG_DIR", raising=False)
        monkeypatch.delenv("LMCA_CACHE_DIR", raising=False)
        get_settings.cache_clear()
        shutil.rmtree(scratch_dir, ignore_errors=True)

    assert observed == {
        "app_data_dir": True,
        "data_dir": True,
        "backup_dir": True,
        "log_dir": True,
        "cache_dir": True,
        "temp_dir": True,
    }
