# Input: structured knowledge points, parsed blocks, and a local block index.
# Output: retrieval query text and ordered context records for local RAG prompts.
# Role: combine structured point fields with same-document semantic and neighbor retrieval.
# Note: retrieval is CPU-only and has no model-loading side effects.

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from textbook_qa.local_rag.index import LocalBlockIndex, SearchResult
from textbook_qa.structured_kp import BlockType, DocumentBlock, StructuredKnowledgePoint


@dataclass(frozen=True)
class RetrievedContext:
    block_id: str
    text: str
    score: float
    rank: int
    line_start: int
    line_end: int
    heading_path: list[str]
    source_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


def build_retrieval_query(point: StructuredKnowledgePoint) -> str:
    """Build a lexical query from all structured fields useful for retrieval."""

    parts: list[str] = []
    _append(parts, point.title)
    _append(parts, point.statement)
    _append(parts, point.formula)
    parts.extend(condition.strip() for condition in point.conditions if condition.strip())

    for variable in point.variables:
        variable_parts = []
        _append(variable_parts, variable.symbol)
        _append(variable_parts, variable.meaning)
        _append(variable_parts, variable.condition)
        if variable_parts:
            symbol = variable.symbol.strip()
            meaning = variable.meaning.strip()
            condition = variable.condition.strip()
            if symbol and meaning:
                rendered = f"{symbol}: {meaning}"
                if condition:
                    rendered = f"{rendered} ({condition})"
                parts.append(rendered)
            else:
                parts.append(" ".join(variable_parts))

    parts.extend(mistake.strip() for mistake in point.common_mistakes if mistake.strip())

    for span in point.evidence:
        _append(parts, span.section_title)
        _append(parts, span.text)

    return "\n".join(parts)


def retrieve_contexts(
    point: StructuredKnowledgePoint,
    blocks: Sequence[DocumentBlock],
    index: LocalBlockIndex,
    top_k: int = 4,
    neighbor_window: int = 1,
) -> list[RetrievedContext]:
    if top_k <= 0 and neighbor_window <= 0:
        return []
    if not blocks and not getattr(index, "blocks", []):
        return []

    source_id = _source_id_for_point(point, blocks)
    query = build_retrieval_query(point)
    semantic_hits = index.search(query, top_k=top_k, source_id=source_id) if query.strip() and top_k > 0 else []

    contexts_by_id: dict[str, RetrievedContext] = {}
    for result in semantic_hits:
        contexts_by_id[result.block_id] = _context_from_search_result(result)

    for block in _neighbor_blocks(point, blocks, source_id, max(0, neighbor_window)):
        contexts_by_id.setdefault(block.id, _context_from_block(block))

    return sorted(
        contexts_by_id.values(),
        key=lambda context: (context.source_id, context.line_start, context.line_end, context.block_id),
    )


def _append(parts: list[str], value: str | None) -> None:
    if value and value.strip():
        parts.append(value.strip())


def _source_id_for_point(point: StructuredKnowledgePoint, blocks: Sequence[DocumentBlock]) -> str | None:
    first_span = point.evidence[0] if point.evidence else None
    if first_span is not None:
        metadata_source = first_span.metadata.get("source_id")
        if metadata_source is not None:
            return str(metadata_source)

    block_by_id = {block.id: block for block in blocks}
    for block_id in point.source_block_ids:
        block = block_by_id.get(block_id)
        if block is not None:
            return _block_source_id(block)

    if first_span is not None and first_span.source:
        return str(first_span.source)
    return None


def _neighbor_blocks(
    point: StructuredKnowledgePoint,
    blocks: Sequence[DocumentBlock],
    source_id: str | None,
    neighbor_window: int,
) -> list[DocumentBlock]:
    if not point.source_block_ids or not blocks:
        return []

    seed_ids = set(point.source_block_ids)
    neighbors: list[DocumentBlock] = []
    for index, block in enumerate(blocks):
        if block.id not in seed_ids:
            continue
        start = max(0, index - neighbor_window)
        stop = min(len(blocks), index + neighbor_window + 1)
        for candidate in blocks[start:stop]:
            if source_id is not None and _block_source_id(candidate) != source_id:
                continue
            if not _is_searchable_block(candidate):
                continue
            neighbors.append(candidate)
    return neighbors


_SEARCHABLE_BLOCK_TYPES = {BlockType.PARAGRAPH, BlockType.LIST_ITEM, BlockType.FORMULA}


def _is_searchable_block(block: DocumentBlock) -> bool:
    return block.type in _SEARCHABLE_BLOCK_TYPES and bool(block.text.strip())


def _context_from_search_result(result: SearchResult) -> RetrievedContext:
    return RetrievedContext(
        block_id=result.block_id,
        text=result.text,
        score=result.score,
        rank=result.rank,
        line_start=result.line_start,
        line_end=result.line_end,
        heading_path=list(result.heading_path),
        source_id=result.source_id,
        metadata=deepcopy(result.metadata),
    )


def _context_from_block(block: DocumentBlock) -> RetrievedContext:
    return RetrievedContext(
        block_id=block.id,
        text=block.text,
        score=0.0,
        rank=0,
        line_start=block.line_start,
        line_end=block.line_end,
        heading_path=list(block.heading_path),
        source_id=_block_source_id(block),
        metadata=deepcopy(block.metadata),
    )


def _block_source_id(block: DocumentBlock) -> str:
    source_id = block.metadata.get("source_id")
    return "" if source_id is None else str(source_id)
