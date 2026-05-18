# Input: EvaluationRequest（target_unit, learner_explanation, reference_material）
# Output: AI 评分结果 dict（由 AI Provider 返回）
# Role: AI 评估服务，根据配置选择 RemoteHTTP 或 Noop Provider，被 evaluations 路由调用
# Note: ai_provider_base_url 未配置时退化为 NoopAIProvider，不发起真实 AI 请求
from __future__ import annotations

from app.core.config import get_settings
from app.db.models import Card, KnowledgeUnit
from app.providers.ai.noop import NoopAIProvider
from app.providers.ai.remote_http import RemoteHTTPAIProvider
from app.schemas.evaluation import EvaluationRequest
from app.services.ai_plugin_host_service import AIPluginHostService


class EvaluationService:
    def __init__(self, base_url: str | None = None, plugin_host_service: AIPluginHostService | None = None) -> None:
        settings = get_settings()
        resolved_base_url = settings.ai_provider_base_url if base_url is None else base_url
        self.plugin_host_service = plugin_host_service or AIPluginHostService.from_settings(settings)
        self.provider = RemoteHTTPAIProvider(resolved_base_url) if resolved_base_url else NoopAIProvider()
        self._use_legacy_provider = base_url is not None or bool(settings.ai_provider_base_url)

    def evaluate(
        self,
        payload: EvaluationRequest,
        *,
        card: Card | None = None,
        knowledge_unit: KnowledgeUnit | None = None,
    ) -> dict[str, object]:
        if self._use_legacy_provider:
            return self.provider.evaluate_explanation(
                target_unit=payload.target_unit,
                learner_explanation=payload.learner_explanation,
                reference_material=payload.reference_material,
            )
        request = {
            "capability": "evaluation.score_explanation",
            "mode": "api",
            "provider_profile": "openai_compatible",
            "rubric_version": payload.rubric_version,
            "target_card": payload.target_card or _target_card_payload(card),
            "target_unit": payload.target_unit or (_target_unit_payload(knowledge_unit) if knowledge_unit is not None else None),
            "learner_explanation": payload.learner_explanation,
        }
        return self.plugin_host_service.run_evaluation_score_explanation(request)

    def close(self) -> None:
        close = getattr(self.provider, "close", None)
        if callable(close):
            close()


def _target_card_payload(card: Card | None) -> dict[str, object]:
    if card is None:
        return {}
    return {
        "id": card.id,
        "card_type": card.card_type,
        "front": card.front,
        "back": card.back,
        "tags": list(card.tags or []),
    }


def _target_unit_payload(unit: KnowledgeUnit) -> dict[str, object]:
    return {
        "id": unit.id,
        "provider_unit_id": unit.provider_unit_id,
        "topic": unit.topic,
        "summary": unit.summary,
        "source_span": unit.source_span,
        "raw_payload": dict(unit.raw_payload or {}),
    }
