from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import httpx

from app.providers.ai.plugin_client import PluginClient
from app.core.config import Settings, get_settings
from app.core.runtime_paths import RuntimePaths
from app.schemas.ai_plugin import PluginConfigRead, PluginConfigUpdateInput, PluginManifest

_PLUGIN_START_TIMEOUT_SECONDS = 5.0
_PLUGIN_START_POLL_INTERVAL_SECONDS = 0.1


class AIPluginHostService:
    def __init__(self, *, plugin_root: Path, plugin_state_root: Path | None = None, plugin_runtime_port: int = 8095) -> None:
        self.plugin_root = Path(plugin_root).expanduser().resolve()
        self.plugin_state_root = (
            Path(plugin_state_root).expanduser().resolve()
            if plugin_state_root is not None
            else self._default_plugin_state_root(self.plugin_root)
        )
        self.plugin_runtime_port = plugin_runtime_port

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> AIPluginHostService:
        resolved_settings = settings or get_settings()
        runtime_paths = RuntimePaths.from_settings(resolved_settings)
        return cls(
            plugin_root=runtime_paths.plugins_dir,
            plugin_state_root=runtime_paths.plugin_state_dir,
            plugin_runtime_port=resolved_settings.plugin_runtime_port,
        )

    def load_manifest(self, plugin_id: str) -> PluginManifest:
        manifest_path = self._manifest_path(plugin_id)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Missing plugin manifest: {manifest_path}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PluginManifest.model_validate(payload)
        if manifest.id != plugin_id:
            raise ValueError(f"Manifest id mismatch: expected {plugin_id}, got {manifest.id}")
        return manifest

    def run_rag_generate_cards(self, payload: dict[str, object]) -> dict[str, object]:
        manifest = self.load_manifest("rag-core")
        base_url = self.ensure_started(manifest)
        client = PluginClient(base_url=base_url)
        try:
            return client.generate_rag_cards(payload)
        finally:
            client.close()

    def run_evaluation_score_explanation(self, payload: dict[str, object]) -> dict[str, object]:
        manifest = self.load_manifest("rag-core")
        base_url = self.ensure_started(manifest)
        client = PluginClient(base_url=base_url)
        try:
            return client.score_explanation(payload)
        finally:
            client.close()

    def run_scheduler_plan_review(self, payload: dict[str, object]) -> dict[str, object]:
        manifest = self.load_manifest("rag-core")
        base_url = self.ensure_started(manifest)
        client = PluginClient(base_url=base_url)
        try:
            return client.plan_review(payload)
        finally:
            client.close()

    def get_plugin_status(self, plugin_id: str) -> dict[str, object]:
        manifest = self.load_manifest(plugin_id)
        base_url = self._base_url(manifest)
        health_url = self._health_url(manifest)
        config_payload = self._read_plugin_config_payload(plugin_id)
        plugin_config = self._public_config_from_payload(config_payload)
        healthy = False
        if not plugin_config.enabled:
            state = "installed_disabled"
        elif not _config_payload_is_complete(config_payload):
            state = "enabled_not_configured"
        else:
            healthy = self._is_healthy(manifest)
            state = "ready" if healthy else "enabled_unhealthy"
        capabilities = self._manifest_capabilities(manifest, api_available=healthy)
        configuration: dict[str, object] = {
            "provider_profile": plugin_config.provider_profile,
            "base_url": plugin_config.base_url,
            "api_key_configured": plugin_config.api_key_configured,
            "model": plugin_config.model,
        }
        if healthy:
            payload = self._capabilities_payload(base_url)
            capabilities_value = payload.get("capabilities")
            if isinstance(capabilities_value, list):
                capabilities = [item for item in capabilities_value if isinstance(item, dict)]
            configuration_value = payload.get("configuration")
            if isinstance(configuration_value, dict):
                configuration.update(configuration_value)
        return {
            "plugin_id": manifest.id,
            "plugin_name": manifest.name,
            "plugin_version": manifest.version,
            "protocol_version": manifest.protocol_version,
            "enabled": plugin_config.enabled,
            "state": state,
            "health": {
                "status": "ok" if healthy else "unavailable",
                "base_url": base_url,
                "health_url": health_url,
                "last_error_code": None if healthy else "plugin_unavailable",
                "last_error_summary": None if healthy else "Plugin runtime is not responding",
            },
            "capabilities": capabilities,
            "configuration": configuration,
        }

    def get_plugin_config(self, plugin_id: str) -> PluginConfigRead:
        payload = self._read_plugin_config_payload(plugin_id)
        return self._public_config_from_payload(payload)

    def test_plugin(self, plugin_id: str) -> dict[str, object]:
        status = self.get_plugin_status(plugin_id)
        if status["state"] in {"installed_disabled", "enabled_not_configured"}:
            return status

        manifest = self.load_manifest(plugin_id)
        base_url = self.ensure_started(manifest)
        client = PluginClient(base_url=base_url)
        try:
            client.test_provider()
        finally:
            client.close()
        return self.get_plugin_status(plugin_id)

    def save_plugin_config(self, plugin_id: str, payload: dict[str, object]) -> dict[str, object]:
        config = PluginConfigUpdateInput.model_validate(payload)
        plugin_state_dir = self._plugin_state_dir(plugin_id)
        plugin_state_dir.mkdir(parents=True, exist_ok=True)
        persisted = {
            "enabled": config.enabled,
            "provider_profile": config.provider_profile,
            "base_url": _normalized_url(config.base_url),
            "api_key": _normalized_text(config.api_key),
            "model": _normalized_text(config.model),
        }
        self._plugin_config_path(plugin_id).write_text(
            json.dumps(persisted, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._public_config_payload_from_payload(persisted)

    def ensure_started(self, manifest: PluginManifest) -> str:
        if self._is_healthy(manifest):
            return self._base_url(manifest)

        plugin_dir = self.plugin_root / manifest.id
        runtime_dir = plugin_dir / "runtime"
        if not runtime_dir.is_dir():
            raise RuntimeError(f"Missing plugin runtime directory: {runtime_dir}")

        runtime_log_path = self._plugin_runtime_log_path(manifest.id)
        runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_log_handle = runtime_log_path.open("ab")
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "runtime.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.plugin_runtime_port),
            ],
            cwd=str(plugin_dir),
            env=self._plugin_environment(plugin_dir),
            stdout=runtime_log_handle,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        runtime_log_handle.close()

        deadline = time.monotonic() + _PLUGIN_START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._is_healthy(manifest):
                return self._base_url(manifest)
            time.sleep(_PLUGIN_START_POLL_INTERVAL_SECONDS)
        raise RuntimeError(f"Failed to start plugin runtime: {manifest.id}")

    def _manifest_path(self, plugin_id: str) -> Path:
        normalized_plugin_id = plugin_id.strip()
        if (
            not normalized_plugin_id
            or normalized_plugin_id in {".", ".."}
            or "/" in normalized_plugin_id
            or "\\" in normalized_plugin_id
        ):
            raise ValueError(f"Invalid plugin id: {plugin_id}")

        manifest_path = (self.plugin_root / normalized_plugin_id / "plugin.json").resolve(strict=False)
        try:
            manifest_path.relative_to(self.plugin_root)
        except ValueError as exc:
            raise ValueError(f"Invalid plugin id: {plugin_id}") from exc
        return manifest_path

    @staticmethod
    def _default_plugin_state_root(plugin_root: Path) -> Path:
        if plugin_root.name == "plugins":
            return plugin_root.parent / "plugin-state"
        raise ValueError("plugin_state_root is required when plugin_root is external to app_data_dir")

    def _base_url(self, manifest: PluginManifest) -> str:
        capability = manifest.capabilities.get("rag.generate_cards")
        if capability is None:
            raise RuntimeError("rag-core manifest does not declare rag.generate_cards")
        return capability.entrypoint.base_url.format(port=self.plugin_runtime_port)

    def _health_url(self, manifest: PluginManifest) -> str:
        capability = manifest.capabilities.get("rag.generate_cards")
        if capability is None:
            raise RuntimeError("rag-core manifest does not declare rag.generate_cards")
        return capability.entrypoint.health.format(port=self.plugin_runtime_port)

    def _is_healthy(self, manifest: PluginManifest) -> bool:
        try:
            response = httpx.get(self._health_url(manifest), timeout=0.5)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        return str(payload.get("status") or "").strip().lower() == "ok"

    def _plugin_environment(self, plugin_dir: Path) -> dict[str, str]:
        env = dict(os.environ)
        pythonpath = str(plugin_dir)
        if env.get("PYTHONPATH"):
            pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
        env["PYTHONPATH"] = pythonpath
        env["LMCA_PLUGIN_CONFIG_PATH"] = str(self._plugin_config_path("rag-core"))
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _capabilities_payload(self, base_url: str) -> dict[str, object]:
        try:
            response = httpx.get(f"{base_url}/capabilities", timeout=0.5)
            response.raise_for_status()
        except httpx.HTTPError:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _manifest_capabilities(self, manifest: PluginManifest, *, api_available: bool) -> list[dict[str, object]]:
        return [
            {
                "name": capability_name,
                "modes": [
                    {
                        "name": mode,
                        "available": True if mode == "local" else api_available,
                    }
                    for mode in capability.modes
                ],
            }
            for capability_name, capability in manifest.capabilities.items()
        ]

    def _plugin_state_dir(self, plugin_id: str) -> Path:
        return self.plugin_state_root / plugin_id

    def _plugin_config_path(self, plugin_id: str) -> Path:
        return self._plugin_state_dir(plugin_id) / "config.json"

    def _plugin_runtime_log_path(self, plugin_id: str) -> Path:
        return self._plugin_state_dir(plugin_id) / "runtime.log"

    def _read_plugin_config_payload(self, plugin_id: str) -> dict[str, object]:
        path = self._plugin_config_path(plugin_id)
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                return payload
        return {
            "enabled": False,
            "provider_profile": "openai_compatible",
            "base_url": None,
            "api_key": None,
            "model": None,
        }

    def _public_config_from_payload(self, payload: dict[str, object]) -> PluginConfigRead:
        return PluginConfigRead.model_validate(self._public_config_payload_from_payload(payload))

    def _public_config_payload_from_payload(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "enabled": bool(payload.get("enabled")),
            "provider_profile": _normalized_text(payload.get("provider_profile")) or "openai_compatible",
            "base_url": _normalized_url(payload.get("base_url")),
            "api_key_configured": bool(_normalized_text(payload.get("api_key"))),
            "model": _normalized_text(payload.get("model")),
        }

    def close(self) -> None:
        return None


def _normalized_url(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.rstrip("/")


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _config_payload_is_complete(payload: dict[str, object]) -> bool:
    return bool(
        bool(payload.get("enabled"))
        and _normalized_url(payload.get("base_url"))
        and _normalized_text(payload.get("api_key"))
        and _normalized_text(payload.get("model"))
    )
