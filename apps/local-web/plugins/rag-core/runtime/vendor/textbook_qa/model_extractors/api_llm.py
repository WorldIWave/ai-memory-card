# Input: document blocks plus API-backed OpenAI-compatible LLM endpoint configuration.
# Output: provider-neutral extraction candidates from API-emitted atomic facts.
# Role: expose the full-API extraction route without reintroducing the legacy rule pipeline.
# Note: behavior is shared with the local extractor implementation; only route identity differs.

from __future__ import annotations

from textbook_qa.model_extractors.local_llm import LocalLlmProvider


class ApiLlmProvider(LocalLlmProvider):
    name = "api_llm"
