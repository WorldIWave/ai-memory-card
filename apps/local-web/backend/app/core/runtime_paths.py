# Input: Settings 中的数据库 URL、运行时根目录与可选显式路径  |  Output: app data/data/db/backup/log/cache 的确定路径
# Output: 提供 RuntimePaths 数据对象，统一描述后端实际读写的本地目录布局
# Role: 这是 backend 在 dev/bundled 两种模式下解析文件系统落点的单一真相来源
# Use: 任何触盘逻辑都应先经由 RuntimePaths.from_settings；不要再拼接零散相对路径
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import Settings


@dataclass(frozen=True)
class RuntimePaths:
    app_data_dir: Path
    data_dir: Path
    database_path: Path
    backup_dir: Path
    log_dir: Path
    cache_dir: Path
    temp_dir: Path
    plugins_dir: Path
    plugin_state_dir: Path

    @classmethod
    def from_settings(cls, settings: Settings) -> RuntimePaths:
        database_path = cls._database_path(settings.database_url)

        if settings.app_data_dir:
            app_data_dir = Path(settings.app_data_dir).expanduser().resolve()
            data_dir = app_data_dir / "data"
            try:
                database_path.relative_to(data_dir)
            except ValueError as exc:
                raise ValueError(f"Configured app_data_dir requires database_path to live under {data_dir}") from exc
        else:
            if database_path.parent.name == "data":
                app_data_dir = database_path.parent.parent
                data_dir = database_path.parent
            else:
                app_data_dir = database_path.parent
                data_dir = app_data_dir / "data"

        log_dir = cls._resolve_optional_dir(settings.log_dir, app_data_dir / "logs")
        cache_dir = cls._resolve_optional_dir(settings.cache_dir, app_data_dir / "cache")
        plugins_dir = cls._resolve_optional_dir(settings.plugin_root, app_data_dir / "plugins")

        return cls(
            app_data_dir=app_data_dir,
            data_dir=data_dir,
            database_path=database_path,
            backup_dir=app_data_dir / "backups",
            log_dir=log_dir,
            cache_dir=cache_dir,
            temp_dir=app_data_dir / "temp",
            plugins_dir=plugins_dir,
            plugin_state_dir=app_data_dir / "plugin-state",
        )

    def ensure_directories(self) -> None:
        for path in (
            self.app_data_dir,
            self.data_dir,
            self.backup_dir,
            self.log_dir,
            self.cache_dir,
            self.temp_dir,
            self.plugins_dir,
            self.plugin_state_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_optional_dir(value: str | None, default: Path) -> Path:
        if value:
            return Path(value).expanduser().resolve()
        return default

    @staticmethod
    def _database_path(database_url: str) -> Path:
        url = make_url(database_url)
        if url.get_backend_name() != "sqlite" or url.host not in (None, "", "localhost"):
            raise ValueError("Runtime paths require a local SQLite database URL")

        database = url.database
        if database in (None, "", ":memory:"):
            raise ValueError("Runtime paths require a local SQLite database URL")

        database_path = Path(database)
        if not database_path.is_absolute():
            database_path = Path.cwd() / database_path
        return database_path.resolve()
