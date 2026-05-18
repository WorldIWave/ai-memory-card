# Input: one markdown file plus local extractor, local generator, and optional judge clients.
# Output: P3 PipelineResult with atomic facts, RAG units, candidates, and judge artifacts.
# Role: orchestrate the full P3 local-LLM -> RAG -> candidate QA -> judge flow.
# Note: clients/providers are injectable so tests run without models or API calls.

from __future__ import annotations

import json
from time import perf_counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from textbook_qa.blocks import parse_markdown_blocks
from textbook_qa.llm_client import ChatClient
from textbook_qa.local_rag.aggregation import augment_structured_points_with_aggregates
from textbook_qa.local_rag.concept_units import build_concept_units
from textbook_qa.local_rag.embeddings import LexicalEmbeddingProvider
from textbook_qa.local_rag.index import build_block_index
from textbook_qa.local_rag.knowledge_units import RAGKnowledgeUnit, assemble_rag_unit
from textbook_qa.local_rag.retrieval import retrieve_contexts
from textbook_qa.model_extractors.base import (
    ExtractionProviderRequestError,
    ExtractionProviderResult,
    ExtractorAvailability,
    ModelExtractorProvider,
)
from textbook_qa.model_extractors.normalize import normalize_candidates
from textbook_qa.model_extractors.registry import default_registry, load_extractor_config
from textbook_qa.optimization import optimize_qa_pairs
from textbook_qa.p3_candidate_generation import generate_candidate_qa_pairs
from textbook_qa.qa_guard import filter_qa_pairs
from textbook_qa.p3_judge import JudgeResult, judge_qa_pairs
from textbook_qa.pipeline import InvalidInputError, write_pipeline_outputs
from textbook_qa.preprocessing import preprocess_document
from textbook_qa.schemas import PipelineArtifacts, PipelineResult, TextbookDocument, dataclass_to_dict
from textbook_qa.structured_kp import DocumentBlock, StructuredKnowledgePoint

_TEXT_CONTENT_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
}


@dataclass
class P3PipelineRun:
    result: PipelineResult
    provider_result: ExtractionProviderResult
    availability: ExtractorAvailability
    raw_structured_points: list[StructuredKnowledgePoint]
    structured_points: list[StructuredKnowledgePoint]
    rag_units: list[RAGKnowledgeUnit]
    generation_rag_units: list[RAGKnowledgeUnit]
    candidate_pairs: list[Any]
    qa_guard_rejections: list[dict[str, Any]]
    judge_result: JudgeResult | None
    runtime_metrics: dict[str, Any]


def run_p3_file_pipeline(
    input_path: Path,
    output_dir: Path | None,
    *,
    config_path: Path | None = None,
    extractor_provider: ModelExtractorProvider | None = None,
    local_client: ChatClient | None = None,
    judge_client: ChatClient | None = None,
    language: str = "zh",
    max_candidates: int | None = 80,
    max_candidates_per_unit: int = 5,
    max_final_questions: int | None = 40,
    top_k: int = 4,
    neighbor_window: int = 1,
    prefer_aggregate_units: bool = False,
    prefer_concept_units: bool = True,
    judge_max_pairs_per_call: int = 12,
    candidate_unit_batch_size: int = 1,
    candidate_unit_batch_max_chars: int | None = None,
    candidate_unit_context_max_chars: int | None = None,
    candidate_prompt_profile: str = "default",
    candidate_filter_profile: str = "default",
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> P3PipelineRun:
    if local_client is None:
        raise InvalidInputError("P3 pipeline requires a configured local_client for candidate QA generation.")

    pipeline_start = perf_counter()
    metrics: dict[str, Any] = {"stages": {}, "counts": {}}

    _progress(progress_callback, "read_document", "start")
    stage_start = perf_counter()
    document = _document_from_path(Path(input_path))
    _record_stage(metrics, "read_document_seconds", stage_start)
    _progress(progress_callback, "read_document", "end")

    _progress(progress_callback, "preprocess", "start")
    stage_start = perf_counter()
    cleaned_document, sections, sentences = preprocess_document(document)
    blocks = parse_markdown_blocks(
        cleaned_document.content,
        source_id=cleaned_document.source_path or document.source_path or document.title,
    )
    _remap_blocks_to_original_lines(blocks, cleaned_document.line_map)
    _record_stage(metrics, "preprocess_and_block_parse_seconds", stage_start)
    _progress(progress_callback, "preprocess", "end")

    _progress(progress_callback, "extract", "start")
    stage_start = perf_counter()
    provider_result, availability, raw_structured_points = _extract_points(
        blocks,
        config_path=config_path,
        extractor_provider=extractor_provider,
        event_callback=event_callback,
        progress_callback=progress_callback,
    )
    _record_stage(metrics, "extract_seconds", stage_start)
    _progress(progress_callback, "extract", "end")

    _progress(progress_callback, "augment", "start")
    stage_start = perf_counter()
    structured_points = augment_structured_points_with_aggregates(raw_structured_points)
    _record_stage(metrics, "augment_seconds", stage_start)
    _progress(progress_callback, "augment", "end")
    concept_points = build_concept_units(raw_structured_points) if prefer_concept_units else []
    relation_linked_concept_unit_count = sum(
        1 for point in concept_points if _concept_relation_linked_member_ids(point)
    )
    relation_linked_member_count = sum(
        len(_concept_relation_linked_member_ids(point)) for point in concept_points
    )
    relation_resolutions = [resolution for point in concept_points for resolution in _concept_relation_resolutions(point)]
    relation_resolution_method_counts = _count_values(resolution.get("method", "") for resolution in relation_resolutions)
    support_linked_concept_unit_count = sum(1 for point in concept_points if _concept_support_linked_member_ids(point))
    support_linked_member_count = sum(len(_concept_support_linked_member_ids(point)) for point in concept_points)
    support_role_counts = _count_values(
        member.get("support_role", "")
        for point in concept_points
        for member in _concept_support_linked_members(point)
    )
    rag_seed_points = [*concept_points, *structured_points] if concept_points else list(structured_points)

    provider_result.metadata["raw_structured_point_count"] = len(raw_structured_points)
    provider_result.metadata["aggregate_structured_point_count"] = sum(
        1 for point in structured_points if "aggregation" in point.metadata
    )
    provider_result.metadata["augmented_structured_point_count"] = len(structured_points)
    provider_result.metadata["concept_structured_point_count"] = len(concept_points)
    provider_result.metadata["relation_linked_concept_unit_count"] = relation_linked_concept_unit_count
    provider_result.metadata["relation_linked_member_count"] = relation_linked_member_count
    provider_result.metadata["relation_resolution_count"] = len(relation_resolutions)
    provider_result.metadata["relation_resolution_method_counts"] = relation_resolution_method_counts
    provider_result.metadata["support_linked_concept_unit_count"] = support_linked_concept_unit_count
    provider_result.metadata["support_linked_member_count"] = support_linked_member_count
    provider_result.metadata["support_role_counts"] = support_role_counts

    _progress(progress_callback, "rag", "start")
    stage_start = perf_counter()
    block_index = build_block_index(blocks, LexicalEmbeddingProvider())
    rag_units = [
        assemble_rag_unit(
            point,
            retrieve_contexts(point, blocks, block_index, top_k=top_k, neighbor_window=neighbor_window),
        )
        for point in rag_seed_points
    ]
    grounding_context_counts = _grounding_context_counts(rag_units)
    _record_stage(metrics, "rag_seconds", stage_start)
    _progress(progress_callback, "rag", "end")

    _progress(progress_callback, "select_rag_units", "start")
    stage_start = perf_counter()
    if prefer_aggregate_units:
        generation_rag_units = _select_generation_rag_units(rag_units)
    elif prefer_concept_units:
        generation_rag_units = _select_concept_generation_rag_units(rag_units)
    else:
        generation_rag_units = list(rag_units)
    _record_stage(metrics, "select_rag_units_seconds", stage_start)
    _progress(progress_callback, "select_rag_units", "end")

    _progress(progress_callback, "candidate_generation", "start")
    stage_start = perf_counter()
    candidate_generation_batches: list[dict[str, Any]] = []

    def record_candidate_batch(stats: dict[str, Any]) -> None:
        candidate_generation_batches.append(dict(stats))
        _emit_event(event_callback, "candidate_batch", batch=dict(stats))

    raw_candidate_pairs = generate_candidate_qa_pairs(
        generation_rag_units,
        local_client,
        language=language,
        max_per_unit=max_candidates_per_unit,
        max_total=max_candidates,
        unit_batch_size=candidate_unit_batch_size,
        unit_batch_max_chars=candidate_unit_batch_max_chars,
        unit_context_max_chars=candidate_unit_context_max_chars,
        prompt_profile=candidate_prompt_profile,
        on_pair=lambda pair: _emit_event(event_callback, "qa_candidate", pair=dataclass_to_dict(pair)),
        on_batch=record_candidate_batch,
    )
    raw_support_usage_summary = _support_usage_summary(raw_candidate_pairs)
    if candidate_filter_profile == "skip_qa_guard":
        candidate_pairs = list(raw_candidate_pairs)
        qa_guard_rejections = []
    else:
        candidate_pairs, qa_guard_rejections = filter_qa_pairs(raw_candidate_pairs)
    support_usage_summary = _support_usage_summary(candidate_pairs)
    for diagnostic in raw_support_usage_summary["diagnostics"]:
        if diagnostic.get("support_usage_status") == "unused_required_support":
            _emit_event(event_callback, "qa_support_warning", diagnostic=diagnostic)
    for rejection in qa_guard_rejections:
        _emit_event(event_callback, "qa_rejected", rejection=rejection)
    _record_stage(metrics, "candidate_generation_seconds", stage_start)
    _progress(progress_callback, "candidate_generation", "end")

    _progress(progress_callback, "judge", "start")
    stage_start = perf_counter()
    judge_result = (
        judge_qa_pairs(
            candidate_pairs,
            judge_client,
            max_pairs_per_call=judge_max_pairs_per_call,
            on_decision=lambda decision: _emit_event(event_callback, "judge_decision", decision=dataclass_to_dict(decision)),
            on_final_pair=lambda pair: _emit_event(event_callback, "qa_judged", pair=dataclass_to_dict(pair)),
        )
        if judge_client is not None
        else None
    )
    judge_quality_summary = _judge_quality_summary(judge_result)
    _record_stage(metrics, "judge_seconds", stage_start)
    _progress(progress_callback, "judge", "end")

    _progress(progress_callback, "optimize", "start")
    stage_start = perf_counter()
    final_pairs = judge_result.final_pairs if judge_result is not None else [_mark_judge_skipped(pair) for pair in candidate_pairs]
    final_pairs = optimize_qa_pairs(
        final_pairs,
        max_questions=max_final_questions,
        apply_guard_checks=candidate_filter_profile != "skip_qa_guard",
    )
    for pair in final_pairs:
        _emit_event(event_callback, "qa_final", pair=dataclass_to_dict(pair))
    _record_stage(metrics, "optimize_seconds", stage_start)
    _progress(progress_callback, "optimize", "end")

    result = PipelineResult(
        qa_pairs=final_pairs,
        artifacts=PipelineArtifacts(
            cleaned_document=cleaned_document,
            sections=sections,
            sentences=sentences,
            raw_qa_pairs=raw_candidate_pairs,
            optimized_qa_pairs=final_pairs,
            warnings=list(provider_result.warnings),
            blocks=list(blocks),
            structured_knowledge_points=structured_points,
            schema_qa_pairs=candidate_pairs,
        ),
    )
    metrics["counts"] = {
        "block_count": len(blocks),
        "raw_structured_point_count": len(raw_structured_points),
        "structured_point_count": len(structured_points),
        "concept_structured_point_count": len(concept_points),
        "relation_linked_concept_unit_count": relation_linked_concept_unit_count,
        "relation_linked_member_count": relation_linked_member_count,
        "relation_resolution_count": len(relation_resolutions),
        "support_linked_concept_unit_count": support_linked_concept_unit_count,
        "support_linked_member_count": support_linked_member_count,
        "rag_unit_count": len(rag_units),
        **grounding_context_counts,
        "generation_rag_unit_count": len(generation_rag_units),
        "concept_generation_unit_count": sum(1 for unit in generation_rag_units if _is_concept_rag_unit(unit)),
        "question_plan_count": sum(len(unit.question_plans) for unit in generation_rag_units),
        "skipped_member_rag_unit_count": max(0, len(rag_units) - len(generation_rag_units)),
        "raw_candidate_pair_count": len(raw_candidate_pairs),
        "candidate_pair_count": len(candidate_pairs),
        "qa_guard_rejected_count": len(qa_guard_rejections),
        "support_required_raw_candidate_count": raw_support_usage_summary["required_count"],
        "support_used_raw_candidate_count": raw_support_usage_summary["used_count"],
        "support_unused_raw_candidate_count": raw_support_usage_summary["unused_count"],
        "support_required_candidate_count": support_usage_summary["required_count"],
        "support_used_candidate_count": support_usage_summary["used_count"],
        "support_unused_candidate_count": support_usage_summary["unused_count"],
        "normalization_rejected_count": int(provider_result.metadata.get("normalization_rejected_count", 0) or 0),
        "candidate_unit_batch_size": candidate_unit_batch_size,
        "candidate_unit_batch_max_chars": candidate_unit_batch_max_chars,
        "candidate_unit_context_max_chars": candidate_unit_context_max_chars,
        "candidate_generation_model_call_count": len(candidate_generation_batches),
        "final_pair_count": len(final_pairs),
    }
    metrics["candidate_generation_batches"] = candidate_generation_batches
    metrics["normalization_rejection_counts"] = dict(provider_result.metadata.get("normalization_rejection_counts", {}))
    metrics["relation_diagnostics"] = dict(provider_result.metadata.get("relation_diagnostics", {}))
    metrics["relation_resolution_method_counts"] = relation_resolution_method_counts
    metrics["support_role_counts"] = support_role_counts
    metrics["support_usage_role_counts"] = raw_support_usage_summary["role_counts"]
    metrics["support_usage_diagnostics"] = raw_support_usage_summary["diagnostics"]
    metrics["kept_support_usage_role_counts"] = support_usage_summary["role_counts"]
    metrics["kept_support_usage_diagnostics"] = support_usage_summary["diagnostics"]
    metrics["judge_quality_diagnostics"] = judge_quality_summary
    metrics["judge_decision_counts"] = judge_quality_summary["decision_counts"]
    metrics["judge_failure_mode_counts"] = judge_quality_summary["failure_mode_counts"]
    metrics["judge_module_attribution_counts"] = judge_quality_summary["module_attribution_counts"]
    metrics["judge_quality_gate_counts"] = judge_quality_summary["quality_gate_counts"]
    metrics["judge_dimension_averages"] = judge_quality_summary["dimension_averages"]
    metrics["stages"]["pipeline_compute_seconds"] = _elapsed(pipeline_start)

    run = P3PipelineRun(
        result=result,
        provider_result=provider_result,
        availability=availability,
        raw_structured_points=raw_structured_points,
        structured_points=structured_points,
        rag_units=rag_units,
        generation_rag_units=generation_rag_units,
        candidate_pairs=candidate_pairs,
        qa_guard_rejections=qa_guard_rejections,
        judge_result=judge_result,
        runtime_metrics=metrics,
    )
    if output_dir is not None:
        _write_p3_outputs(run, Path(output_dir))
    return run


def _document_from_path(input_path: Path) -> TextbookDocument:
    if not input_path.exists() or not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    suffix = input_path.suffix.lower()
    content_type = _TEXT_CONTENT_TYPES.get(suffix)
    if content_type is None:
        supported = ", ".join(sorted(_TEXT_CONTENT_TYPES))
        raise InvalidInputError(
            f"Unsupported file extension: {suffix or '<none>'}. Supported extensions: {supported}"
        )
    content = input_path.read_text(encoding="utf-8")
    if not content.strip():
        raise InvalidInputError(f"Input document is empty: {input_path}")
    return TextbookDocument(
        source_path=str(input_path),
        title=input_path.stem,
        content=content,
        metadata={"content_type": content_type},
    )


def _extract_points(
    blocks: Sequence[DocumentBlock],
    *,
    config_path: Path | None,
    extractor_provider: ModelExtractorProvider | None,
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> tuple[ExtractionProviderResult, ExtractorAvailability, list[StructuredKnowledgePoint]]:
    provider_name = getattr(extractor_provider, "name", "local_llm")
    provider = extractor_provider
    if provider is None:
        provider_name = "local_llm"
        config = load_extractor_config(config_path) if config_path is not None else {"providers": {}}
        provider_config = _provider_config(config, provider_name)
        provider = default_registry().create(provider_name, provider_config)

    set_runtime_callbacks = getattr(provider, "set_runtime_callbacks", None)
    if callable(set_runtime_callbacks):
        set_runtime_callbacks(
            event_callback=lambda event, payload: _emit_event(event_callback, event, **payload),
            progress_callback=lambda label: _progress(progress_callback, label, "update"),
        )

    try:
        availability = provider.availability()
    except Exception as exc:
        reason = _warning("availability_failed", exc)
        return ExtractionProviderResult(provider=provider_name, warnings=[reason]), ExtractorAvailability(provider=provider_name, available=False, reason=reason), []
    if not availability.available:
        return ExtractionProviderResult(provider=provider_name, warnings=[availability.reason]), availability, []

    try:
        provider_result = provider.extract(blocks)
    except ExtractionProviderRequestError:
        raise
    except Exception as exc:
        reason = _warning("extract_failed", exc)
        return ExtractionProviderResult(provider=provider_name, warnings=[reason]), availability, []

    try:
        normalization = normalize_candidates(blocks, provider_result.candidates)
        points = normalization.points
        provider_result.metadata.update(
            {
                "normalization_rejected_count": len(normalization.rejections),
                "normalization_rejection_counts": dict(normalization.rejection_counts),
                "normalization_rejections": list(normalization.rejections[:100]),
                "relation_diagnostics": dict(normalization.relation_diagnostics),
            }
        )
    except Exception as exc:
        provider_result.warnings.append(_warning("normalize_failed", exc))
        points = []
    return provider_result, availability, points


def _provider_config(config: dict[str, Any], provider_name: str) -> dict[str, Any]:
    providers = config.get("providers", {})
    if not isinstance(providers, dict):
        return {}
    provider_config = providers.get(provider_name, {})
    return dict(provider_config) if isinstance(provider_config, dict) else {}


def _remap_blocks_to_original_lines(blocks: Sequence[DocumentBlock], line_map: dict[int, int]) -> None:
    if not line_map:
        return
    for block in blocks:
        block.line_start = line_map.get(block.line_start, block.line_start)
        block.line_end = line_map.get(block.line_end, block.line_end)


def _emit_event(callback: Callable[[str, dict[str, Any]], None] | None, event: str, **payload: Any) -> None:
    if callback is None:
        return
    callback(event, payload)


def _progress(callback: Callable[[str, str], None] | None, stage: str, state: str) -> None:
    if callback is None:
        return
    callback(stage, state)


def _grounding_context_counts(rag_units: Sequence[RAGKnowledgeUnit]) -> dict[str, int]:
    structured_item_count = 0
    source_evidence_count = 0
    retrieved_context_count = 0
    char_count = 0
    for unit in rag_units:
        char_count += len(unit.merged_context_text)
        grounding = unit.metadata.get("grounding_context")
        if not isinstance(grounding, dict):
            continue
        structured_item_count += int(grounding.get("structured_item_count", 0) or 0)
        source_evidence_count += int(grounding.get("source_evidence_count", 0) or 0)
        retrieved_context_count += int(grounding.get("retrieved_context_count", 0) or 0)
    return {
        "grounding_context_structured_item_count": structured_item_count,
        "grounding_context_source_evidence_count": source_evidence_count,
        "grounding_context_retrieved_context_count": retrieved_context_count,
        "grounding_context_char_count": char_count,
    }


def _judge_quality_summary(judge_result: JudgeResult | None) -> dict[str, Any]:
    if judge_result is None:
        return {
            "decision_counts": {},
            "failure_mode_counts": {},
            "module_attribution_counts": {},
            "quality_gate_counts": {},
            "dimension_averages": {},
            "decisions": [],
        }

    decision_counts: dict[str, int] = {}
    failure_mode_counts: dict[str, int] = {}
    module_attribution_counts: dict[str, int] = {}
    quality_gate_counts: dict[str, int] = {}
    dimension_totals: dict[str, float] = {}
    dimension_counts: dict[str, int] = {}
    decision_rows: list[dict[str, Any]] = []

    for decision in judge_result.decisions:
        decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1
        if decision.quality_gate_reason:
            quality_gate_counts[decision.quality_gate_reason] = quality_gate_counts.get(decision.quality_gate_reason, 0) + 1
        if decision.module_attribution:
            module_attribution_counts[decision.module_attribution] = module_attribution_counts.get(decision.module_attribution, 0) + 1
        for mode in decision.failure_modes:
            failure_mode_counts[mode] = failure_mode_counts.get(mode, 0) + 1
        for key, value in decision.dimension_scores.items():
            dimension_totals[key] = dimension_totals.get(key, 0.0) + float(value)
            dimension_counts[key] = dimension_counts.get(key, 0) + 1
        decision_rows.append(
            {
                "index": decision.index,
                "decision": decision.decision,
                "score": decision.score,
                "quality_gate_reason": decision.quality_gate_reason,
                "failure_modes": list(decision.failure_modes),
                "module_attribution": decision.module_attribution,
                "dimension_scores": dict(decision.dimension_scores),
                "rationale": decision.rationale,
            }
        )

    dimension_averages = {
        key: round(total / max(1, dimension_counts[key]), 4)
        for key, total in sorted(dimension_totals.items())
    }
    return {
        "decision_counts": decision_counts,
        "failure_mode_counts": failure_mode_counts,
        "module_attribution_counts": module_attribution_counts,
        "quality_gate_counts": quality_gate_counts,
        "dimension_averages": dimension_averages,
        "decisions": decision_rows,
    }


def _support_usage_summary(pairs: Sequence[Any]) -> dict[str, Any]:
    required_count = 0
    used_count = 0
    unused_count = 0
    role_counts: dict[str, int] = {}
    diagnostics: list[dict[str, Any]] = []

    for index, pair in enumerate(pairs):
        metadata = getattr(pair, "metadata", {}) or {}
        required_roles = _unique_strings(metadata.get("required_support_roles", []))
        required_member_ids = _unique_strings(metadata.get("required_support_member_ids", []))
        support_snippets = _unique_strings(metadata.get("support_snippets", []))
        if not (required_roles or required_member_ids or support_snippets):
            continue

        required_count += 1
        for role in required_roles:
            role_counts[role] = role_counts.get(role, 0) + 1

        status = str(metadata.get("support_usage_status", "") or "")
        if status == "used":
            used_count += 1
        elif status == "unused_required_support":
            unused_count += 1

        diagnostics.append(
            {
                "index": index,
                "question": str(getattr(pair, "question", "") or ""),
                "rag_unit_id": str(metadata.get("rag_unit_id", "") or ""),
                "question_plan_id": str(metadata.get("question_plan_id", "") or ""),
                "question_plan_type": str(metadata.get("question_plan_type", "") or ""),
                "support_usage_status": status,
                "required_support_roles": required_roles,
                "required_support_member_ids": required_member_ids,
                "used_support_roles": _unique_strings(metadata.get("used_support_roles", [])),
                "used_support_member_ids": _unique_strings(metadata.get("used_support_member_ids", [])),
                "unused_support_roles": _unique_strings(metadata.get("unused_support_roles", [])),
            }
        )

    return {
        "required_count": required_count,
        "used_count": used_count,
        "unused_count": unused_count,
        "role_counts": role_counts,
        "diagnostics": diagnostics,
    }


def _select_generation_rag_units(rag_units: Sequence[RAGKnowledgeUnit]) -> list[RAGKnowledgeUnit]:
    covered_member_ids: set[str] = set()
    for unit in rag_units:
        aggregation = unit.metadata.get("aggregation")
        if not isinstance(aggregation, dict):
            continue
        member_ids = aggregation.get("member_ids", [])
        if isinstance(member_ids, list):
            covered_member_ids.update(str(item) for item in member_ids if str(item).strip())

    selected: list[RAGKnowledgeUnit] = []
    for unit in rag_units:
        if _is_concept_rag_unit(unit):
            continue
        if unit.seed_point.id in covered_member_ids and "aggregation" not in unit.metadata:
            continue
        selected.append(unit)
    return selected


def _select_concept_generation_rag_units(rag_units: Sequence[RAGKnowledgeUnit]) -> list[RAGKnowledgeUnit]:
    covered_member_ids: set[str] = set()
    absorbed_member_ids: set[str] = set()
    for unit in rag_units:
        concept_unit = unit.seed_point.metadata.get("concept_unit")
        if not isinstance(concept_unit, dict):
            continue
        member_ids = _concept_unit_member_ids(unit.seed_point)
        covered_member_ids.update(member_ids)
        linked_member_ids = _concept_relation_linked_member_ids(unit.seed_point)
        support_member_ids = _concept_support_linked_member_ids(unit.seed_point)
        covered_member_ids.update(linked_member_ids)
        covered_member_ids.update(support_member_ids)
        absorbed_member_ids.update(linked_member_ids)
        absorbed_member_ids.update(support_member_ids)

    selected: list[RAGKnowledgeUnit] = []
    for unit in rag_units:
        if _is_concept_rag_unit(unit):
            member_ids = _concept_unit_member_ids(unit.seed_point)
            is_absorbed_support_unit = bool(member_ids) and all(
                member_id in absorbed_member_ids for member_id in member_ids
            )
            if (
                is_absorbed_support_unit
                and not _concept_relation_linked_member_ids(unit.seed_point)
                and not _concept_support_linked_member_ids(unit.seed_point)
            ):
                continue
            selected.append(unit)
            continue
        aggregation = unit.seed_point.metadata.get("aggregation")
        if isinstance(aggregation, dict):
            aggregate_member_ids = aggregation.get("member_ids", [])
            if isinstance(aggregate_member_ids, list) and any(
                str(member_id) in covered_member_ids for member_id in aggregate_member_ids
            ):
                continue
        if unit.seed_point.id in covered_member_ids:
            continue
        selected.append(unit)
    return selected

def _is_concept_rag_unit(unit: RAGKnowledgeUnit) -> bool:
    return isinstance(unit.seed_point.metadata.get("concept_unit"), dict)


def _concept_unit_member_ids(point: StructuredKnowledgePoint) -> list[str]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    member_ids = concept_unit.get("member_ids", [])
    if not isinstance(member_ids, list):
        return []
    return _unique_strings(member_ids)


def _concept_relation_linked_member_ids(point: StructuredKnowledgePoint) -> list[str]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    member_ids = concept_unit.get("relation_linked_member_ids")
    if isinstance(member_ids, list):
        return _unique_strings(member_ids)
    members = concept_unit.get("relation_linked_members")
    if not isinstance(members, list):
        return []
    return _unique_strings(item.get("member_id") for item in members if isinstance(item, dict))


def _concept_relation_resolutions(point: StructuredKnowledgePoint) -> list[dict[str, str]]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_items = concept_unit.get("relation_resolution")
    if not isinstance(raw_items, list):
        return []

    resolutions: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        resolutions.append(
            {
                "requested_concept": str(item.get("requested_concept", "") or ""),
                "resolved_concept_key": str(item.get("resolved_concept_key", "") or ""),
                "method": str(item.get("method", "") or ""),
            }
        )
    return resolutions


def _concept_support_linked_member_ids(point: StructuredKnowledgePoint) -> list[str]:
    return _unique_strings(item.get("member_id") for item in _concept_support_linked_members(point))


def _concept_support_linked_members(point: StructuredKnowledgePoint) -> list[dict[str, str]]:
    concept_unit = point.metadata.get("concept_unit")
    if not isinstance(concept_unit, dict):
        return []
    raw_items = concept_unit.get("support_linked_members")
    if not isinstance(raw_items, list):
        return []

    members: list[dict[str, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        members.append(
            {
                "member_id": str(item.get("member_id", "") or ""),
                "support_role": str(item.get("support_role", "") or ""),
            }
        )
    return members


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value).strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _unique_strings(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _mark_judge_skipped(pair: Any) -> Any:
    metadata = dict(pair.metadata)
    metadata["judge_decision"] = "skipped"
    return replace(pair, metadata=metadata)


def _write_p3_outputs(run: P3PipelineRun, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_start = perf_counter()
    write_pipeline_outputs(run.result, output_dir)
    (output_dir / "atomic_facts.json").write_text(
        json.dumps(dataclass_to_dict(run.provider_result.candidates), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "provider_result.json").write_text(
        json.dumps(
            {
                "availability": dataclass_to_dict(run.availability),
                "provider_result": dataclass_to_dict(run.provider_result),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "structured_points.json").write_text(
        json.dumps(dataclass_to_dict(run.structured_points), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "rag_units.json").write_text(
        json.dumps(dataclass_to_dict(run.rag_units), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "candidate_qa_pairs.json").write_text(
        json.dumps(dataclass_to_dict(run.candidate_pairs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "qa_guard_rejections.json").write_text(
        json.dumps(run.qa_guard_rejections, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    judge_payload = {
        "decisions": dataclass_to_dict(run.judge_result.decisions) if run.judge_result else [],
        "raw_responses": run.judge_result.raw_responses if run.judge_result else [],
    }
    (output_dir / "judge_decisions.json").write_text(
        json.dumps(judge_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "judge_quality_diagnostics.json").write_text(
        json.dumps(run.runtime_metrics.get("judge_quality_diagnostics", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    run.runtime_metrics["stages"]["artifact_write_seconds"] = _elapsed(write_start)
    (output_dir / "runtime_metrics.json").write_text(
        json.dumps(run.runtime_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _record_stage(metrics: dict[str, Any], name: str, started_at: float) -> None:
    metrics.setdefault("stages", {})[name] = _elapsed(started_at)


def _elapsed(started_at: float) -> float:
    return round(perf_counter() - started_at, 6)


def _warning(prefix: str, exc: Exception) -> str:
    return f"{prefix}:{exc.__class__.__name__}:{exc}"
