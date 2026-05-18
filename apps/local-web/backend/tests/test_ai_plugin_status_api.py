from __future__ import annotations

from app.api.dependencies import get_ai_plugin_host_service
from app.main import app


class FakeHost:
    test_calls = 0

    def get_plugin_status(self, plugin_id: str) -> dict[str, object]:
        assert plugin_id == "rag-core"
        return {
            "plugin_id": "rag-core",
            "plugin_name": "RAG Card Generation",
            "plugin_version": "0.1.0",
            "protocol_version": "1",
            "enabled": False,
            "state": "installed_disabled",
            "health": {"status": "ok", "base_url": "http://127.0.0.1:8095"},
            "capabilities": [{"name": "rag.generate_cards"}],
            "configuration": {
                "provider_profile": "openai_compatible",
                "base_url": None,
                "api_key_configured": False,
                "model": None,
            },
        }

    def test_plugin(self, plugin_id: str) -> dict[str, object]:
        assert plugin_id == "rag-core"
        self.test_calls += 1
        return {
            "plugin_id": "rag-core",
            "plugin_name": "RAG Card Generation",
            "plugin_version": "0.1.0",
            "protocol_version": "1",
            "enabled": True,
            "state": "ready",
            "health": {"status": "ok", "base_url": "http://127.0.0.1:8095"},
            "capabilities": [{"name": "rag.generate_cards"}],
            "configuration": {
                "provider_profile": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key_configured": True,
                "model": "gpt-4o-mini",
            },
        }

    def close(self) -> None:
        return None

    def save_plugin_config(self, plugin_id: str, payload: dict[str, object]) -> dict[str, object]:
        assert plugin_id == "rag-core"
        return {
            "enabled": bool(payload.get("enabled")),
            "provider_profile": payload.get("provider_profile") or "openai_compatible",
            "base_url": payload.get("base_url"),
            "api_key_configured": bool(payload.get("api_key")),
            "model": payload.get("model"),
        }


def test_ai_plugin_status_endpoint_returns_runtime_status(memory_client) -> None:
    app.dependency_overrides[get_ai_plugin_host_service] = lambda: FakeHost()
    try:
        response = memory_client.get("/api/ai/plugins/rag-core")
    finally:
        app.dependency_overrides.pop(get_ai_plugin_host_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == "rag-core"
    assert payload["enabled"] is False
    assert payload["state"] == "installed_disabled"
    assert payload["health"]["status"] == "ok"
    assert payload["configuration"] == {
        "provider_profile": "openai_compatible",
        "base_url": None,
        "api_key_configured": False,
        "model": None,
    }


def test_ai_plugin_config_endpoint_persists_plugin_settings(memory_client) -> None:
    app.dependency_overrides[get_ai_plugin_host_service] = lambda: FakeHost()
    try:
        response = memory_client.put(
            "/api/ai/plugins/rag-core/config",
            json={
                "enabled": True,
                "provider_profile": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "model": "gpt-4o-mini",
            },
        )
    finally:
        app.dependency_overrides.pop(get_ai_plugin_host_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "enabled": True,
        "provider_profile": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key_configured": True,
        "model": "gpt-4o-mini",
    }


def test_ai_plugin_test_endpoint_returns_ready_runtime_status(memory_client) -> None:
    app.dependency_overrides[get_ai_plugin_host_service] = lambda: FakeHost()
    try:
        response = memory_client.post("/api/ai/plugins/rag-core/test")
    finally:
        app.dependency_overrides.pop(get_ai_plugin_host_service, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["plugin_id"] == "rag-core"
    assert payload["enabled"] is True
    assert payload["state"] == "ready"
    assert payload["health"]["status"] == "ok"
