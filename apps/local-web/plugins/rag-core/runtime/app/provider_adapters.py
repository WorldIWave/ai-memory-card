from __future__ import annotations

from typing import Any

from .config import PluginRuntimeConfig
from .contracts import PluginEvaluationTaskRequest, PluginTaskRequest
from .errors import RuntimeTaskFailure
from .pipeline_service import generate_cards_from_documents, probe_provider, score_explanation


class LocalPipelineAdapter:
    def __init__(
        self,
        *,
        config: PluginRuntimeConfig,
        provider_profile: str,
    ) -> None:
        self.config = config
        self.provider_profile = provider_profile

    def generate_rag_cards(self, payload: PluginTaskRequest) -> dict[str, Any]:
        if not self.config.available_provider_profiles():
            raise RuntimeTaskFailure(
                code="plugin_not_configured",
                message="AI plugin is enabled but provider settings are incomplete.",
            )
        return generate_cards_from_documents(
            documents=[document.model_dump() for document in payload.documents],
            deck_name=str(payload.deck.get("name") or "AI Generated Cards"),
            topics=payload.topics,
            generation_prefs=payload.generation_prefs,
            provider_settings={
                "base_url": _config_value(self.config, "base_url"),
                "api_key": _config_value(self.config, "api_key"),
                "model": _config_value(self.config, "model"),
                "timeout": str(self.config.request_timeout),
            },
        )

    def probe_provider(self) -> dict[str, Any]:
        if not self.config.available_provider_profiles():
            raise RuntimeTaskFailure(
                code="plugin_not_configured",
                message="AI plugin is enabled but provider settings are incomplete.",
            )
        return probe_provider(
            provider_settings={
                "base_url": _config_value(self.config, "base_url"),
                "api_key": _config_value(self.config, "api_key"),
                "model": _config_value(self.config, "model"),
                "timeout": str(self.config.request_timeout),
            }
        )

    def score_explanation(self, payload: PluginEvaluationTaskRequest) -> dict[str, Any]:
        if not self.config.available_provider_profiles():
            raise RuntimeTaskFailure(
                code="plugin_not_configured",
                message="AI plugin is enabled but provider settings are incomplete.",
            )
        return score_explanation(
            target_card=payload.target_card.model_dump(),
            target_unit=payload.target_unit.model_dump() if payload.target_unit is not None else None,
            learner_explanation=payload.learner_explanation,
            rubric_version=payload.rubric_version,
            provider_settings={
                "base_url": _config_value(self.config, "base_url"),
                "api_key": _config_value(self.config, "api_key"),
                "model": _config_value(self.config, "model"),
                "timeout": str(self.config.request_timeout),
            },
        )

    def close(self) -> None:
        return None


def build_provider_adapter(
    *,
    config: PluginRuntimeConfig,
    provider_profile: str,
    client: object | None = None,
) -> LocalPipelineAdapter:
    del client
    normalized_profile = provider_profile.strip() or config.default_provider_profile
    if normalized_profile not in {"openai_compatible", "managed_remote_service"}:
        raise ValueError(f"Unsupported provider_profile: {provider_profile}")
    return LocalPipelineAdapter(config=config, provider_profile=normalized_profile)


def _config_value(config: object, primary_key: str, fallback_key: str | None = None) -> str:
    primary = getattr(config, primary_key, None)
    if primary is not None and str(primary).strip():
        return str(primary).strip()
    if fallback_key is not None:
        fallback = getattr(config, fallback_key, None)
        if fallback is not None and str(fallback).strip():
            return str(fallback).strip()
    return ""
