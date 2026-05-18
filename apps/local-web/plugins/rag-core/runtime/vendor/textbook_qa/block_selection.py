# Input: parsed textbook DocumentBlock records before model extraction.
# Output: scored and preselected blocks for local LLM extraction.
# Role: reduce slow model calls using structural density, not content blacklists.
# Note: final relevance is decided by model content_role during extraction.

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from statistics import mean
from typing import Any

from textbook_qa.structured_kp import BlockType, DocumentBlock

_INSTRUCTIONAL_SIGNAL_RE = re.compile(
    r"\u5b9a\u4e49|\u5b9a\u7406|\u516c\u5f0f|\u8bc1\u660e|\u63a8\u5bfc|"
    r"\u6761\u4ef6|\u7ed3\u679c|\u6027\u8d28|\u8bef\u533a|\u6613\u9519|"
    r"definition|theorem|formula|proof|derive|condition|result|property|example|misconception|mistake",
    re.IGNORECASE,
)
_MATH_RE = re.compile(r"[$=]|\\(?:theta|frac|sum|left|right|begin|end|times|in|mathbb)")


def score_block(block: DocumentBlock) -> float:
    text = _combined_text(block)
    score = 0.0
    if block.type is BlockType.FORMULA:
        score += 6.0
    elif block.type is BlockType.LIST_ITEM:
        score += 1.0
    elif block.type is BlockType.PARAGRAPH:
        score += 0.5

    if _MATH_RE.search(text):
        score += 3.0
    if len(block.text.strip()) >= 28:
        score += 1.0
    if 40 <= len(block.text.strip()) <= 600:
        score += 0.8

    if _INSTRUCTIONAL_SIGNAL_RE.search(text):
        score += 2.0
    if len(block.text.strip()) <= 16 and not _MATH_RE.search(text):
        score -= 1.5
    return score


def adaptive_block_budget(
    blocks: Sequence[DocumentBlock],
    *,
    min_blocks: int,
    max_blocks: int,
) -> int:
    raw_count = len(blocks)
    if raw_count <= 0:
        return 0
    upper = max(1, max_blocks)
    lower = max(1, min(min_blocks, upper))
    if raw_count <= lower:
        return raw_count
    estimated = math.ceil(math.sqrt(raw_count))
    return min(raw_count, upper, max(lower, estimated))


def preselect_blocks(
    blocks: Sequence[DocumentBlock],
    *,
    max_blocks: int,
    preselect_max_blocks: int,
    min_score: float,
) -> tuple[list[DocumentBlock], dict[str, Any]]:
    raw_blocks = list(blocks)
    scored = [(index, block, score_block(block)) for index, block in enumerate(raw_blocks)]
    above_threshold = [item for item in scored if item[2] >= min_score]
    ranked = sorted(above_threshold, key=lambda item: (-item[2], item[0]))
    limit = max(1, min(max_blocks, preselect_max_blocks))
    selected_ranked = _section_diverse_selection(ranked, limit)
    if not selected_ranked and raw_blocks:
        fallback_ranked = sorted(scored, key=lambda item: (-item[2], item[0]))
        selected_ranked = _section_diverse_selection(fallback_ranked, min(max_blocks, len(scored)))
    selected = [block for _index, block, _score in sorted(selected_ranked, key=lambda item: item[0])]
    scores = [item[2] for item in scored]
    return selected, {
        "raw_eligible_blocks": len(raw_blocks),
        "preselected_blocks": len(selected),
        "skipped_by_preselect": max(0, len(raw_blocks) - len(selected)),
        "preselect_min_score": min_score,
        "preselect_max_blocks": preselect_max_blocks,
        "preselect_score_min": min(scores) if scores else 0.0,
        "preselect_score_max": max(scores) if scores else 0.0,
        "preselect_score_avg": mean(scores) if scores else 0.0,
        "preselected_section_count": len({_section_key(block) for block in selected}),
        "preselect_strategy": "section_diverse_score",
    }


def _section_diverse_selection(
    ranked: Sequence[tuple[int, DocumentBlock, float]],
    limit: int,
) -> list[tuple[int, DocumentBlock, float]]:
    selected: list[tuple[int, DocumentBlock, float]] = []
    selected_indexes: set[int] = set()
    seen_sections: set[tuple[str, ...]] = set()

    for item in ranked:
        index, block, _score = item
        section = _section_key(block)
        if section in seen_sections:
            continue
        selected.append(item)
        selected_indexes.add(index)
        seen_sections.add(section)
        if len(selected) >= limit:
            return selected

    for item in ranked:
        index, _block, _score = item
        if index in selected_indexes:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _section_key(block: DocumentBlock) -> tuple[str, ...]:
    cleaned = tuple(part.strip().casefold() for part in block.heading_path if part.strip())
    return cleaned or ("untitled",)


def _combined_text(block: DocumentBlock) -> str:
    heading = " ".join(block.heading_path)
    return f"{heading}\n{block.text}"
