# Input: Mock HTTP 响应（含维度分数、mastery_score 等字段）  |  Output: 断言字段映射正确
# Role: 单元测试 RemoteHTTPAIProvider，验证远端 AI 评测响应能正确映射为内部结构
# Note: 使用 httpx.MockTransport 拦截网络请求，无需真实远端服务即可运行
# Usage: pytest tests/test_remote_ai_provider.py，测试隔离，无外部依赖
from __future__ import annotations

import httpx

from app.providers.ai.remote_http import RemoteHTTPAIProvider


def test_remote_ai_provider_maps_response() -> None:
    payload = {
        "dimension_scores": {
            "concept": 2,
            "mechanism": 2,
            "boundary": 1,
            "misconception": 3,
        },
        "mastery_score": 0.67,
        "weak_points": ["boundary conditions"],
        "reinforcement_advice": ["review failure modes"],
        "provider_meta": {
            "provider_name": "autodl",
            "model_name": "qwen",
            "prompt_version": "v1",
            "rubric_version": "v1",
            "trace_id": "trace-1",
            "latency_ms": 500,
        },
    }

    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    provider = RemoteHTTPAIProvider(base_url="http://example.com", client=client)

    result = provider.evaluate_explanation(
        target_unit={"topic": "RAG"},
        learner_explanation="retrieval plus generation",
    )

    assert result["mastery_score"] == 0.67
    assert result["trace_id"] == "trace-1"


def test_remote_ai_provider_posts_rag_card_generation_request() -> None:
    seen_request: httpx.Request | None = None
    payload = {
        "deck": {"name": "ML"},
        "cards": [
            {
                "card_type": "recall",
                "front": "What is RAG?",
                "back": "Retrieval augmented generation.",
                "render_format": "markdown",
                "tags": ["ai-generated"],
                "source_unit_id": "ku_1",
            }
        ],
        "knowledge_units": [{"unit_id": "ku_1", "topic": "RAG"}],
        "warnings": [],
        "provider_meta": {"trace_id": "rag-1"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_request
        seen_request = request
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = RemoteHTTPAIProvider(base_url="http://example.com", client=client)

    result = provider.generate_rag_cards(
        deck={"name": "ML"},
        documents=[{"filename": "rag.md", "text": "RAG combines retrieval and generation."}],
        topics=["RAG"],
        generation_prefs={"backend": "extractive"},
    )

    assert seen_request is not None
    assert str(seen_request.url) == "http://example.com/v1/rag/cards/generate"
    assert result["provider_meta"]["trace_id"] == "rag-1"
