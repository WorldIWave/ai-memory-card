from pathlib import Path
import shutil
import sys
import tempfile

import pytest

from app.core.config import Settings
from app.core.runtime_paths import RuntimePaths
from app.schemas.ai_plugin import PluginManifest
from app.services.ai_plugin_host_service import AIPluginHostService


@pytest.fixture()
def plugin_tmp_dir() -> Path:
    base_dir = Path.cwd() / ".pytest-temp"
    base_dir.mkdir(exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=base_dir))
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_plugin_host_loads_rag_core_manifest(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    manifest_path = plugin_root / "rag-core" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    service = AIPluginHostService(plugin_root=plugin_root)

    manifest = service.load_manifest("rag-core")

    assert isinstance(manifest, PluginManifest)
    assert manifest.id == "rag-core"
    assert "rag.generate_cards" in manifest.capabilities


def test_plugin_host_from_settings_honors_plugin_root_override(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "custom-plugins"
    manifest_path = plugin_root / "rag-core" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    settings = Settings(
        database_url=f"sqlite:///{(plugin_tmp_dir / 'data' / 'ai_memory_card.db').as_posix()}",
        app_data_dir=str(plugin_tmp_dir),
        plugin_root=str(plugin_root),
    )

    service = AIPluginHostService.from_settings(settings)

    manifest = service.load_manifest("rag-core")

    assert service.plugin_root == plugin_root.resolve()
    assert service.plugin_state_root == (plugin_tmp_dir / "plugin-state").resolve()
    assert manifest.id == "rag-core"


def test_plugin_host_constructor_and_factory_share_state_root_resolution(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    settings = Settings(
        database_url=f"sqlite:///{(plugin_tmp_dir / 'data' / 'ai_memory_card.db').as_posix()}",
        app_data_dir=str(plugin_tmp_dir),
        plugin_root=str(plugin_root),
    )

    direct_service = AIPluginHostService(plugin_root=plugin_root)
    factory_service = AIPluginHostService.from_settings(settings)

    assert direct_service.plugin_root == factory_service.plugin_root
    assert direct_service.plugin_state_root == factory_service.plugin_state_root


def test_plugin_host_requires_explicit_state_root_for_external_plugin_root(plugin_tmp_dir: Path) -> None:
    external_plugin_root = plugin_tmp_dir.parent / "external-plugins"

    with pytest.raises(ValueError, match="plugin_state_root is required"):
        AIPluginHostService(plugin_root=external_plugin_root)


@pytest.mark.parametrize("plugin_id", ["..", "../rag-core", "rag/core", r"rag\core"])
def test_plugin_host_rejects_invalid_plugin_ids(plugin_tmp_dir: Path, plugin_id: str) -> None:
    service = AIPluginHostService(plugin_root=plugin_tmp_dir / "plugins")

    with pytest.raises(ValueError, match="Invalid plugin id"):
        service.load_manifest(plugin_id)


def test_plugin_host_raises_clear_error_for_missing_manifest(plugin_tmp_dir: Path) -> None:
    service = AIPluginHostService(plugin_root=plugin_tmp_dir / "plugins")

    with pytest.raises(FileNotFoundError, match="plugin.json"):
        service.load_manifest("rag-core")


def test_plugin_host_rejects_manifest_id_mismatch(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    manifest_path = plugin_root / "rag-core" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "id": "other-plugin",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root)

    with pytest.raises(ValueError, match="Manifest id mismatch"):
        service.load_manifest("rag-core")


def test_plugin_host_ensure_started_launches_runtime_when_health_probe_fails(
    plugin_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    plugin_dir = plugin_root / "rag-core"
    manifest_path = plugin_dir / "plugin.json"
    runtime_dir = plugin_dir / "runtime"
    runtime_dir.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root, plugin_runtime_port=8095)
    manifest = service.load_manifest("rag-core")
    health_states = iter([False, True])
    launch_record: dict[str, object] = {}

    monkeypatch.setattr(service, "_is_healthy", lambda _manifest: next(health_states))

    class DummyPopen:
        pass

    def fake_popen(command: list[str], **kwargs: object) -> DummyPopen:
        launch_record["command"] = command
        launch_record["cwd"] = kwargs.get("cwd")
        launch_record["env"] = kwargs.get("env")
        return DummyPopen()

    monkeypatch.setattr("app.services.ai_plugin_host_service.subprocess.Popen", fake_popen)

    base_url = service.ensure_started(manifest)

    assert base_url == "http://127.0.0.1:8095"
    assert launch_record["command"] == [
        sys.executable,
        "-m",
        "uvicorn",
        "runtime.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8095",
    ]
    assert launch_record["cwd"] == str(plugin_dir)
    env = launch_record["env"]
    assert isinstance(env, dict)
    assert str(plugin_dir) in str(env.get("PYTHONPATH", ""))


def test_runtime_paths_include_and_create_plugin_dirs(plugin_tmp_dir: Path) -> None:
    database_path = plugin_tmp_dir / "data" / "ai_memory_card.db"
    database_path.parent.mkdir(parents=True)
    database_path.write_text("", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        app_data_dir=str(plugin_tmp_dir),
    )

    paths = RuntimePaths.from_settings(settings)
    paths.ensure_directories()

    assert paths.plugins_dir == (plugin_tmp_dir / "plugins").resolve()
    assert paths.plugin_state_dir == (plugin_tmp_dir / "plugin-state").resolve()
    assert paths.plugins_dir.is_dir()
    assert paths.plugin_state_dir.is_dir()


def test_runtime_paths_honor_plugin_root_override(plugin_tmp_dir: Path) -> None:
    database_path = plugin_tmp_dir / "data" / "ai_memory_card.db"
    custom_plugin_root = plugin_tmp_dir / "custom-plugins"
    database_path.parent.mkdir(parents=True)
    database_path.write_text("", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        app_data_dir=str(plugin_tmp_dir),
        plugin_root=str(custom_plugin_root),
    )

    paths = RuntimePaths.from_settings(settings)
    paths.ensure_directories()

    assert paths.plugins_dir == custom_plugin_root.resolve()
    assert paths.plugins_dir.is_dir()
    assert paths.plugin_state_dir == (plugin_tmp_dir / "plugin-state").resolve()


def test_external_plugin_root_override_keeps_plugin_state_dir_under_app_data(plugin_tmp_dir: Path) -> None:
    app_data_dir = plugin_tmp_dir / "app-data"
    database_path = app_data_dir / "data" / "ai_memory_card.db"
    external_plugin_root = plugin_tmp_dir.parent / "external-plugins"
    database_path.parent.mkdir(parents=True)
    database_path.write_text("", encoding="utf-8")
    settings = Settings(
        database_url=f"sqlite:///{database_path.as_posix()}",
        app_data_dir=str(app_data_dir),
        plugin_root=str(external_plugin_root),
    )

    paths = RuntimePaths.from_settings(settings)
    service = AIPluginHostService.from_settings(settings)

    assert paths.plugins_dir == external_plugin_root.resolve()
    assert paths.plugin_state_dir == (app_data_dir / "plugin-state").resolve()
    assert service.plugin_root == external_plugin_root.resolve()
    assert service.plugin_state_root == (app_data_dir / "plugin-state").resolve()


def test_plugin_host_persists_plugin_config(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    manifest_path = plugin_root / "rag-core" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root)

    saved = service.save_plugin_config(
        "rag-core",
        {
            "enabled": True,
            "provider_profile": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
        },
    )

    loaded = service.get_plugin_config("rag-core")

    assert saved["enabled"] is True
    assert saved["provider_profile"] == "openai_compatible"
    assert loaded.base_url == "https://api.example.com/v1"
    assert loaded.api_key_configured is True
    assert loaded.model == "gpt-4o-mini"
    assert "api_key" not in saved
    assert (service.plugin_state_root / "rag-core" / "config.json").is_file()


def test_plugin_host_runs_scheduler_plan_review(
    plugin_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    plugin_dir = plugin_root / "rag-core"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        """
        {
          "id": "rag-core",
          "name": "AI Capability Plugin",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            },
            "scheduler.plan_review": {
              "modes": ["local"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root, plugin_state_root=plugin_tmp_dir / "plugin-state")
    monkeypatch.setattr(service, "ensure_started", lambda _manifest: "http://127.0.0.1:8095")

    class DummyClient:
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

        def plan_review(self, payload: dict[str, object]) -> dict[str, object]:
            assert self.base_url == "http://127.0.0.1:8095"
            assert payload["capability"] == "scheduler.plan_review"
            return {"scheduler_type": "ai_rl_v1", "interval_days": 2}

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.services.ai_plugin_host_service.PluginClient", DummyClient)

    result = service.run_scheduler_plan_review({"capability": "scheduler.plan_review"})

    assert result["scheduler_type"] == "ai_rl_v1"
    assert result["interval_days"] == 2


def test_plugin_status_is_installed_disabled_by_default(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    plugin_dir = plugin_root / "rag-core"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            },
            "evaluation.score_explanation": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            },
            "scheduler.plan_review": {
              "modes": ["local"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root, plugin_state_root=plugin_tmp_dir / "plugin-state")

    status = service.get_plugin_status("rag-core")

    assert status["enabled"] is False
    assert status["state"] == "installed_disabled"
    capabilities = {capability["name"]: capability for capability in status["capabilities"]}
    assert set(capabilities) == {"rag.generate_cards", "evaluation.score_explanation", "scheduler.plan_review"}
    assert capabilities["rag.generate_cards"]["modes"] == [{"name": "api", "available": False}]
    assert capabilities["scheduler.plan_review"]["modes"] == [{"name": "local", "available": True}]


def test_plugin_status_is_ready_when_enabled_configured_and_healthy(
    plugin_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    plugin_dir = plugin_root / "rag-core"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root, plugin_state_root=plugin_tmp_dir / "plugin-state")
    service.save_plugin_config(
        "rag-core",
        {
            "enabled": True,
            "provider_profile": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
        },
    )
    monkeypatch.setattr(service, "_is_healthy", lambda _manifest: True)
    monkeypatch.setattr(service, "_capabilities_payload", lambda _base_url: {})

    status = service.get_plugin_status("rag-core")

    assert status["enabled"] is True
    assert status["state"] == "ready"
    assert status["configuration"] == {
        "provider_profile": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key_configured": True,
        "model": "gpt-4o-mini",
    }


def test_plugin_status_is_passive_for_unhealthy_enabled_runtime(
    plugin_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    plugin_dir = plugin_root / "rag-core"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        """
        {
          "id": "rag-core",
          "name": "RAG Card Generation",
          "version": "0.1.0",
          "protocol_version": "1",
          "capabilities": {
            "rag.generate_cards": {
              "modes": ["api"],
              "entrypoint": {
                "base_url": "http://127.0.0.1:{port}",
                "health": "http://127.0.0.1:{port}/health"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    service = AIPluginHostService(plugin_root=plugin_root, plugin_state_root=plugin_tmp_dir / "plugin-state")
    service.save_plugin_config(
        "rag-core",
        {
            "enabled": True,
            "provider_profile": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
        },
    )
    monkeypatch.setattr(service, "_is_healthy", lambda _manifest: False)
    monkeypatch.setattr(
        service,
        "ensure_started",
        lambda _manifest: pytest.fail("get_plugin_status should not launch the runtime"),
    )

    status = service.get_plugin_status("rag-core")

    assert status["state"] == "enabled_unhealthy"
    assert status["health"]["status"] == "unavailable"


def test_plugin_host_falls_back_to_empty_config_when_state_file_is_malformed(plugin_tmp_dir: Path) -> None:
    plugin_root = plugin_tmp_dir / "plugins"
    service = AIPluginHostService(plugin_root=plugin_root)
    config_path = service.plugin_state_root / "rag-core" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{not-json", encoding="utf-8")

    loaded = service.get_plugin_config("rag-core")

    assert loaded.enabled is False
    assert loaded.provider_profile == "openai_compatible"
    assert loaded.base_url is None
    assert loaded.api_key_configured is False
    assert loaded.model is None
