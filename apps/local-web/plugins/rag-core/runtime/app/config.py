from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PluginRuntimeConfig:
    plugin_id: str = "rag-core"
    plugin_version: str = "0.1.0"
    protocol_version: str = "1"
    enabled: bool = False
    default_provider_profile: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    request_timeout: float = 300.0
    last_error_code: str | None = None
    last_error_summary: str | None = None

    def base_url_for(self, provider_profile: str) -> str:
        normalized = provider_profile.strip() or self.default_provider_profile
        if normalized in {"openai_compatible", "managed_remote_service"}:
            return self.base_url
        raise ValueError(f"Unsupported provider_profile: {provider_profile}")

    def available_provider_profiles(self) -> list[str]:
        if self.enabled and self.base_url and self.api_key and self.model:
            return ["openai_compatible"]
        return []

    @property
    def managed_remote_base_url(self) -> str:
        return self.base_url


def load_runtime_config() -> PluginRuntimeConfig:
    file_config = _file_config()
    base_url = _file_or_env(file_config, "base_url", "LMCA_RAG_BASE_URL", "")
    if not base_url:
        base_url = _file_or_env(file_config, "managed_remote_base_url", "LMCA_RAG_MANAGED_REMOTE_BASE_URL", "")
    return PluginRuntimeConfig(
        enabled=_file_bool(file_config, "enabled", "LMCA_RAG_ENABLED", False),
        base_url=base_url,
        api_key=_file_or_env(file_config, "api_key", "LMCA_RAG_API_KEY", ""),
        model=_file_or_env(file_config, "model", "LMCA_RAG_MODEL", ""),
        request_timeout=_float_env("LMCA_RAG_REMOTE_TIMEOUT", 300.0),
    )


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _file_bool(file_config: dict[str, object], file_key: str, env_key: str, default: bool) -> bool:
    value = file_config.get(file_key)
    if isinstance(value, bool):
        return value
    if value is not None and str(value).strip():
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    env_value = os.environ.get(env_key)
    if env_value is None or not env_value.strip():
        return default
    return env_value.strip().lower() in {"1", "true", "yes", "on"}


def _file_config() -> dict[str, object]:
    path_value = os.environ.get("LMCA_PLUGIN_CONFIG_PATH", "").strip()
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _file_or_env(file_config: dict[str, object], file_key: str, env_key: str, default: str) -> str:
    value = file_config.get(file_key)
    if value is not None and str(value).strip():
        return str(value).strip()
    return _env(env_key, default)
