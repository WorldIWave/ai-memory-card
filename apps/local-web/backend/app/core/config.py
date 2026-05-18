# Input: 环境变量（前缀 LMCA_）  |  Output: Settings 单例（含 database_url、ai_provider 等）
# Role: 全局配置中枢，所有模块通过 get_settings() 获取运行时参数
# Note: 使用 lru_cache 缓存单例；修改环境变量后需重启服务才能生效
# Usage: from app.core.config import get_settings; s = get_settings()
"""
config.py - 应用配置

职责: 定义应用级配置项，从环境变量读取
输入: 环境变量（前缀 LMCA_）
输出: Settings 单例
位置: Core层
关联: db/session.py, services/backup_service.py
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Memory Card Backend"
    database_url: str = "sqlite:///./ai_memory_card.db"
    ai_provider_base_url: str | None = None
    app_data_dir: str | None = None
    log_dir: str | None = None
    cache_dir: str | None = None
    plugin_root: str | None = None
    plugin_runtime_port: int = 8095
    runtime_mode: str = "development"
    release_channel_url: str | None = None
    enable_onboarding_seed: bool | None = None

    model_config = SettingsConfigDict(env_prefix="LMCA_", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
