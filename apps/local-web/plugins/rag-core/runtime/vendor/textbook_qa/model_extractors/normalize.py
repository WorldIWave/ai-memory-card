# Input: document blocks and provider-neutral model extraction candidates.
# Output: structured knowledge points normalized for downstream QA generation.
# Role: convert pretrained extractor spans and relations into stable knowledge records.
# Note: keep this adapter deterministic and independent of pipeline integration.

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from textbook_qa.model_extractors.base import ExtractionCandidate
from textbook_qa.schemas import EvidenceSpan
from textbook_qa.structured_kp import (
    DocumentBlock,
    KnowledgePointType,
    KnowledgeRelation,
    StructuredKnowledgePoint,
    VariableDefinition,
)

_RELATION_LABELS = {
    "defines",
    "used_for",
    "condition_of",
    "part_of",
    "contrasts_with",
    "prerequisite_of",
}
_APPLICATION_LABELS = {"application", "procedure", "deep_reasoning", "condition", "result", "worked_example", "example", "\u5e94\u7528", "\u7528\u9014", "\u6761\u4ef6", "\u7ed3\u679c"}
_FORMULA_LABELS = {"formula", "\u516c\u5f0f"}
_DEFINITION_LABELS = {"definition", "concept", "term", "knowledge_point", "\u77e5\u8bc6\u70b9", "\u6982\u5ff5", "\u5b9a\u4e49", "\u672f\u8bed"}
_NOTATION_LABELS = {"symbol", "variable", "notation", "\u7b26\u53f7", "\u53d8\u91cf"}
_MISCONCEPTION_LABELS = {"misconception", "mistake", "common_mistake", "\u6613\u9519\u70b9", "\u8bef\u533a", "\u5e38\u89c1\u9519\u8bef", "\u9519\u8bef"}
_NON_INSTRUCTIONAL_ROLES = {
    "metadata",
    "course_logistics",
    "navigation",
    "tooling_instruction",
    "administrative",
    "assignment_submission",
    "assignment_instruction",
    "account_setup",
    "source_note",
    "non_instructional",
    "other_non_instructional",
    "download_instruction",
}


@dataclass
class NormalizationResult:
    points: list[StructuredKnowledgePoint] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    rejection_counts: dict[str, int] = field(default_factory=dict)
    relation_diagnostics: dict[str, Any] = field(default_factory=dict)


def normalize_candidates(
    blocks: Sequence[DocumentBlock], candidates: Sequence[ExtractionCandidate]
) -> NormalizationResult:
    block_by_id = {block.id: block for block in blocks}
    points: list[StructuredKnowledgePoint] = []
    rejections: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()
    seen: set[tuple[str, str, int, int, str, str]] = set()

    for candidate in candidates:
        block = block_by_id.get(candidate.block_id)
        if block is None:
            _reject(rejections, rejection_counts, candidate, "missing_block")
            continue

        text = candidate.text.strip()
        if not text:
            _reject(rejections, rejection_counts, candidate, "empty_text", block)
            continue

        point_type = _point_type(candidate.label)
        if point_type is None:
            _reject(rejections, rejection_counts, candidate, "unsupported_label", block)
            continue

        content_role = _normalize_role(candidate.attributes.get("content_role"))
        if content_role in _NON_INSTRUCTIONAL_ROLES:
            _reject(rejections, rejection_counts, candidate, "non_instructional_content_role", block)
            continue

        standalone = _optional_bool(candidate.attributes.get("standalone"), default=True)
        if standalone is False:
            _reject(rejections, rejection_counts, candidate, "not_standalone", block)
            continue

        source_id = _source_id(block)
        title = _title(point_type, candidate, text)
        statement = _string_attr(candidate.attributes.get("statement")) or block.text.strip()
        if point_type not in {KnowledgePointType.FORMULA, KnowledgePointType.NOTATION} and _is_fragment_concept(title, statement):
            _reject(rejections, rejection_counts, candidate, "fragment_concept", block)
            continue

        key = (point_type.value, title.casefold(), block.line_start, block.line_end, candidate.block_id, source_id)
        if key in seen:
            _reject(rejections, rejection_counts, candidate, "duplicate", block)
            continue
        seen.add(key)

        points.append(_point(point_type, title, block, candidate, text, source_id, standalone))

    return NormalizationResult(
        points=points,
        rejections=rejections,
        rejection_counts=dict(rejection_counts),
        relation_diagnostics=_aggregate_relation_diagnostics(points),
    )


def candidates_to_structured_points(
    blocks: Sequence[DocumentBlock], candidates: Sequence[ExtractionCandidate]
) -> list[StructuredKnowledgePoint]:
    return normalize_candidates(blocks, candidates).points


def _reject(
    rejections: list[dict[str, Any]],
    rejection_counts: Counter[str],
    candidate: ExtractionCandidate,
    reason: str,
    block: DocumentBlock | None = None,
) -> None:
    rejection_counts[reason] += 1
    rejection = {
        "reason": reason,
        "provider": candidate.provider,
        "block_id": candidate.block_id,
        "label": candidate.label,
        "text": candidate.text,
    }
    if block is not None:
        rejection["line_start"] = block.line_start
        rejection["line_end"] = block.line_end
    rejections.append(rejection)


def _point_type(label: str) -> KnowledgePointType | None:
    normalized = _normalize_label(label)
    if normalized in _RELATION_LABELS or normalized in _APPLICATION_LABELS:
        return KnowledgePointType.APPLICATION
    if normalized in _FORMULA_LABELS:
        return KnowledgePointType.FORMULA
    if normalized in _NOTATION_LABELS:
        return KnowledgePointType.NOTATION
    if normalized in _MISCONCEPTION_LABELS:
        return KnowledgePointType.MISCONCEPTION
    if normalized in _DEFINITION_LABELS:
        return KnowledgePointType.DEFINITION
    return None


def _normalize_label(label: str) -> str:
    normalized = label.strip().casefold().replace("-", "_")
    if normalized.startswith(("b_", "i_")):
        normalized = normalized[2:]
    return normalized


def _normalize_role(value: object) -> str:
    return _string_attr(value).casefold().replace("-", "_").replace(" ", "_")


def _title(point_type: KnowledgePointType, candidate: ExtractionCandidate, text: str) -> str:
    concept = _string_attr(candidate.attributes.get("concept")) or _string_attr(candidate.attributes.get("title"))
    if concept:
        return concept
    if point_type is KnowledgePointType.APPLICATION:
        head = _string_attr(candidate.attributes.get("head"))
        if head:
            return head
    return text


def _point(
    point_type: KnowledgePointType,
    title: str,
    block: DocumentBlock,
    candidate: ExtractionCandidate,
    text: str,
    source_id: str,
    standalone: bool,
) -> StructuredKnowledgePoint:
    metadata: dict[str, Any] = {
        "provider": candidate.provider,
        "candidate_label": candidate.label,
        "candidate_confidence": candidate.confidence,
        "start_char": candidate.start_char,
        "end_char": candidate.end_char,
        "candidate_attributes": dict(candidate.attributes),
    }
    content_role = _string_attr(candidate.attributes.get("content_role"))
    if content_role:
        metadata["content_role"] = content_role
    evidence_text = _string_attr(candidate.attributes.get("evidence_text"))
    if evidence_text:
        metadata["evidence_text"] = evidence_text
        metadata["evidence_text_found"] = evidence_text in block.text
    if point_type is KnowledgePointType.APPLICATION:
        metadata.update(
            {
                "relation": candidate.label,
                "relation_head": _string_attr(candidate.attributes.get("head")),
                "relation_tail": _string_attr(candidate.attributes.get("tail")),
            }
        )

    statement = _string_attr(candidate.attributes.get("statement"))
    if not statement:
        statement = text if point_type is KnowledgePointType.APPLICATION else block.text.strip()
    formula = _string_attr(candidate.attributes.get("formula"))
    if not formula and point_type is KnowledgePointType.FORMULA:
        formula = text
    conditions = _string_list_attr(candidate.attributes.get("conditions"))
    common_mistakes = _string_list_attr(candidate.attributes.get("common_mistakes"))
    if not common_mistakes and point_type is KnowledgePointType.MISCONCEPTION:
        common_mistakes = [text]
    relations, relation_diagnostics = _relations_attr(candidate.attributes.get("relations"), block)
    if relation_diagnostics["raw_relation_count"]:
        metadata["relation_diagnostics"] = relation_diagnostics
    digest = hashlib.sha1(
        "|".join(
            [
                point_type.value,
                title.casefold(),
                str(block.line_start),
                str(block.line_end),
                candidate.block_id,
                source_id,
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]

    return StructuredKnowledgePoint(
        id=f"model-skp-{digest}",
        type=point_type,
        title=title,
        statement=statement,
        conditions=conditions,
        formula=formula,
        variables=_variables_attr(candidate.attributes.get("variables")),
        common_mistakes=common_mistakes,
        source_block_ids=[block.id],
        evidence=[_evidence(block, source_id)],
        confidence=_optional_float(candidate.confidence) or 0.0,
        metadata=metadata,
        fact_type=_string_attr(candidate.attributes.get("fact_type")) or point_type.value,
        pedagogical_value=_optional_float(candidate.attributes.get("pedagogical_value")) or 0.0,
        standalone=standalone,
        relations=relations,
    )


def _evidence(block: DocumentBlock, source_id: str) -> EvidenceSpan:
    return EvidenceSpan(
        source=source_id,
        text=block.text,
        line_start=block.line_start,
        line_end=block.line_end,
        section_title=block.heading_path[-1] if block.heading_path else None,
        metadata={"block_id": block.id, "heading_path": list(block.heading_path), **block.metadata},
    )


def _source_id(block: DocumentBlock) -> str:
    return str(block.metadata.get("source_id") or block.id.split(":", 1)[0] or "document")


def _string_attr(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _string_list_attr(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, parsed))


def _optional_bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return default


def _variables_attr(value: object) -> list[VariableDefinition]:
    if not isinstance(value, list):
        return []
    variables: list[VariableDefinition] = []
    for item in value:
        if isinstance(item, dict):
            symbol = _string_attr(item.get("symbol") or item.get("name"))
            meaning = _string_attr(item.get("meaning") or item.get("description"))
            condition = _string_attr(item.get("condition"))
        else:
            symbol = _string_attr(item)
            meaning = ""
            condition = ""
        if symbol or meaning:
            variables.append(VariableDefinition(symbol=symbol, meaning=meaning, condition=condition))
    return variables


def _relations_attr(value: object, block: DocumentBlock) -> tuple[list[KnowledgeRelation], dict[str, Any]]:
    if not isinstance(value, list):
        return [], _relation_diagnostics()
    relations: list[KnowledgeRelation] = []
    seen: set[tuple[str, str, str, str]] = set()
    relation_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    raw_count = 0
    evidence_found_count = 0
    evidence_missing_count = 0
    for item in value:
        raw_count += 1
        if not isinstance(item, dict):
            rejection_counts["invalid_relation_object"] += 1
            continue
        relation_type = _normalize_relation_type(item.get("type") or item.get("relation_type"))
        source_concept = _string_attr(item.get("source_concept") or item.get("source"))
        target_concept = _string_attr(item.get("target_concept") or item.get("target"))
        evidence_text = _string_attr(item.get("evidence_text"))
        if relation_type not in _RELATION_LABELS:
            rejection_counts["unsupported_relation_type"] += 1
            continue
        if not source_concept or not target_concept:
            rejection_counts["missing_endpoint"] += 1
            continue
        key = (relation_type, source_concept.casefold(), target_concept.casefold(), evidence_text)
        if key in seen:
            rejection_counts["duplicate_relation"] += 1
            continue
        seen.add(key)
        relation_counts[relation_type] += 1
        if evidence_text and evidence_text in block.text:
            evidence_found_count += 1
        else:
            evidence_missing_count += 1
        relations.append(
            KnowledgeRelation(
                type=relation_type,
                source_concept=source_concept,
                target_concept=target_concept,
                evidence_text=evidence_text,
                confidence=_optional_float(item.get("confidence")) or 0.0,
            )
        )
    return relations, _relation_diagnostics(
        raw_relation_count=raw_count,
        relation_counts_by_type=relation_counts,
        relation_rejection_counts=rejection_counts,
        relation_evidence_found_count=evidence_found_count,
        relation_evidence_missing_count=evidence_missing_count,
    )


def _relation_diagnostics(
    *,
    raw_relation_count: int = 0,
    relation_counts_by_type: Counter[str] | None = None,
    relation_rejection_counts: Counter[str] | None = None,
    relation_evidence_found_count: int = 0,
    relation_evidence_missing_count: int = 0,
) -> dict[str, Any]:
    type_counts = dict(sorted((relation_counts_by_type or Counter()).items()))
    rejection_counts = dict(sorted((relation_rejection_counts or Counter()).items()))
    valid_count = sum(type_counts.values())
    invalid_count = sum(rejection_counts.values())
    mapping_denominator = relation_evidence_found_count + relation_evidence_missing_count
    return {
        "raw_relation_count": raw_relation_count,
        "valid_relation_count": valid_count,
        "invalid_relation_count": invalid_count,
        "relation_counts_by_type": type_counts,
        "relation_rejection_counts": rejection_counts,
        "relation_evidence_found_count": relation_evidence_found_count,
        "relation_evidence_missing_count": relation_evidence_missing_count,
        "relation_evidence_mapping_rate": round(relation_evidence_found_count / mapping_denominator, 6) if mapping_denominator else 0.0,
    }


def _aggregate_relation_diagnostics(points: Sequence[StructuredKnowledgePoint]) -> dict[str, Any]:
    raw_count = 0
    found_count = 0
    missing_count = 0
    type_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    for point in points:
        diagnostics = point.metadata.get("relation_diagnostics")
        if not isinstance(diagnostics, dict):
            continue
        raw_count += _int_attr(diagnostics.get("raw_relation_count"))
        found_count += _int_attr(diagnostics.get("relation_evidence_found_count"))
        missing_count += _int_attr(diagnostics.get("relation_evidence_missing_count"))
        type_counts.update(_counter_attr(diagnostics.get("relation_counts_by_type")))
        rejection_counts.update(_counter_attr(diagnostics.get("relation_rejection_counts")))
    return _relation_diagnostics(
        raw_relation_count=raw_count,
        relation_counts_by_type=type_counts,
        relation_rejection_counts=rejection_counts,
        relation_evidence_found_count=found_count,
        relation_evidence_missing_count=missing_count,
    )


def _counter_attr(value: object) -> Counter[str]:
    counts: Counter[str] = Counter()
    if isinstance(value, dict):
        for key, raw_count in value.items():
            counts[str(key)] += _int_attr(raw_count)
    return counts


def _int_attr(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _normalize_relation_type(value: object) -> str:
    return _string_attr(value).casefold().replace("-", "_").replace(" ", "_")


def _is_fragment_concept(title: str, statement: str) -> bool:
    title = title.strip()
    statement = statement.strip()
    if not title:
        return True
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", title):
        return True

    normalized_title = re.sub(r"\s+", " ", title).strip()
    normalized_statement = re.sub(r"\s+", " ", statement).strip()
    if normalized_title.casefold() == normalized_statement.casefold() and len(normalized_title) <= 12:
        return True

    if len(normalized_title) <= 8 and normalized_title.endswith(("\u7684", "\u5730", "\u5f97")):
        return True

    if _is_chinese_prefix_fragment(normalized_title, normalized_statement):
        return True

    if (
        re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", normalized_title)
        and normalized_title.casefold() == normalized_statement.casefold()
        and len(normalized_title) <= 24
    ):
        return True

    return False


def _is_chinese_prefix_fragment(title: str, statement: str) -> bool:
    if not re.fullmatch(r"[\u4e00-\u9fff]{1,4}", title):
        return False
    pattern = re.compile(
        re.escape(title)
        + r"(?P<suffix>[\u4e00-\u9fff]{1,6})(?:\u662f|\u4e3a|\u6307|\u8868\u793a|\u79f0\u4e3a|\u5b9a\u4e49\u4e3a|\u901a\u5e38\u79f0\u4e3a)"
    )
    discourse_prefixes = (
        "\u901a\u5e38",
        "\u4e00\u822c",
        "\u53ef\u4ee5",
        "\u4e5f",
        "\u5219",
        "\u65f6",
        "\u82e5",
    )
    for match in pattern.finditer(statement):
        suffix = match.group("suffix")
        if suffix.startswith(discourse_prefixes):
            continue
        return True
    return False
