# Input: Settings 或默认配置单例  |  Output: 已配置的滚动日志文件路径，失败时返回 None
# Output: 为 FastAPI 进程接入 runtime-aware 的文件日志处理器
# Role: 这是后端启动链路里把日志落到 app_data_root/logs 的统一入口
# Use: 仅在应用启动时调用一次；目录解析依赖 RuntimePaths，别在请求链里重复配置 handler
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.runtime_paths import RuntimePaths


def configure_runtime_logging(settings: Settings | None = None) -> Path | None:
    active_settings = settings or get_settings()
    try:
        runtime_paths = RuntimePaths.from_settings(active_settings)
    except ValueError:
        return None
    log_dir = runtime_paths.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == log_path:
            return log_path

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    setattr(file_handler, "_lmca_runtime_log", True)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger.addHandler(file_handler)
    return log_path


def shutdown_runtime_logging() -> None:
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if getattr(handler, "_lmca_runtime_log", False):
            root_logger.removeHandler(handler)
            handler.close()
