# Input: model-backed StructuredKnowledgePoint fragments from one document.
# Output: aggregate StructuredKnowledgePoint seeds plus original points for Local RAG.
# Role: merge same-block and nearby section fragments into fuller P2.5 knowledge units.
# Note: aggregation is deterministic and avoids provider/model dependencies.

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Any

from textbook_qa.schemas import EvidenceSpan
from textbook_qa.structured_kp import KnowledgePointType, StructuredKnowledgePoint, VariableDefinition

_TYPE_PRIORITY = {
    KnowledgePointType.MISCONCEPTION: 50,
    KnowledgePointType.FORMULA: 40,
    KnowledgePointType.APPLICATION: 30,
    KnowledgePointType.PROCEDURE: 25,
    KnowledgePointType.DEFINITION: 20,
    KnowledgePointType.NOTATION: 10,
    KnowledgePointType.DEEP_REASONING: 5,
}
_TITLE_TYPE_PRIORITY = {
    KnowledgePointType.DEFINITION: 40,
    KnowledgePointType.NOTATION: 30,
    KnowledgePointType.APPLICATION: 20,
    KnowledgePointType.FORMULA: 10,
    KnowledgePointType.MISCONCEPTION: 5,
}
_SECTION_MAX_LINE_GAP = 3

_CONCEPT_SUFFIXES = (
    "\u6982\u5ff5",
    "\u5b9a\u4e49",
    "\u5b9a\u7406",
    "\u516c\u5f0f",
    "\u51fd\u6570",
    "\u53d8\u91cf",
    "\u77e9\u9635",
    "\u5411\u91cf",
    "\u5206\u5e03",
    "\u6982\u7387",
    "\u671f\u671b",
    "\u65b9\u5dee",
    "\u7b97\u6cd5",
    "\u6a21\u578b",
)


def aggregate_structured_points(points: Sequence[StructuredKnowledgePoint]) -> list[StructuredKnowledgePoint]:
    """Merge same-block extraction fragments into one richer structured point."""
    groups: "OrderedDict[tuple[str, str, str], list[StructuredKnowledgePoint]]" = OrderedDict()
    for point in points:
        groups.setdefault(_group_key(point), []).append(point)

    aggregated: list[StructuredKnowledgePoint] = []
    for group in groups.values():
        if len(group) == 1:
            aggregated.append(deepcopy(group[0]))
            continue
        aggregated.append(_aggregate_group(group, strategy="same_block"))
    return aggregated


def augment_structured_points_with_aggregates(
    points: Sequence[StructuredKnowledgePoint],
) -> list[StructuredKnowledgePoint]:
    """Add aggregate KU seeds before original points so coverage is preserved."""
    same_block_groups: "OrderedDict[tuple[str, str, str], list[StructuredKnowledgePoint]]" = OrderedDict()
    for point in points:
        same_block_groups.setdefault(_group_key(point), []).append(point)

    aggregates: list[StructuredKnowledgePoint] = []
    aggregates.extend(_neighbor_section_aggregates(points))
    for group in same_block_groups.values():
        if len(group) > 1:
            aggregates.append(_aggregate_group(group, strategy="same_block"))

    return [*aggregates, *(deepcopy(point) for point in points)]


def _neighbor_section_aggregates(points: Sequence[StructuredKnowledgePoint]) -> list[StructuredKnowledgePoint]:
    section_groups: "OrderedDict[tuple[str, str], list[StructuredKnowledgePoint]]" = OrderedDict()
    for point in points:
        key = _section_key(point)
        if key[0] and key[1]:
            section_groups.setdefault(key, []).append(point)

    aggregates: list[StructuredKnowledgePoint] = []
    seen_member_sets: set[tuple[str, ...]] = set()
    for group in section_groups.values():
        for neighbors in _neighbor_groups(group):
            member_ids = tuple(point.id for point in neighbors)
            if member_ids in seen_member_sets:
                continue
            seen_member_sets.add(member_ids)
            aggregates.append(_aggregate_group(neighbors, strategy="neighbor_section"))
    return aggregates


def _neighbor_groups(points: Sequence[StructuredKnowledgePoint]) -> list[list[StructuredKnowledgePoint]]:
    ordered = sorted(points, key=lambda point: (_line_start(point), _line_end(point), point.id))
    groups: list[list[StructuredKnowledgePoint]] = []
    current: list[StructuredKnowledgePoint] = []
    for point in ordered:
        if not current:
            current = [point]
            continue
        if _line_gap(current[-1], point) <= _SECTION_MAX_LINE_GAP:
            current.append(point)
            continue
        _append_neighbor_group(groups, current)
        current = [point]
    _append_neighbor_group(groups, current)
    return groups


def _append_neighbor_group(groups: list[list[StructuredKnowledgePoint]], group: list[StructuredKnowledgePoint]) -> None:
    if len(group) <= 1:
        return
    if len({_block_id(point) for point in group}) <= 1:
        return
    groups.append(list(group))


def _section_key(point: StructuredKnowledgePoint) -> tuple[str, str]:
    evidence = point.evidence[0] if point.evidence else None
    source = evidence.source if evidence else ""
    section = evidence.section_title if evidence and evidence.section_title else ""
    return source, section


def _line_gap(left: StructuredKnowledgePoint, right: StructuredKnowledgePoint) -> int:
    return max(0, _line_start(right) - _line_end(left) - 1)


def _line_start(point: StructuredKnowledgePoint) -> int:
    if point.evidence:
        return point.evidence[0].line_start
    return 0


def _line_end(point: StructuredKnowledgePoint) -> int:
    if point.evidence:
        return point.evidence[0].line_end
    return _line_start(point)


def _block_id(point: StructuredKnowledgePoint) -> str:
    evidence = point.evidence[0] if point.evidence else None
    if evidence:
        block_id = str(evidence.metadata.get("block_id") or "")
        if block_id:
            return block_id
    if point.source_block_ids:
        return point.source_block_ids[0]
    return point.id


def _group_key(point: StructuredKnowledgePoint) -> tuple[str, str, str]:
    evidence = point.evidence[0] if point.evidence else None
    source = evidence.source if evidence else ""
    section = evidence.section_title if evidence and evidence.section_title else ""
    block_id = _block_id(point)
    if not block_id and evidence:
        block_id = f"{evidence.line_start}-{evidence.line_end}"
    return source, section, block_id


def _aggregate_group(group: Sequence[StructuredKnowledgePoint], *, strategy: str) -> StructuredKnowledgePoint:
    members = [deepcopy(point) for point in group]
    title_point = max(members, key=_title_score)
    evidence = _merge_evidence([item for point in members for item in point.evidence])
    source_block_ids = _unique(item for point in members for item in point.source_block_ids)
    formulas = [point.formula.strip() for point in members if point.formula.strip()]
    variables = _merge_variables_from_points(members)
    conditions = _merge_conditions(members)
    common_mistakes = _unique(
        mistake.strip()
        for point in members
        for mistake in point.common_mistakes
        if mistake and mistake.strip()
    )
    metadata = deepcopy(title_point.metadata)
    metadata["aggregation"] = {
        "strategy": strategy,
        "member_ids": [point.id for point in members],
        "member_titles": [point.title for point in members],
        "member_types": [point.type.value for point in members],
    }

    return StructuredKnowledgePoint(
        id=_aggregate_id(members),
        type=max((point.type for point in members), key=lambda item: _TYPE_PRIORITY.get(item, 0)),
        title=title_point.title.strip(),
        statement=_statement_from_evidence(evidence) or _longest_text(point.statement for point in members),
        conditions=conditions,
        formula=formulas[0] if formulas else "",
        variables=variables,
        common_mistakes=common_mistakes,
        source_block_ids=source_block_ids,
        evidence=evidence,
        confidence=max(point.confidence for point in members),
        metadata=metadata,
    )


def _title_score(point: StructuredKnowledgePoint) -> tuple[float, int, int]:
    title = point.title.strip()
    score = float(_TITLE_TYPE_PRIORITY.get(point.type, 0)) + float(point.confidence)
    if _contains_cjk(title) and any(title.endswith(suffix) for suffix in _CONCEPT_SUFFIXES):
        score += 20.0
    if _looks_like_symbol_or_number(title):
        score -= 30.0
    if len(title) <= 1:
        score -= 10.0
    return score, len(title), -len(point.id)


def _looks_like_symbol_or_number(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", stripped):
        return True
    if stripped.startswith("$") and stripped.endswith("$"):
        inner = stripped.strip("$").strip()
        return bool(re.fullmatch(r"[A-Za-z](?:[_^]?[A-Za-z0-9{}]+)?", inner))
    return False


def _merge_evidence(items: Sequence[EvidenceSpan]) -> list[EvidenceSpan]:
    if not items:
        return []
    first = items[0]
    source = first.source
    section = first.section_title
    line_start = min(item.line_start for item in items)
    line_end = max(item.line_end for item in items)
    text = "\n".join(_unique(item.text.strip() for item in items if item.text.strip()))
    metadata: dict[str, Any] = deepcopy(first.metadata)
    metadata["aggregated_evidence_count"] = len(items)
    metadata["block_ids"] = _unique(str(item.metadata.get("block_id")) for item in items if item.metadata.get("block_id"))
    return [
        EvidenceSpan(
            source=source,
            text=text,
            line_start=line_start,
            line_end=line_end,
            section_title=section,
            metadata=metadata,
        )
    ]


def _statement_from_evidence(evidence: Sequence[EvidenceSpan]) -> str:
    if not evidence:
        return ""
    return evidence[0].text.strip()


def _merge_conditions(points: Sequence[StructuredKnowledgePoint]) -> list[str]:
    values: list[str] = []
    for point in points:
        values.extend(point.conditions)
        if point.type in {KnowledgePointType.APPLICATION, KnowledgePointType.PROCEDURE} and point.statement.strip():
            values.append(point.statement.strip())
    return _unique(value.strip() for value in values if value and value.strip())


def _merge_variables_from_points(points: Sequence[StructuredKnowledgePoint]) -> list[VariableDefinition]:
    groups: list[list[VariableDefinition]] = [list(point.variables) for point in points]
    inferred = [_notation_variable(point) for point in points]
    groups.append([variable for variable in inferred if variable is not None])
    return _merge_variables(groups)


def _notation_variable(point: StructuredKnowledgePoint) -> VariableDefinition | None:
    if point.type is not KnowledgePointType.NOTATION:
        return None
    symbol = _clean_symbol(point.title)
    if not symbol or _looks_like_long_phrase(symbol):
        return None
    meaning = _notation_meaning(point.title, symbol, point.statement)
    if not meaning:
        return None
    condition = "; ".join(condition.strip() for condition in point.conditions if condition and condition.strip())
    return VariableDefinition(symbol=symbol, meaning=meaning, condition=condition)


def _notation_meaning(raw_symbol: str, clean_symbol: str, statement: str) -> str:
    cleaned_statement = statement.strip().rstrip(".\u3002")
    if not cleaned_statement:
        return ""
    symbol_patterns = [re.escape(raw_symbol.strip()), re.escape(clean_symbol)]
    predicates = (
        r"(?:is|means|denotes|represents|indicates|stands\s+for|"
        r"\u8868\u793a|\u4ee3\u8868|\u662f|\u4e3a|\u6307|\u79f0\u4e3a|\u5b9a\u4e49\u4e3a)"
    )
    for symbol_pattern in symbol_patterns:
        if not symbol_pattern:
            continue
        match = re.match(rf"^\s*{symbol_pattern}\s*{predicates}\s*(?P<meaning>.+?)\s*$", cleaned_statement, re.IGNORECASE)
        if match:
            return _clean_meaning(match.group("meaning"))
    if cleaned_statement.casefold() in {raw_symbol.strip().casefold(), clean_symbol.casefold()}:
        return ""
    return _clean_meaning(cleaned_statement)


def _clean_meaning(text: str) -> str:
    meaning = text.strip().strip(":,; ")
    meaning = re.sub(r"^(?:the|a|an)\s+", "", meaning, flags=re.IGNORECASE)
    return meaning.strip()


def _clean_symbol(text: str) -> str:
    symbol = text.strip().strip("` ")
    if symbol.startswith("$") and symbol.endswith("$") and len(symbol) >= 2:
        symbol = symbol[1:-1].strip()
    return symbol


def _looks_like_long_phrase(text: str) -> bool:
    return len(text) > 32 or bool(re.search(r"\s", text.strip()))


def _merge_variables(groups: Iterable[Sequence[VariableDefinition]]) -> list[VariableDefinition]:
    merged: list[VariableDefinition] = []
    seen: set[tuple[str, str, str]] = set()
    for variables in groups:
        for variable in variables:
            key = (variable.symbol, variable.meaning, variable.condition)
            if key in seen:
                continue
            seen.add(key)
            merged.append(deepcopy(variable))
    return merged


def _aggregate_id(points: Sequence[StructuredKnowledgePoint]) -> str:
    digest = hashlib.sha1("|".join(point.id for point in points).encode("utf-8")).hexdigest()[:12]
    return f"agg-skp-{digest}"


def _longest_text(values: Iterable[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    return max(cleaned, key=len) if cleaned else ""


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
