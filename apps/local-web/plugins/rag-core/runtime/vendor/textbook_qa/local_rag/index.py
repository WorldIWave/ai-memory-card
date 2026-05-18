# Input: parsed textbook blocks and a CPU embedding provider.
# Output: in-memory searchable block index and ranked retrieval results.
# Role: provide deterministic local retrieval over parsed textbook content.
# Note: this module has no model-loading side effects and does not require a GPU.

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from textbook_qa.local_rag.embeddings import cosine_similarity
from textbook_qa.structured_kp import BlockType, DocumentBlock


class EmbeddingProvider(Protocol):
    """Encode text snippets into dense vectors."""

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector for each input text."""


@dataclass(frozen=True)
class IndexedBlock:
    block_id: str
    text: str
    heading_path: list[str]
    line_start: int
    line_end: int
    source_id: str
    block_type: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchResult:
    block_id: str
    text: str
    score: float
    rank: int
    line_start: int
    line_end: int
    heading_path: list[str]
    source_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


_SEARCHABLE_BLOCK_TYPES = {BlockType.PARAGRAPH, BlockType.LIST_ITEM, BlockType.FORMULA}


class LocalBlockIndex:
    """Search a small in-memory collection of embedded textbook blocks."""

    def __init__(self, blocks: Sequence[IndexedBlock], embedding_provider: EmbeddingProvider) -> None:
        self.blocks = list(blocks)
        self.embedding_provider = embedding_provider

    def search(self, query: str, top_k: int = 4, source_id: str | None = None) -> list[SearchResult]:
        if top_k <= 0:
            return []

        candidates = [block for block in self.blocks if source_id is None or block.source_id == source_id]
        if not candidates:
            return []

        query_embedding = self.embedding_provider.encode([query])[0]
        scored = [
            (cosine_similarity(query_embedding, block.embedding), block)
            for block in candidates
        ]
        scored.sort(key=lambda item: (-item[0], item[1].line_start, item[1].block_id))

        return [
            SearchResult(
                block_id=block.block_id,
                text=block.text,
                score=score,
                rank=rank,
                line_start=block.line_start,
                line_end=block.line_end,
                heading_path=list(block.heading_path),
                source_id=block.source_id,
                metadata=deepcopy(block.metadata),
            )
            for rank, (score, block) in enumerate(scored[:top_k], start=1)
        ]


def build_block_index(blocks: Sequence[DocumentBlock], embedding_provider: EmbeddingProvider) -> LocalBlockIndex:
    searchable_blocks = [block for block in blocks if _is_searchable(block)]
    embeddings = embedding_provider.encode([block.text for block in searchable_blocks])
    if len(embeddings) != len(searchable_blocks):
        raise ValueError(
            f"Expected {len(searchable_blocks)} embeddings for searchable blocks, got {len(embeddings)}"
        )

    indexed_blocks = [
        IndexedBlock(
            block_id=block.id,
            text=block.text,
            heading_path=list(block.heading_path),
            line_start=block.line_start,
            line_end=block.line_end,
            source_id=_normalize_source_id(block.metadata.get("source_id")),
            block_type=block.type.value,
            embedding=list(embedding),
            metadata=deepcopy(block.metadata),
        )
        for block, embedding in zip(searchable_blocks, embeddings)
    ]
    return LocalBlockIndex(indexed_blocks, embedding_provider)


def _is_searchable(block: DocumentBlock) -> bool:
    return block.type in _SEARCHABLE_BLOCK_TYPES and bool(block.text.strip())


def _normalize_source_id(source_id: Any) -> str:
    return "" if source_id is None else str(source_id)
