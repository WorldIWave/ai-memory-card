# Input: 无外部参数（依赖 BackupService 读取路径和备份信息）
# Output: runtime/diagnostics 快照 dict，或拼接后的日志文本字符串
# Role: 系统诊断服务，聚合版本、路径、备份、日志文件信息，被 system 路由调用
# Usage: DiagnosticsService().runtime_snapshot() / .diagnostics_snapshot() / .export_logs()
from __future__ import annotations

import json
from pathlib import Path
import sys
import tomllib
from typing import Any

from app.core.config import get_settings
from app.core.errors import ValidationError
from app.core.runtime_paths import RuntimePaths
from app.services.backup_service import BackupService


class DiagnosticsService:
    def __init__(self, backup_service: BackupService | None = None) -> None:
        self._backup_service = backup_service or BackupService()

    def backend_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def log_dir(self) -> Path:
        return self._runtime_paths().log_dir

    def runtime_snapshot(self) -> dict[str, Any]:
        settings = get_settings()
        runtime_paths = self._runtime_paths(settings)
        backend_root = self.backend_root()
        backend_version = self._backend_version(backend_root)
        return {
            "app_name": settings.app_name,
            "app_version": backend_version,
            "backend_version": backend_version,
            "backend_root": str(backend_root),
            "app_data_dir": str(runtime_paths.app_data_dir),
            "database_path": str(runtime_paths.database_path),
            "backup_dir": str(runtime_paths.backup_dir),
            "log_dir": str(runtime_paths.log_dir),
            "cache_dir": str(runtime_paths.cache_dir),
            "runtime_mode": settings.runtime_mode,
            "release_channel_url": settings.release_channel_url,
            "python_executable": sys.executable,
            "python_version": sys.version,
            "backend_port": None,
        }

    def diagnostics_snapshot(self) -> dict[str, Any]:
        database_path = self._backup_service.database_path()
        log_dir = self.log_dir()
        log_files = [
            {"name": p.name, "path": str(p), "size_bytes": p.stat().st_size}
            for p in sorted(log_dir.glob("*.log"))
        ] if log_dir.exists() else []
        backups = self._backup_service.list_backups()
        return {
            **self.runtime_snapshot(),
            "database_exists": database_path.exists(),
            "database_size_bytes": database_path.stat().st_size if database_path.exists() else 0,
            "backup_count": len(backups),
            "backups": backups,
            "log_files": log_files,
        }

    def export_logs(self) -> str:
        diagnostics = self.diagnostics_snapshot()
        log_dir = self.log_dir()
        sections = [
            "AI Memory Card Log Export", "",
            json.dumps({"app_version": diagnostics["app_version"], "database_path": diagnostics["database_path"], "backup_count": diagnostics["backup_count"]}, indent=2, sort_keys=True),
            "",
        ]
        log_paths = sorted(log_dir.glob("*.log")) if log_dir.exists() else []
        if not log_paths:
            sections.extend(["No log files found.", ""])
            return "\n".join(sections)
        for log_path in log_paths:
            sections.append(f"== {log_path.name} ==")
            sections.append(log_path.read_text(encoding="utf-8", errors="replace").rstrip())
            sections.append("")
        return "\n".join(sections)

    def _runtime_paths(self, settings=None) -> RuntimePaths:
        active_settings = settings or get_settings()
        try:
            return RuntimePaths.from_settings(active_settings)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def _backend_version(self, backend_root: Path) -> str:
        pyproject_path = backend_root / "pyproject.toml"
        with pyproject_path.open("rb") as handle:
            payload = tomllib.load(handle)
        return str(payload["project"]["version"])
