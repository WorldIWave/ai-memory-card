# Input: 无外部参数（读取 settings.database_url）  |  Output: 备份元数据 dict 或还原确认 dict
# Role: SQLite 备份/还原服务，使用线程锁+文件锁保证操作互斥，还原后自动执行 Alembic 迁移
# Note: 仅支持本地 SQLite 文件；还原流程先暂存再原子替换，失败时自动清理暂存文件
# Usage: BackupService().create_backup() / .restore_backup(filename) / .list_backups()
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.runtime_paths import RuntimePaths
from app.db import session as session_module

_OPERATION_LOCK = threading.Lock()
_OPERATION_LOCK_FILENAME = ".system-operation.lock"
_SQLITE_BUSY_TIMEOUT_MS = 5_000


class BackupService:
    def database_path(self) -> Path:
        try:
            return RuntimePaths.from_settings(get_settings()).database_path
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def backup_dir(self) -> Path:
        try:
            return RuntimePaths.from_settings(get_settings()).backup_dir
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def list_backups(self) -> list[dict[str, Any]]:
        backup_dir = self.backup_dir()
        if not backup_dir.exists():
            return []
        return [
            self._backup_metadata(path)
            for path in sorted(
                backup_dir.glob("*.sqlite3"),
                key=lambda p: (p.stat().st_mtime, p.name),
                reverse=True,
            )
        ]

    def create_backup(self) -> dict[str, Any]:
        database_path = self.database_path()
        if not database_path.exists():
            raise NotFoundError("Database file")

        backup_dir = self.backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)

        created_at = datetime.now(timezone.utc)
        timestamp = created_at.strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"ai-memory-card-{timestamp}.sqlite3"
        counter = 1
        while backup_path.exists():
            backup_path = backup_dir / f"ai-memory-card-{timestamp}-{counter}.sqlite3"
            counter += 1

        with self._operation_guard():
            self._copy_database(
                source_path=database_path,
                target_path=backup_path,
                coordination_path=database_path,
                coordination_lock_mode="IMMEDIATE",
            )
        return self._backup_metadata(backup_path)

    def restore_backup(self, filename: str) -> dict[str, str]:
        backup_path = self._resolve_backup_path(filename)
        database_path = self.database_path()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = self.backup_dir() / f".restore-{os.getpid()}-{database_path.name}"

        with self._operation_guard():
            try:
                self._copy_database(source_path=backup_path, target_path=staging_path)
                self._probe_database_lock(database_path, lock_mode="EXCLUSIVE")
                self._replace_database_file(staging_path, database_path)
                self._run_migrations(database_path)
                session_module.get_engine().dispose()
            finally:
                if staging_path.exists():
                    staging_path.unlink()

        return {"restored_from": backup_path.name, "database_path": str(database_path)}

    @contextmanager
    def _operation_guard(self):
        lock_path = self.database_path().parent / _OPERATION_LOCK_FILENAME
        with _OPERATION_LOCK:
            lock_handle = self._acquire_lock_file(lock_path)
            try:
                session_module.get_engine().dispose()
                yield
            finally:
                session_module.get_engine().dispose()
                os.close(lock_handle)
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass

    def _acquire_lock_file(self, lock_path: Path) -> int:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(handle, f"pid={os.getpid()}\n".encode("utf-8"))
                return handle
            except FileExistsError as exc:
                if self._clear_stale_lock(lock_path):
                    continue
                raise ConflictError("System backup or restore already in progress") from exc

    def _clear_stale_lock(self, lock_path: Path) -> bool:
        try:
            payload = lock_path.read_text(encoding="utf-8").strip()
        except OSError:
            return False
        pid = self._parse_lock_pid(payload)
        if pid is None or self._pid_is_alive(pid):
            return False
        try:
            lock_path.unlink()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def _parse_lock_pid(self, payload: str) -> int | None:
        if not payload.startswith("pid="):
            return None
        try:
            return int(payload.split("=", maxsplit=1)[1])
        except ValueError:
            return None

    def _pid_is_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            return self._windows_pid_is_alive(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True

    def _windows_pid_is_alive(self, pid: int) -> bool:
        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True

        error_invalid_parameter = 87
        return kernel32.GetLastError() != error_invalid_parameter

    def _copy_database(self, source_path: Path, target_path: Path, *, coordination_path: Path | None = None, coordination_lock_mode: str | None = None) -> None:
        coordination_connection: sqlite3.Connection | None = None
        source_connection: sqlite3.Connection | None = None
        target_connection: sqlite3.Connection | None = None

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_path.unlink()

        try:
            if coordination_path is not None and coordination_lock_mode is not None:
                coordination_connection = self._open_connection(coordination_path)
                self._begin_lock_transaction(coordination_connection, coordination_lock_mode)
            source_connection = self._open_connection(source_path)
            target_connection = self._open_connection(target_path)
            source_connection.backup(target_connection)
            target_connection.commit()
            if coordination_connection is not None and coordination_connection.in_transaction:
                coordination_connection.commit()
        except sqlite3.OperationalError as exc:
            raise self._map_sqlite_error(exc) from exc
        finally:
            self._close_connection(target_connection)
            self._close_connection(source_connection)
            self._close_connection(coordination_connection)
            session_module.get_engine().dispose()

    def _probe_database_lock(self, database_path: Path, *, lock_mode: str) -> None:
        connection: sqlite3.Connection | None = None
        try:
            connection = self._open_connection(database_path)
            self._begin_lock_transaction(connection, lock_mode)
            if connection.in_transaction:
                connection.commit()
        except sqlite3.OperationalError as exc:
            raise self._map_sqlite_error(exc) from exc
        finally:
            self._close_connection(connection)

    def _replace_database_file(self, staging_path: Path, database_path: Path) -> None:
        session_module.get_engine().dispose()
        try:
            os.replace(staging_path, database_path)
        except PermissionError as exc:
            raise ConflictError("Database is busy; retry backup or restore after active requests finish") from exc

    def _open_connection(self, path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(str(path), timeout=_SQLITE_BUSY_TIMEOUT_MS / 1000, isolation_level=None)
        connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MS}")
        return connection

    def _begin_lock_transaction(self, connection: sqlite3.Connection, lock_mode: str) -> None:
        connection.execute(f"BEGIN {lock_mode}")

    def _close_connection(self, connection: sqlite3.Connection | None) -> None:
        if connection is None:
            return
        try:
            if connection.in_transaction:
                connection.rollback()
        finally:
            connection.close()

    def _run_migrations(self, database_path: Path) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
        command.upgrade(config, "head")

    def _map_sqlite_error(self, error: sqlite3.OperationalError) -> ConflictError:
        message = str(error).lower()
        if "locked" in message or "busy" in message:
            return ConflictError("Database is busy; retry backup or restore after active requests finish")
        return ConflictError("Backup operation failed")

    def _resolve_backup_path(self, filename: str) -> Path:
        backup_dir = self.backup_dir().resolve()
        backup_path = (backup_dir / filename).resolve()
        if backup_path.parent != backup_dir or not backup_path.is_file():
            raise NotFoundError("Backup file")
        return backup_path

    def _backup_metadata(self, path: Path) -> dict[str, Any]:
        stat_result = path.stat()
        modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
        return {
            "filename": path.name,
            "path": str(path.resolve()),
            "size_bytes": stat_result.st_size,
            "modified_at": modified_at.isoformat(),
        }
