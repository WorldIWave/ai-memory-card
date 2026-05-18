# Input: structured knowledge points extracted from textbook blocks.
# Output: deterministic concept-centered knowledge units for local RAG.
# Role: merge aliases, formula fragments, evidence, variables, and relations by concept key.
# Note: normalization is structural and avoids textbook-specific vocabulary.

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from copy import deepcopy
from typing import Any, TypeVar

from textbook_qa.schemas import EvidenceSpan
from textbook_qa.structured_kp import KnowledgePointType, KnowledgeRelation, StructuredKnowledgePoint, VariableDefinition

_TYPE_PRIORITY = {
    KnowledgePointType.MISCONCEPTION: 60,
    KnowledgePointType.FORMULA: 50,
    KnowledgePointType.PROCEDURE: 40,
    KnowledgePointType.APPLICATION: 35,
    KnowledgePointType.DEFINITION: 30,
    KnowledgePointType.NOTATION: 20,
    KnowledgePointType.DEEP_REASONING: 10,
}
_TITLE_TYPE_PRIORITY = {
    KnowledgePointType.DEFINITION: 50,
    KnowledgePointType.APPLICATION: 30,
    KnowledgePointType.PROCEDURE: 25,
    KnowledgePointType.NOTATION: 20,
    KnowledgePointType.FORMULA: 10,
    KnowledgePointType.MISCONCEPTION: 5,
    KnowledgePointType.DEEP_REASONING: 5,
}

_T = TypeVar("_T")
_TARGET_OWNED_RELATION_TYPES = {"condition_of", "part_of", "prerequisite_of"}
_SOURCE_OWNED_RELATION_TYPES = {"defines", "used_for"}
_BIDIRECTIONAL_RELATION_TYPES = {"contrasts_with"}
_CONDITION_RELATION_TYPES = {"condition_of", "prerequisite_of"}
_EXAMPLE_FACT_TYPES = {"worked_example", "example"}
_MISCONCEPTION_FACT_TYPES = {"misconception", "mistake", "common_mistake"}
_SUPPORT_TARGET_KEYS = ("target_concept", "support_for", "example_of", "misconception_of", "concept_of")
_EXAMPLE_SUFFIXES = (
    "worked_example",
    "worked example",
    "example",
    "sample",
    "\u4f8b\u9898",
    "\u4f8b\u5b50",
    "\u793a\u4f8b",
)
_MISCONCEPTION_SUFFIXES = (
    "common_mistake",
    "common mistake",
    "misconception",
    "mistake",
    "pitfall",
    "\u6613\u9519\u70b9",
    "\u8bef\u533a",
    "\u5e38\u89c1\u9519\u8bef",
    "\u9519\u8bef",
)


def concept_key(title: str) -> str:
    text = title.strip().casefold()
    text = text.replace("$", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text)
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def build_concept_units(points: Sequence[StructuredKnowledgePoint]) -> list[StructuredKnowledgePoint]:
    groups: "OrderedDict[str, list[StructuredKnowledgePoint]]" = OrderedDict()
    for point in points:
        key = _point_concept_key(point)
        groups.setdefault(key, []).append(point)
    resolver = _concept_resolution_index(groups)
    linked_members = _relation_linked_members(groups, resolver)
    support_members = _support_linked_members(groups, resolver)
    return [
        _merge_group(key, group, linked_members.get(key, []), support_members.get(key, []))
        for key, group in groups.items()
    ]


def _relation_linked_members(
    groups: "OrderedDict[str, list[StructuredKnowledgePoint]]",
    resolver: dict[str, Any],
) -> dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]]:
    linked: dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]] = {key: [] for key in groups}
    seen: set[tuple[str, str, str, str, str, str]] = set()

    for source_group_key, source_members in groups.items():
        for point in source_members:
            for relation in point.relations:
                relation_type = relation.type.strip()
                if relation_type in _TARGET_OWNED_RELATION_TYPES:
                    target_resolution = _resolve_concept_reference(relation.target_concept, resolver)
                    if target_resolution and target_resolution["key"] != source_group_key:
                        _append_relation_link(
                            linked,
                            seen,
                            target_resolution["key"],
                            point,
                            relation,
                            direction="incoming",
                            resolution=target_resolution,
                        )
                elif relation_type in _SOURCE_OWNED_RELATION_TYPES:
                    source_resolution = _resolve_concept_reference(relation.source_concept, resolver)
                    owner_key = source_resolution["key"] if source_resolution else source_group_key
                    target_resolution = _resolve_concept_reference(relation.target_concept, resolver)
                    if owner_key in groups and target_resolution and target_resolution["key"] != owner_key:
                        for target_point in groups[target_resolution["key"]]:
                            _append_relation_link(
                                linked,
                                seen,
                                owner_key,
                                target_point,
                                relation,
                                direction="outgoing",
                                resolution=target_resolution,
                            )
                elif relation_type in _BIDIRECTIONAL_RELATION_TYPES:
                    source_resolution = _resolve_concept_reference(relation.source_concept, resolver)
                    target_resolution = _resolve_concept_reference(relation.target_concept, resolver)
                    if (
                        source_resolution
                        and target_resolution
                        and source_resolution["key"] != target_resolution["key"]
                    ):
                        for target_point in groups[target_resolution["key"]]:
                            _append_relation_link(
                                linked,
                                seen,
                                source_resolution["key"],
                                target_point,
                                relation,
                                direction="outgoing",
                                resolution=target_resolution,
                            )
                        for source_point in groups[source_resolution["key"]]:
                            _append_relation_link(
                                linked,
                                seen,
                                target_resolution["key"],
                                source_point,
                                relation,
                                direction="incoming",
                                resolution=source_resolution,
                            )
    return linked


def _support_linked_members(
    groups: "OrderedDict[str, list[StructuredKnowledgePoint]]",
    resolver: dict[str, Any],
) -> dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]]:
    linked: dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]] = {key: [] for key in groups}
    seen: set[tuple[str, str, str, str]] = set()

    for source_group_key, source_members in groups.items():
        for point in source_members:
            support_role = _support_role(point)
            if not support_role:
                continue

            target_resolution = _support_target_resolution(point, support_role, source_group_key, groups, resolver)
            if target_resolution is None:
                continue
            _append_support_link(
                linked,
                seen,
                target_resolution["key"],
                point,
                support_role=support_role,
                resolution=target_resolution,
            )
    return linked


def _support_target_resolution(
    point: StructuredKnowledgePoint,
    support_role: str,
    source_group_key: str,
    groups: "OrderedDict[str, list[StructuredKnowledgePoint]]",
    resolver: dict[str, Any],
) -> dict[str, str] | None:
    source_group = groups.get(source_group_key, [])
    has_core_peer = any(_support_role(member) == "" for member in source_group)
    for reference in _support_target_references(point, support_role):
        resolution = _resolve_concept_reference(reference, resolver)
        if resolution is None or resolution["key"] not in groups:
            continue
        if resolution["key"] != source_group_key:
            return resolution
        if has_core_peer:
            return _resolution(reference, source_group_key, "same_concept")

    if has_core_peer:
        return _resolution(source_group_key, source_group_key, "same_concept")
    return None


def _append_support_link(
    linked: dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]],
    seen: set[tuple[str, str, str, str]],
    owner_key: str,
    member: StructuredKnowledgePoint,
    *,
    support_role: str,
    resolution: dict[str, str],
) -> None:
    if owner_key not in linked:
        return
    unique_key = (owner_key, member.id, support_role, resolution["requested_concept"])
    if unique_key in seen:
        return
    seen.add(unique_key)

    metadata: dict[str, Any] = {
        "member_id": member.id,
        "member_title": member.title,
        "support_role": support_role,
        "target_concept": resolution["requested_concept"],
        "resolved_concept_key": resolution["resolved_concept_key"],
        "resolution_method": resolution["method"],
    }
    linked[owner_key].append((member, metadata))


def _support_role(point: StructuredKnowledgePoint) -> str:
    values = [
        _metadata_text(point.metadata, "content_role"),
        _metadata_text(point.metadata, "fact_type"),
        _metadata_text(point.metadata, "candidate_label"),
    ]
    candidate_attributes = point.metadata.get("candidate_attributes")
    if isinstance(candidate_attributes, dict):
        values.extend(
            [
                _metadata_text(candidate_attributes, "content_role"),
                _metadata_text(candidate_attributes, "fact_type"),
                _metadata_text(candidate_attributes, "type"),
                _metadata_text(candidate_attributes, "label"),
            ]
        )
        raw_fact = candidate_attributes.get("raw_fact")
        if isinstance(raw_fact, dict):
            values.extend(
                [
                    _metadata_text(raw_fact, "content_role"),
                    _metadata_text(raw_fact, "fact_type"),
                    _metadata_text(raw_fact, "type"),
                    _metadata_text(raw_fact, "label"),
                ]
            )

    normalized_values = {value.strip().casefold().replace("-", "_").replace(" ", "_") for value in values if value}
    if point.type is KnowledgePointType.MISCONCEPTION or normalized_values & _MISCONCEPTION_FACT_TYPES:
        return "misconception"
    if normalized_values & _EXAMPLE_FACT_TYPES or "worked_example" in normalized_values:
        return "example"
    return ""


def _support_target_references(point: StructuredKnowledgePoint, support_role: str) -> list[str]:
    references: list[str] = []
    references.extend(_support_metadata_references(point.metadata))
    candidate_attributes = point.metadata.get("candidate_attributes")
    if isinstance(candidate_attributes, dict):
        references.extend(_support_metadata_references(candidate_attributes))
        raw_fact = candidate_attributes.get("raw_fact")
        if isinstance(raw_fact, dict):
            references.extend(_support_metadata_references(raw_fact))

    stripped_title = _strip_support_suffix(point.title, support_role)
    if stripped_title and concept_key(stripped_title) != concept_key(point.title):
        references.append(stripped_title)
    return _unique(reference.strip() for reference in references if reference and reference.strip())


def _support_metadata_references(metadata: dict[str, Any]) -> list[str]:
    references: list[str] = []
    for key in _SUPPORT_TARGET_KEYS:
        value = metadata.get(key)
        if isinstance(value, str):
            references.append(value)
        elif isinstance(value, list):
            references.extend(str(item) for item in value if item)
    return references


def _strip_support_suffix(title: str, support_role: str) -> str:
    suffixes = _EXAMPLE_SUFFIXES if support_role == "example" else _MISCONCEPTION_SUFFIXES
    normalized_title = title.strip()
    normalized_key = concept_key(normalized_title)
    for suffix in suffixes:
        suffix_key = concept_key(suffix)
        if suffix_key == "unknown":
            continue
        marker = "_" + suffix_key
        if normalized_key.endswith(marker):
            return normalized_title[: -len(suffix)].strip(" _:-:\uFF1A")
        if normalized_title.casefold().endswith(suffix.casefold()):
            return normalized_title[: -len(suffix)].strip(" _:-:\uFF1A")
    return ""


def _metadata_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _concept_resolution_index(groups: "OrderedDict[str, list[StructuredKnowledgePoint]]") -> dict[str, Any]:
    exact: dict[str, list[tuple[str, str]]] = {}
    searchable: list[tuple[str, str]] = []
    for group_key, members in groups.items():
        _add_resolution_entry(exact, searchable, group_key, group_key, "exact")
        for point in members:
            title_key = concept_key(point.title)
            _add_resolution_entry(exact, searchable, title_key, group_key, "title")
            for aliases in _concept_alias_groups(point.metadata):
                for alias in aliases:
                    alias_key = concept_key(str(alias))
                    _add_resolution_entry(exact, searchable, alias_key, group_key, "alias")
    return {"exact": exact, "searchable": _unique(searchable)}


def _add_resolution_entry(
    exact: dict[str, list[tuple[str, str]]],
    searchable: list[tuple[str, str]],
    lookup_key: str,
    group_key: str,
    method: str,
) -> None:
    if lookup_key == "unknown":
        return
    exact.setdefault(lookup_key, []).append((group_key, method))
    searchable.append((lookup_key, group_key))


def _resolve_concept_reference(reference: str, resolver: dict[str, Any]) -> dict[str, str] | None:
    query_key = concept_key(reference)
    if query_key == "unknown":
        return None

    direct = _unique_resolution_entries(resolver["exact"].get(query_key, []))
    if len(direct) == 1:
        group_key, method = direct[0]
        return _resolution(reference, group_key, method)

    if not _can_use_containment_resolution(query_key):
        return None

    containing_matches = _unique(
        (group_key, "contains")
        for lookup_key, group_key in resolver["searchable"]
        if lookup_key != query_key and (query_key in lookup_key or lookup_key in query_key)
    )
    containing_groups = _unique(group_key for group_key, _method in containing_matches)
    if len(containing_groups) != 1:
        return None
    return _resolution(reference, containing_groups[0], "contains")


def _unique_resolution_entries(entries: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    by_group: "OrderedDict[str, str]" = OrderedDict()
    for group_key, method in entries:
        if group_key not in by_group or by_group[group_key] != "exact":
            by_group[group_key] = method
    return list(by_group.items())


def _resolution(reference: str, group_key: str, method: str) -> dict[str, str]:
    return {
        "requested_concept": reference,
        "resolved_concept_key": group_key,
        "method": method,
        "key": group_key,
    }


def _can_use_containment_resolution(query_key: str) -> bool:
    compact = query_key.replace("_", "")
    return len(compact) >= 6


def _append_relation_link(
    linked: dict[str, list[tuple[StructuredKnowledgePoint, dict[str, Any]]]],
    seen: set[tuple[str, str, str, str, str, str]],
    owner_key: str,
    member: StructuredKnowledgePoint,
    relation: KnowledgeRelation,
    *,
    direction: str,
    resolution: dict[str, str] | None = None,
) -> None:
    if owner_key not in linked:
        return
    unique_key = (
        owner_key,
        member.id,
        relation.type,
        relation.source_concept,
        relation.target_concept,
        direction,
    )
    if unique_key in seen:
        return
    seen.add(unique_key)
    link_metadata: dict[str, Any] = {
        "member_id": member.id,
        "member_title": member.title,
        "relation_type": relation.type,
        "source_concept": relation.source_concept,
        "target_concept": relation.target_concept,
        "direction": direction,
    }
    if resolution is not None and resolution.get("method") not in {"exact", "title"}:
        link_metadata["_resolution"] = {
            "requested_concept": resolution["requested_concept"],
            "resolved_concept_key": resolution["resolved_concept_key"],
            "method": resolution["method"],
        }
    linked[owner_key].append((member, link_metadata))


def _point_concept_key(point: StructuredKnowledgePoint) -> str:
    for aliases in _concept_alias_groups(point.metadata):
        for alias in aliases:
            key = concept_key(str(alias))
            if key != "unknown":
                return key
    if point.relations:
        for relation in point.relations:
            if relation.source_concept:
                key = concept_key(relation.source_concept)
                if key != "unknown":
                    return key
    key = concept_key(point.title)
    if key != "unknown":
        return key
    return _unknown_concept_key(point)


def _concept_alias_groups(metadata: dict[str, Any]) -> list[list[object]]:
    alias_groups: list[list[object]] = []
    aliases = metadata.get("concept_aliases")
    if isinstance(aliases, list):
        alias_groups.append(aliases)
    candidate_attributes = metadata.get("candidate_attributes")
    if isinstance(candidate_attributes, dict):
        nested_aliases = candidate_attributes.get("concept_aliases")
        if isinstance(nested_aliases, list):
            alias_groups.append(nested_aliases)
    return alias_groups


def _unknown_concept_key(point: StructuredKnowledgePoint) -> str:
    digest = hashlib.sha1(point.title.strip().encode("utf-8")).hexdigest()[:12]
    return f"unknown:{digest}:{point.id}"


def _merge_group(
    key: str,
    group: Sequence[StructuredKnowledgePoint],
    relation_links: Sequence[tuple[StructuredKnowledgePoint, dict[str, Any]]] | None = None,
    support_links: Sequence[tuple[StructuredKnowledgePoint, dict[str, Any]]] | None = None,
) -> StructuredKnowledgePoint:
    copied_relation_links = [(deepcopy(point), dict(metadata)) for point, metadata in relation_links or []]
    copied_support_links = [(deepcopy(point), dict(metadata)) for point, metadata in support_links or []]
    support_ids = {point.id for point, _metadata in copied_support_links}
    copied_group = [deepcopy(point) for point in group]
    non_support_members = [point for point in copied_group if point.id not in support_ids]
    core_members = non_support_members or copied_group
    relation_link_members = [point for point, _metadata in copied_relation_links]
    support_link_members = [point for point, _metadata in copied_support_links]
    members = [*core_members, *relation_link_members, *support_link_members]
    title_point = max(core_members, key=_title_score)
    evidence = _merge_evidence([item for point in members for item in point.evidence])
    metadata = deepcopy(title_point.metadata)
    metadata["concept_unit"] = {
        "concept_key": key,
        "member_ids": [point.id for point in core_members],
        "member_types": [point.type.value for point in core_members],
        "member_titles": [point.title for point in core_members],
    }
    if copied_relation_links:
        metadata["concept_unit"]["relation_linked_member_ids"] = [point.id for point in relation_link_members]
        metadata["concept_unit"]["relation_linked_members"] = [
            _public_relation_link_metadata(item_metadata) for _point, item_metadata in copied_relation_links
        ]
        relation_resolution = _relation_resolution_metadata(item_metadata for _point, item_metadata in copied_relation_links)
        if relation_resolution:
            metadata["concept_unit"]["relation_resolution"] = relation_resolution
    if copied_support_links:
        metadata["concept_unit"]["support_linked_member_ids"] = [point.id for point in support_link_members]
        metadata["concept_unit"]["support_linked_members"] = [
            _public_relation_link_metadata(item_metadata) for _point, item_metadata in copied_support_links
        ]
        examples = _merge_examples(copied_support_links)
        if examples:
            metadata["concept_unit"]["examples"] = examples

    return StructuredKnowledgePoint(
        id=_concept_id(key, core_members),
        type=max((point.type for point in core_members), key=lambda item: _TYPE_PRIORITY.get(item, 0)),
        title=title_point.title.strip(),
        statement=_longest(point.statement for point in core_members) or _longest(point.statement for point in members),
        conditions=_merge_conditions(members, copied_relation_links),
        formula=_first_text(point.formula for point in core_members) or _first_text(point.formula for point in members),
        variables=_merge_variables(point.variables for point in members),
        common_mistakes=_merge_common_mistakes(members, copied_support_links),
        source_block_ids=_unique(
            block_id for point in members for block_id in point.source_block_ids if block_id
        ),
        evidence=evidence,
        confidence=max((point.confidence for point in members), default=0.0),
        metadata=metadata,
        fact_type=title_point.fact_type,
        pedagogical_value=max((point.pedagogical_value for point in core_members), default=0.0),
        standalone=all(point.standalone for point in core_members),
        relations=_merge_relations(point.relations for point in members),
    )


def _merge_examples(support_links: Sequence[tuple[StructuredKnowledgePoint, dict[str, Any]]]) -> list[str]:
    examples: list[str] = []
    for point, metadata in support_links:
        if metadata.get("support_role") != "example":
            continue
        examples.extend(_metadata_examples(point.metadata))
        statement = point.statement.strip()
        if statement:
            examples.append(statement)
    return _unique(value.strip() for value in examples if value and value.strip())


def _metadata_examples(metadata: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw_examples = metadata.get("examples")
    if isinstance(raw_examples, list):
        values.extend(str(item) for item in raw_examples if item)
    candidate_attributes = metadata.get("candidate_attributes")
    if isinstance(candidate_attributes, dict):
        raw_nested = candidate_attributes.get("examples")
        if isinstance(raw_nested, list):
            values.extend(str(item) for item in raw_nested if item)
        raw_fact = candidate_attributes.get("raw_fact")
        if isinstance(raw_fact, dict):
            raw_fact_examples = raw_fact.get("examples")
            if isinstance(raw_fact_examples, list):
                values.extend(str(item) for item in raw_fact_examples if item)
    return values


def _merge_common_mistakes(
    members: Sequence[StructuredKnowledgePoint],
    support_links: Sequence[tuple[StructuredKnowledgePoint, dict[str, Any]]],
) -> list[str]:
    values = [value.strip() for point in members for value in point.common_mistakes if value and value.strip()]
    for point, metadata in support_links:
        if metadata.get("support_role") != "misconception":
            continue
        statement = point.statement.strip()
        if statement:
            values.append(statement)
    return _unique(values)


def _public_relation_link_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in metadata.items() if not key.startswith("_")}


def _relation_resolution_metadata(items: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    resolutions: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        resolution = item.get("_resolution")
        if not isinstance(resolution, dict):
            continue
        payload = {
            "requested_concept": str(resolution.get("requested_concept", "") or ""),
            "resolved_concept_key": str(resolution.get("resolved_concept_key", "") or ""),
            "method": str(resolution.get("method", "") or ""),
        }
        key = (payload["requested_concept"], payload["resolved_concept_key"], payload["method"])
        if key in seen:
            continue
        seen.add(key)
        resolutions.append(payload)
    return resolutions


def _merge_conditions(
    members: Sequence[StructuredKnowledgePoint],
    relation_links: Sequence[tuple[StructuredKnowledgePoint, dict[str, Any]]],
) -> list[str]:
    values = [value.strip() for point in members for value in point.conditions if value and value.strip()]
    for point, metadata in relation_links:
        if metadata.get("relation_type") not in _CONDITION_RELATION_TYPES:
            continue
        statement = point.statement.strip()
        if statement:
            values.append(statement)
        for relation in point.relations:
            if relation.type == metadata.get("relation_type") and relation.evidence_text.strip():
                values.append(relation.evidence_text.strip())
    return _unique(values)


def _merge_evidence(items: Sequence[EvidenceSpan]) -> list[EvidenceSpan]:
    if not items:
        return []

    first = items[0]
    text = "\n".join(_unique(item.text.strip() for item in items if item.text and item.text.strip()))
    metadata: dict[str, Any] = deepcopy(first.metadata)
    metadata["block_ids"] = _evidence_block_ids(items)

    return [
        EvidenceSpan(
            source=first.source,
            text=text,
            line_start=min(item.line_start for item in items),
            line_end=max(item.line_end for item in items),
            section_title=first.section_title,
            metadata=metadata,
        )
    ]


def _evidence_block_ids(items: Sequence[EvidenceSpan]) -> list[str]:
    block_ids: list[str] = []
    for item in items:
        block_id = item.metadata.get("block_id")
        if block_id:
            block_ids.append(str(block_id))
        nested = item.metadata.get("block_ids")
        if isinstance(nested, list):
            block_ids.extend(str(value) for value in nested if value)
    return _unique(block_ids)


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


def _merge_relations(groups: Iterable[Sequence[KnowledgeRelation]]) -> list[KnowledgeRelation]:
    merged: list[KnowledgeRelation] = []
    seen: set[tuple[str, str, str, str, float]] = set()
    for relations in groups:
        for relation in relations:
            key = (
                relation.type,
                relation.source_concept,
                relation.target_concept,
                relation.evidence_text,
                relation.confidence,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(deepcopy(relation))
    return merged


def _concept_id(key: str, points: Sequence[StructuredKnowledgePoint]) -> str:
    digest_input = "|".join([key, *(point.id for point in points)])
    digest = hashlib.sha1(digest_input.encode("utf-8")).hexdigest()[:12]
    return f"concept-skp-{digest}"


def _longest(values: Iterable[str]) -> str:
    cleaned = [value.strip() for value in values if value and value.strip()]
    return max(cleaned, key=len) if cleaned else ""


def _first_text(values: Iterable[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _title_score(point: StructuredKnowledgePoint) -> tuple[float, int, int]:
    title = point.title.strip()
    score = float(_TITLE_TYPE_PRIORITY.get(point.type, 0)) + float(point.confidence)
    if _looks_like_symbol(title):
        score -= 30.0
    if not title:
        score -= 100.0
    return score, len(title), -len(point.id)


def _looks_like_symbol(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped.startswith("$") and stripped.endswith("$"):
        return True
    normalized = stripped.replace("_", "").replace("^", "")
    return bool(re.fullmatch(r"[A-Za-z0-9(){}\\]+", normalized)) and len(normalized) <= 12


def _unique(values: Iterable[_T]) -> list[_T]:
    seen: set[_T] = set()
    unique_values: list[_T] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values