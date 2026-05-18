# Input: 无（不依赖任何外部服务）  |  Output: 全零评分或明确的未配置错误
# Role: AI 提供商的空实现，用于开发/测试环境，避免解释评估依赖真实 AI 服务
# Note: 解释评估可降级为全零；RAG 生成不能无中生有，因此会抛出未配置错误
# Usage: 未配置 LMCA_AI_PROVIDER_BASE_URL 时由服务层选择此类或直接返回 provider 未配置
from __future__ import annotations


class NoopAIProvider:
    def get_name(self) -> str:
        return "none"

    def evaluate_explanation(
        self,
        *,
        target_unit: dict[str, object],
        learner_explanation: str,
        reference_material: str | None = None,
    ) -> dict[str, object]:
        return {
            "mastery_score": 0.0,
            "concept_score": 0.0,
            "mechanism_score": 0.0,
            "boundary_score": 0.0,
            "misconception_score": 0.0,
            "trace_id": None,
        }

    def generate_rag_cards(
        self,
        *,
        deck: dict[str, object],
        documents: list[dict[str, object]],
        topics: list[str] | None = None,
        generation_prefs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        raise RuntimeError("Remote AI provider is not configured")
