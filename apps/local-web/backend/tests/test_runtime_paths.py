from pathlib import Path
import shutil
import tempfile

import pytest

from app.core.config import Settings
from app.core.errors import ValidationError
from app.core.runtime_paths import RuntimePaths
from app.services.backup_service import BackupService
from app.services.diagnostics_service import DiagnosticsService


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


@pytest.fixture()
def runtime_tmp_dir() -> Path:
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_runtime_paths_uses_explicit_app_data_dir_when_database_matches(runtime_tmp_dir: Path) -> None:
    app_data_dir = runtime_tmp_dir / "app-data"
    data_dir = app_data_dir / "data"
    database_path = data_dir / "runtime.db"
    log_dir = runtime_tmp_dir / "logs"
    cache_dir = runtime_tmp_dir / "cache"
    settings = Settings(
        database_url=_sqlite_url(database_path),
        app_data_dir=str(app_data_dir),
        log_dir=str(log_dir),
        cache_dir=str(cache_dir),
    )

    paths = RuntimePaths.from_settings(settings)

    assert paths.app_data_dir == app_data_dir.resolve()
    assert paths.data_dir == data_dir.resolve()
    assert paths.database_path == database_path.resolve()
    assert paths.backup_dir == (app_data_dir / "backups").resolve()
    assert paths.log_dir == log_dir.resolve()
    assert paths.cache_dir == cache_dir.resolve()
    assert paths.temp_dir == (app_data_dir / "temp").resolve()


def test_runtime_paths_rejects_explicit_app_data_dir_that_does_not_match_database(runtime_tmp_dir: Path) -> None:
    app_data_dir = runtime_tmp_dir / "app-data"
    other_database_path = runtime_tmp_dir / "other" / "runtime.db"
    settings = Settings(
        database_url=_sqlite_url(other_database_path),
        app_data_dir=str(app_data_dir),
    )

    with pytest.raises(ValueError, match="live under"):
        RuntimePaths.from_settings(settings)


def test_runtime_paths_falls_back_to_data_parent_for_database_under_data_dir(runtime_tmp_dir: Path) -> None:
    database_path = runtime_tmp_dir / "app-data" / "data" / "ai_memory_card.db"
    settings = Settings(database_url=_sqlite_url(database_path))

    paths = RuntimePaths.from_settings(settings)

    assert paths.app_data_dir == (runtime_tmp_dir / "app-data").resolve()
    assert paths.data_dir == (runtime_tmp_dir / "app-data" / "data").resolve()
    assert paths.database_path == database_path.resolve()
    assert paths.backup_dir == (runtime_tmp_dir / "app-data" / "backups").resolve()
    assert paths.log_dir == (runtime_tmp_dir / "app-data" / "logs").resolve()
    assert paths.cache_dir == (runtime_tmp_dir / "app-data" / "cache").resolve()
    assert paths.temp_dir == (runtime_tmp_dir / "app-data" / "temp").resolve()


def test_runtime_paths_falls_back_to_database_parent_when_not_under_data_dir(runtime_tmp_dir: Path) -> None:
    database_path = runtime_tmp_dir / "db" / "ai_memory_card.db"
    settings = Settings(database_url=_sqlite_url(database_path))

    paths = RuntimePaths.from_settings(settings)

    assert paths.app_data_dir == (runtime_tmp_dir / "db").resolve()
    assert paths.data_dir == (runtime_tmp_dir / "db" / "data").resolve()
    assert paths.database_path == database_path.resolve()
    assert paths.backup_dir == (runtime_tmp_dir / "db" / "backups").resolve()
    assert paths.log_dir == (runtime_tmp_dir / "db" / "logs").resolve()
    assert paths.cache_dir == (runtime_tmp_dir / "db" / "cache").resolve()
    assert paths.temp_dir == (runtime_tmp_dir / "db" / "temp").resolve()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:pass@localhost/db",
        "sqlite://",
        "sqlite:///:memory:",
    ],
)
def test_runtime_paths_rejects_unsupported_database_urls(database_url: str) -> None:
    settings = Settings(database_url=database_url)

    with pytest.raises(ValueError, match="local SQLite"):
        RuntimePaths.from_settings(settings)


def test_diagnostics_service_maps_unsupported_database_urls_to_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.diagnostics_service.get_settings",
        lambda: Settings(database_url="postgresql://user:pass@localhost/db"),
    )
    service = DiagnosticsService()

    with pytest.raises(ValidationError, match="local SQLite"):
        service.runtime_snapshot()


def test_backup_service_maps_mismatched_app_data_dir_to_specific_validation_error(
    monkeypatch: pytest.MonkeyPatch,
    runtime_tmp_dir: Path,
) -> None:
    app_data_dir = runtime_tmp_dir / "app-data"
    other_database_path = runtime_tmp_dir / "other" / "runtime.db"
    monkeypatch.setattr(
        "app.services.backup_service.get_settings",
        lambda: Settings(
            database_url=_sqlite_url(other_database_path),
            app_data_dir=str(app_data_dir),
        ),
    )
    service = BackupService()

    with pytest.raises(ValidationError, match="Configured app_data_dir"):
        service.database_path()
