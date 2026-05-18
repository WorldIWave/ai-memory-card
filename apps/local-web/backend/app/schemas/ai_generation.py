# Input: 前端上传文件读取后的文本、牌组名和生成偏好  |  Output: AI 生成导入请求/响应 DTO
# Role: 定义本地 /api/ai/rag/import-cards 与远端 RAG provider 之间的数据契约
# Note: documents 接收纯文本，不直接接收二进制文件；知识单元暂随响应返回不入库
# Usage: routes/ai.py 与 services/rag_import_service.py 共享这些 schema
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.card import CardRead
from app.schemas.deck import DeckRead


class RAGImportDocument(BaseModel):
    filename: str = "document.txt"
    content_type: str = "text/plain"
    text: str

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("document text is required")
        return value


class RAGImportGenerationPrefs(BaseModel):
    backend: Literal["extractive", "llm"] = "llm"
    card_types: list[str] = Field(default_factory=lambda: ["recall", "understanding", "boundary"])
    max_cards_per_unit: int = Field(default=3, ge=1, le=10)
    language: str = "zh"
    max_candidates: int | None = Field(default=None, ge=1)
    max_final_questions: int | None = Field(default=None, ge=1)
    candidate_unit_batch_size: int | None = Field(default=None, ge=1)
    candidate_batch_max_chars: int | None = Field(default=None, ge=1)
    candidate_context_max_chars: int | None = Field(default=None, ge=1)
    judge_max_pairs_per_call: int | None = Field(default=None, ge=1)
    adaptive_batching_enabled: bool = True
    model_context_tokens: int | None = Field(default=None, ge=1)
    reserved_output_tokens: int | None = Field(default=None, ge=1)
    target_chunk_tokens: int | None = Field(default=None, ge=1)
    extractor_batch_mode: Literal["block", "section", "token-window"] = "block"
    extractor_max_blocks: int | None = Field(default=None, ge=1)
    extractor_max_chars: int | None = Field(default=None, ge=1)
    extractor_max_tokens: int | None = Field(default=None, ge=1)
    extractor_batch_max_chars: int | None = Field(default=None, ge=1)
    extractor_preselect_max_blocks: int | None = Field(default=None, ge=1)
    extractor_preselect_min_score: float | None = Field(default=None, ge=0)
    disable_extractor_preselect: bool = False
    disable_extractor_adaptive_max_blocks: bool = False
    extractor_adaptive_min_blocks: int | None = Field(default=None, ge=1)
    extractor_adaptive_max_blocks_limit: int | None = Field(default=None, ge=1)
    prefer_aggregate_units: bool = False


class RAGImportCardsRequest(BaseModel):
    deck_id: int | None = Field(default=None, ge=1)
    deck_name: str | None = None
    documents: list[RAGImportDocument] = Field(min_length=1)
    topics: list[str] | None = None
    generation_prefs: RAGImportGenerationPrefs = Field(default_factory=RAGImportGenerationPrefs)

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [topic.strip() for topic in value if topic and topic.strip()]
        return normalized or None


class RAGImportCardsResponse(BaseModel):
    deck: DeckRead
    cards: list[CardRead]
    imported_count: int
    knowledge_units: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider_meta: dict[str, Any] = Field(default_factory=dict)
