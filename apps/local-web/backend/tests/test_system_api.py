# Input: 真实 SQLite 数据库、FastAPI app  |  Output: 无（pytest 断言副作用）
# Role: 集成测试 /api/system/* 端点（runtime、backup、restore、diagnostics、logs）
# Note: 每个测试通过 clean_system_artifacts fixture 清理备份/日志/锁文件，需真实文件 IO
# Usage: pytest tests/test_system_api.py
from __future__ import annotations

from collections.abc import Generator
from contextlib import closing
import gc
from pathlib import Path, PurePath
import os
import sqlite3
import shutil
import sys
import tempfile
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db import session as session_module
from app.main import app


def _database_path() -> Path:
    url = make_url(get_settings().database_url)
    assert url.database is not None

    database_path = Path(url.database)
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    return database_path


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _backup_dir() -> Path:
    return _database_path().parent / "backups"


def _log_dir() -> Path:
    return _database_path().parent / "logs"


def _lock_path() -> Path:
    return _database_path().parent / ".system-operation.lock"


def _dispose_database_engine() -> None:
    if session_module.get_engine.cache_info().currsize:
        session_module.get_engine().dispose()
    session_module.get_engine.cache_clear()
    gc.collect()


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Generator[None, None, None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    _dispose_database_engine()


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return

    for attempt in range(10):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            _dispose_database_engine()
            if attempt == 9:
                raise
            time.sleep(0.1)


@pytest.fixture()
def runtime_tmp_dir() -> Generator[Path, None, None]:
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    try:
        yield temp_dir
    finally:
        _dispose_database_engine()
        _remove_tree(temp_dir)


def _create_card(client: TestClient, front: str) -> int:
    deck_id: int | None = None

    decks_response = client.get("/api/decks")
    assert decks_response.status_code == 200
    for deck in decks_response.json():
        if deck["name"] == "System Deck":
            deck_id = deck["id"]
            break

    if deck_id is None:
        deck_response = client.post("/api/decks", json={"name": "System Deck"})
        assert deck_response.status_code == 201
        deck_id = deck_response.json()["id"]

    card_response = client.post(
        "/api/cards",
        json={
            "deck_id": deck_id,
            "card_type": "recall",
            "front": front,
            "back": f"Answer for {front}",
            "render_format": "markdown",
        },
    )
    assert card_response.status_code == 201
    return card_response.json()["id"]


def _write_pre_0002_backup(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            );
            INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema');

            CREATE TABLE deck (
                id INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                description VARCHAR NOT NULL DEFAULT '',
                default_scheduler_type VARCHAR NOT NULL DEFAULT 'sm2_basic',
                visibility VARCHAR NOT NULL DEFAULT 'normal',
                deleted_at DATETIME NULL,
                source_type VARCHAR NOT NULL DEFAULT 'manual',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );

            CREATE TABLE card (
                id INTEGER PRIMARY KEY,
                deck_id INTEGER NOT NULL,
                knowledge_unit_ref_id INTEGER NULL,
                card_type VARCHAR NOT NULL,
                front VARCHAR NOT NULL,
                back VARCHAR NOT NULL,
                hint VARCHAR NULL,
                tags JSON NOT NULL,
                render_format VARCHAR NOT NULL DEFAULT 'markdown',
                sort_order INTEGER NULL,
                source_type VARCHAR NOT NULL DEFAULT 'manual',
                status VARCHAR NOT NULL DEFAULT 'active',
                ai_lock_status VARCHAR NOT NULL DEFAULT 'user_locked',
                last_ai_task_id INTEGER NULL,
                content_version INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY(deck_id) REFERENCES deck (id)
            );

            CREATE INDEX ix_card_deck_id ON card (deck_id);
            CREATE INDEX ix_card_knowledge_unit_ref_id ON card (knowledge_unit_ref_id);
            CREATE INDEX ix_card_last_ai_task_id ON card (last_ai_task_id);

            CREATE TABLE cardreviewstate (
                card_id INTEGER NOT NULL,
                scheduler_type VARCHAR NOT NULL DEFAULT 'sm2_basic',
                state_version INTEGER NOT NULL DEFAULT 1,
                interval_days FLOAT NOT NULL DEFAULT 0.0,
                ease_factor FLOAT NOT NULL DEFAULT 2.5,
                repetition_count INTEGER NOT NULL DEFAULT 0,
                lapses INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at DATETIME NULL,
                next_due_at DATETIME NULL,
                stability_score FLOAT NULL,
                difficulty_score FLOAT NULL,
                scheduler_state_blob JSON NOT NULL,
                last_scheduler_decision_id INTEGER NULL,
                PRIMARY KEY (card_id),
                FOREIGN KEY(card_id) REFERENCES card (id)
            );
            """
        )
        connection.commit()


@pytest.fixture()
def clean_system_artifacts() -> Generator[None, None, None]:
    _dispose_database_engine()
    for path in (_backup_dir(), _log_dir()):
        _remove_tree(path)
    if _lock_path().exists():
        _lock_path().unlink()

    yield

    _dispose_database_engine()
    for path in (_backup_dir(), _log_dir()):
        _remove_tree(path)
    if _lock_path().exists():
        _lock_path().unlink()


def test_runtime_endpoint_returns_paths_and_versions(clean_system_artifacts: None) -> None:
    with TestClient(app) as client:
        response = client.get("/api/system/runtime")

    _dispose_database_engine()

    assert response.status_code == 200
    payload = response.json()
    assert payload["app_name"] == "AI Memory Card Backend"
    assert payload["app_version"] == "0.1.0"
    assert payload["backend_version"] == "0.1.0"
    assert payload["database_path"] == str(_database_path())
    assert payload["backup_dir"] == str(_backup_dir())
    assert payload["log_dir"] == str(_log_dir())
    assert payload["app_data_dir"] == str(_database_path().parent)
    assert payload["cache_dir"] == str(_database_path().parent / "cache")
    assert payload["runtime_mode"] == "development"
    assert "release_channel_url" in payload
    assert payload["python_executable"] == sys.executable
    assert payload["python_version"] == sys.version
    assert PurePath(payload["backend_root"]).parts[-3:] == ("apps", "local-web", "backend")
    assert "backend_port" in payload


def test_runtime_endpoint_surfaces_configured_runtime_dirs(
    clean_system_artifacts: None,
    monkeypatch: pytest.MonkeyPatch,
    runtime_tmp_dir: Path,
) -> None:
    app_data_dir = runtime_tmp_dir / "desktop-runtime"
    database_path = app_data_dir / "data" / "configured.db"
    log_dir = runtime_tmp_dir / "configured-logs"
    cache_dir = runtime_tmp_dir / "configured-cache"
    database_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LMCA_DATABASE_URL", _sqlite_url(database_path))
    monkeypatch.setenv("LMCA_APP_DATA_DIR", str(app_data_dir))
    monkeypatch.setenv("LMCA_LOG_DIR", str(log_dir))
    monkeypatch.setenv("LMCA_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("LMCA_RUNTIME_MODE", "desktop")
    monkeypatch.setenv("LMCA_RELEASE_CHANNEL_URL", "https://updates.example.test/channel.json")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/api/system/runtime")
        deck_response = client.post("/api/decks", json={"name": "Configured Runtime Deck"})

    _dispose_database_engine()

    assert response.status_code == 200
    assert deck_response.status_code == 201
    payload = response.json()
    assert payload["app_data_dir"] == str(app_data_dir.resolve())
    assert payload["database_path"] == str(database_path.resolve())
    assert payload["log_dir"] == str(log_dir.resolve())
    assert payload["cache_dir"] == str(cache_dir.resolve())
    assert payload["runtime_mode"] == "desktop"
    assert payload["release_channel_url"] == "https://updates.example.test/channel.json"
    assert payload["python_executable"] == sys.executable
    assert payload["python_version"] == sys.version

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM deck WHERE name = ?",
            ("Configured Runtime Deck",),
        ).fetchone()

    _dispose_database_engine()

    assert row is not None
    assert row[0] == 1


def test_runtime_endpoint_rejects_mismatched_app_data_dir(
    clean_system_artifacts: None,
    monkeypatch: pytest.MonkeyPatch,
    runtime_tmp_dir: Path,
) -> None:
    database_path = runtime_tmp_dir / "elsewhere" / "configured.db"
    app_data_dir = runtime_tmp_dir / "desktop-runtime"
    database_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LMCA_DATABASE_URL", _sqlite_url(database_path))
    monkeypatch.setenv("LMCA_APP_DATA_DIR", str(app_data_dir))
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/api/system/runtime")

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Configured app_data_dir")


def test_backup_restore_and_listing_round_trip(clean_system_artifacts: None) -> None:
    with TestClient(app) as client:
        _create_card(client, "Before backup")

        backup_response = client.post("/api/system/backup")
        assert backup_response.status_code == 201
        backup_payload = backup_response.json()

        backup_path = Path(backup_payload["path"])
        assert backup_path.exists()
        assert backup_path.name == backup_payload["filename"]

        backups_response = client.get("/api/system/backups")
        assert backups_response.status_code == 200
        backups_payload = backups_response.json()
        assert any(item["filename"] == backup_payload["filename"] for item in backups_payload)

        _create_card(client, "Created after backup")

        restore_response = client.post(
            "/api/system/restore",
            json={"filename": backup_payload["filename"]},
        )
        assert restore_response.status_code == 200
        assert restore_response.json()["restored_from"] == backup_payload["filename"]

        cards_response = client.get("/api/cards")
        assert cards_response.status_code == 200
        fronts = [row["front"] for row in cards_response.json()]

    _dispose_database_engine()

    assert "Before backup" in fronts
    assert "Created after backup" not in fronts


def test_diagnostics_and_log_export_reflect_local_state(clean_system_artifacts: None) -> None:
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    log_path.write_text("startup ok\nbackup ok\n", encoding="utf-8")

    with TestClient(app) as client:
        backup_response = client.post("/api/system/backup")
        assert backup_response.status_code == 201

        diagnostics_response = client.get("/api/system/diagnostics")
        assert diagnostics_response.status_code == 200
        diagnostics_payload = diagnostics_response.json()
        assert diagnostics_payload["database_exists"] is True
        assert diagnostics_payload["backup_count"] >= 1
        assert any(item["name"] == "app.log" for item in diagnostics_payload["log_files"])

        export_response = client.get("/api/system/logs/export")

    _dispose_database_engine()

    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/plain")
    assert "attachment;" in export_response.headers["content-disposition"]
    assert "app.log" in export_response.text
    assert "startup ok" in export_response.text


def test_restore_rejects_path_traversal_filename(clean_system_artifacts: None) -> None:
    with TestClient(app) as client:
        response = client.post("/api/system/restore", json={"filename": "../x.sqlite3"})

    _dispose_database_engine()

    assert response.status_code == 404
    assert response.json()["detail"] == "Backup file not found"


def test_restore_requires_filename(clean_system_artifacts: None) -> None:
    with TestClient(app) as client:
        response = client.post("/api/system/restore", json={})

    _dispose_database_engine()

    assert response.status_code == 422


def test_backup_rejects_malformed_lock_payload_without_reclaiming(clean_system_artifacts: None) -> None:
    lock_path = _lock_path()
    lock_path.write_text("garbage-lock-state", encoding="utf-8")

    with TestClient(app) as client:
        response = client.post("/api/system/backup")

    _dispose_database_engine()

    assert response.status_code == 409
    assert response.json()["detail"] == "System backup or restore already in progress"
    assert lock_path.read_text(encoding="utf-8") == "garbage-lock-state"


def test_backup_rejects_active_lock_owner(clean_system_artifacts: None) -> None:
    lock_path = _lock_path()
    lock_path.write_text(f"pid={os.getpid()}\n", encoding="utf-8")

    with TestClient(app) as client:
        response = client.post("/api/system/backup")

    _dispose_database_engine()

    assert response.status_code == 409
    assert response.json()["detail"] == "System backup or restore already in progress"
    assert lock_path.read_text(encoding="utf-8") == f"pid={os.getpid()}\n"


def test_restore_applies_migrations_immediately(clean_system_artifacts: None) -> None:
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    legacy_backup_path = backup_dir / "legacy-pre-0002.sqlite3"
    _write_pre_0002_backup(legacy_backup_path)

    with TestClient(app) as client:
        restore_response = client.post("/api/system/restore", json={"filename": legacy_backup_path.name})

    _dispose_database_engine()

    assert restore_response.status_code == 200

    with closing(sqlite3.connect(_database_path())) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(card)").fetchall()}
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert "deleted_at" in columns
    assert revision is not None
    assert revision[0] == "0009_scheduler_mode_setting"

