# Input: base_url、解释评估请求或 RAG 生成请求  |  Output: 本地服务可消费的 dict
# Role: 对接远端 AI HTTP 服务，封装 explanation evaluation 与 RAG card generation 调用
# Note: 网络错误会直接 raise；调用方需在应用关闭时调用 close() 释放连接
# Usage: EvaluationService/RAGImportService 按配置创建并调用本 provider
from __future__ import annotations

import httpx


class RemoteHTTPAIProvider:
    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self.client = client or httpx.Client()

    def get_name(self) -> str:
        return "remote_http"

    def evaluate_explanation(
        self,
        *,
        target_unit: dict[str, object],
        learner_explanation: str,
        reference_material: str | None = None,
    ) -> dict[str, object]:
        response = self.client.post(
            f"{self.base_url}/v1/evaluations/explanation",
            json={
                "target_unit": target_unit,
                "learner_explanation": learner_explanation,
                "reference_material": reference_material,
            },
        )
        response.raise_for_status()
        payload = response.json()
        dimension_scores = payload.get("dimension_scores") or {}
        provider_meta = payload.get("provider_meta") or {}

        return {
            "mastery_score": payload.get("mastery_score", 0.0),
            "concept_score": dimension_scores.get("concept", 0.0),
            "mechanism_score": dimension_scores.get("mechanism", 0.0),
            "boundary_score": dimension_scores.get("boundary", 0.0),
            "misconception_score": dimension_scores.get("misconception", 0.0),
            "trace_id": provider_meta.get("trace_id"),
        }

    def generate_rag_cards(
        self,
        *,
        deck: dict[str, object],
        documents: list[dict[str, object]],
        topics: list[str] | None = None,
        generation_prefs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        response = self.client.post(
            f"{self.base_url}/v1/rag/cards/generate",
            json={
                "schema_version": "v1",
                "deck": deck,
                "documents": documents,
                "topics": topics,
                "generation_prefs": generation_prefs or {},
            },
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "deck": payload.get("deck") or deck,
            "cards": payload.get("cards") or [],
            "knowledge_units": payload.get("knowledge_units") or [],
            "warnings": payload.get("warnings") or [],
            "provider_meta": payload.get("provider_meta") or {},
        }

    def close(self) -> None:
        if self._owns_client:
            self.client.close()
