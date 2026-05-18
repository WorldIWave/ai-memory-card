from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import shutil
import tempfile

from app.core.config import Settings
from app.core.logging_setup import configure_runtime_logging


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"


def _matching_handlers(log_path: Path) -> list[RotatingFileHandler]:
    handlers: list[RotatingFileHandler] = []
    for handler in logging.getLogger().handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path:
            handlers.append(handler)
    return handlers


def _temp_runtime_dir() -> Path:
    temp_root = Path.cwd() / ".pytest-temp"
    temp_root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=temp_root))


def test_configure_runtime_logging_writes_rotating_log_file() -> None:
    base_dir = _temp_runtime_dir()
    try:
        database_path = base_dir / "app-data" / "data" / "runtime.db"
        settings = Settings(database_url=_sqlite_url(database_path))

        log_path = configure_runtime_logging(settings)
        logger = logging.getLogger("tests.runtime.logging")
        logger.setLevel(logging.INFO)
        logger.info("runtime log smoke test")

        for handler in _matching_handlers(log_path):
            handler.flush()

        assert log_path.exists()
        assert "runtime log smoke test" in log_path.read_text(encoding="utf-8")
    finally:
        for handler in _matching_handlers(base_dir / "app-data" / "logs" / "app.log"):
            logging.getLogger().removeHandler(handler)
            handler.close()
        shutil.rmtree(base_dir, ignore_errors=True)


def test_configure_runtime_logging_does_not_stack_duplicate_handlers() -> None:
    base_dir = _temp_runtime_dir()
    try:
        database_path = base_dir / "app-data" / "data" / "runtime.db"
        settings = Settings(database_url=_sqlite_url(database_path))

        log_path = configure_runtime_logging(settings)
        configure_runtime_logging(settings)

        assert len(_matching_handlers(log_path)) == 1
    finally:
        for handler in _matching_handlers(base_dir / "app-data" / "logs" / "app.log"):
            logging.getLogger().removeHandler(handler)
            handler.close()
        shutil.rmtree(base_dir, ignore_errors=True)
