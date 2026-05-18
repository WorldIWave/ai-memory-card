from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from textbook_qa.llm_client import ChatClient
from textbook_qa.local_rag.knowledge_units import RAGKnowledgeUnit
from textbook_qa.model_extractors.api_llm import ApiLlmProvider
from textbook_qa.p3_pipeline import P3PipelineRun, run_p3_file_pipeline
from textbook_qa.runtime_config import env_first, float_env, load_env_file
from textbook_qa.schemas import EvidenceSpan, QuestionAnswerPair, QuestionType
from textbook_qa.service_contract import GenerateCardsDocument, GenerateCardsRequest, GenerateCardsResponse

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env.remote"

QUESTION_TYPE_TO_CARD_TYPE = {
    QuestionType.DEFINITION: "recall",
    QuestionType.FORMULA: "recall",
    QuestionType.APPLICATION: "understanding",
    QuestionType.REASONING: "understanding",
    QuestionType.DEEP: "understanding",
    QuestionType.MISCONCEPTION: "boundary",
}

app = FastAPI(title="Textbook QA Service", version="0.1.0")


@app.post("/v1/rag/cards/generate", response_model=GenerateCardsResponse)
def generate_cards_route(payload: GenerateCardsRequest) -> GenerateCardsResponse:
    try:
        return GenerateCardsResponse.model_validate(generate_rag_cards(payload))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "service_unavailable", "message": str(exc)},
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "io_error", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "pipeline_failed", "message": str(exc)},
        ) from exc


def generate_rag_cards(payload: GenerateCardsRequest) -> dict[str, Any]:
    base_url, model, api_key, timeout = _service_runtime_settings()
    trace_id = f"rag-{uuid4().hex[:12]}"

    with TemporaryDirectory(prefix="textbook-qa-service-") as temp_dir:
        temp_root = Path(temp_dir)
        input_path = temp_root / _request_filename(payload.documents)
        input_path.write_text(_combined_markdown(payload.documents), encoding="utf-8")

        run = run_p3_file_pipeline(
            input_path,
            None,
            extractor_provider=_api_extractor_provider(base_url=base_url, model=model, api_key=api_key, timeout=timeout),
            local_client=ChatClient(base_url=base_url, model=model, api_key=api_key, timeout=timeout),
            judge_client=None,
            language=_language(payload),
            max_candidates_per_unit=_max_cards_per_unit(payload),
            candidate_prompt_profile="api_simple",
            candidate_filter_profile="skip_qa_guard",
        )

    knowledge_units, unit_id_by_key = normalize_knowledge_units(
        run.generation_rag_units or run.rag_units,
        source_documents=payload.documents,
    )
    cards = normalize_cards_from_pairs(
        run.result.qa_pairs,
        unit_id_by_key=unit_id_by_key,
        knowledge_units=knowledge_units,
        allowed_card_types=_allowed_card_types(payload),
    )
    cards, normalized_units = filter_cards_and_units_by_topics(cards, knowledge_units, topics=payload.topics)
    warnings = list(run.result.artifacts.warnings)
    if run.result.qa_pairs and not cards and _allowed_card_types(payload) is not None:
        warnings.append("all generated cards were filtered out by the requested card_types")
    if payload.topics and knowledge_units and not normalized_units:
        warnings.append("no generated knowledge units matched the requested topics")

    return {
        "deck": {"name": _deck_name(payload)},
        "cards": cards,
        "knowledge_units": normalized_units,
        "warnings": warnings,
        "provider_meta": _provider_meta(run, trace_id=trace_id, model=model),
    }


def normalize_cards_from_pairs(
    pairs: Sequence[QuestionAnswerPair],
    *,
    unit_id_by_key: dict[str, str] | None = None,
    knowledge_units: Sequence[dict[str, Any]] | None = None,
    allowed_card_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    fallback_unit_id = _fallback_unit_id(unit_id_by_key)
    for pair in pairs:
        card_type = QUESTION_TYPE_TO_CARD_TYPE.get(pair.question_type, "recall")
        if allowed_card_types is not None and card_type not in allowed_card_types:
            continue
        normalized.append(
            {
                "card_type": card_type,
                "front": pair.question,
                "back": pair.answer,
                "render_format": "markdown",
                "tags": ["ai-generated", pair.question_type.value],
                "source_unit_id": _source_unit_id_for_pair(pair, unit_id_by_key, knowledge_units, fallback_unit_id),
            }
        )
    return normalized


def filter_cards_and_units_by_topics(
    cards: Sequence[dict[str, Any]],
    knowledge_units: Sequence[dict[str, Any]],
    *,
    topics: Sequence[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    referenced_unit_ids = {str(card.get("source_unit_id") or "").strip() for card in cards if card.get("source_unit_id")}
    normalized_units = [unit for unit in knowledge_units if unit.get("unit_id") in referenced_unit_ids] if referenced_unit_ids else []
    if not topics:
        return list(cards), normalized_units

    normalized_topics = [_normalize_topic(topic) for topic in topics if _normalize_topic(topic)]
    if not normalized_topics:
        return list(cards), normalized_units

    matching_unit_ids = {
        str(unit.get("unit_id") or "").strip()
        for unit in normalized_units
        if _unit_matches_topics(unit, normalized_topics)
    }
    filtered_cards = [card for card in cards if str(card.get("source_unit_id") or "").strip() in matching_unit_ids]
    filtered_units = [
        unit for unit in normalized_units if str(unit.get("unit_id") or "").strip() in matching_unit_ids
    ]
    return filtered_cards, filtered_units


def normalize_knowledge_units(
    units: Sequence[RAGKnowledgeUnit],
    *,
    source_documents: Sequence[GenerateCardsDocument],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    normalized: list[dict[str, Any]] = []
    unit_id_by_key: dict[str, str] = {}
    seen_ids: set[str] = set()
    default_source_document = _default_source_document(source_documents)

    for index, unit in enumerate(units, start=1):
        topic = _first_non_blank(unit.title, unit.seed_point.title, unit.concept_id, f"Knowledge Unit {index}")
        unit_id = _unique_unit_id(topic, fallback=unit.concept_id or unit.seed_point.id or unit.id, seen_ids=seen_ids)
        concept_definition = _first_non_blank(*unit.results, unit.seed_point.statement, topic)
        primary_evidence = unit.primary_evidence
        metadata = _json_safe(getattr(unit, "metadata", {}) or {})
        concept_unit = metadata.get("concept_unit") if isinstance(metadata, dict) else {}
        if not isinstance(concept_unit, dict):
            concept_unit = {}
        normalized.append(
            {
                "unit_id": unit_id,
                "topic": topic,
                "concept_definition": concept_definition,
                "summary": concept_definition,
                "source_document": default_source_document,
                "source_span": _source_span(primary_evidence),
                "provider_rag_unit_id": unit.id,
                "concept_id": unit.concept_id,
                "knowledge_point_type": unit.type.value,
                "results": list(unit.results),
                "conditions": list(unit.conditions),
                "formulas": list(unit.formulas),
                "misconceptions": list(unit.misconceptions),
                "examples": list(unit.examples),
                "rag_context": str(getattr(unit, "merged_context_text", "") or ""),
                "retrieved_contexts": [
                    _retrieved_context_payload(context)
                    for context in list(getattr(unit, "retrieved_contexts", []) or [])
                ],
                "question_plans": _json_list(getattr(unit, "question_plans", []) or []),
                "rag_metadata": metadata,
                "grounding_context": metadata.get("grounding_context") if isinstance(metadata, dict) else None,
                "support_linked_members": _json_list(concept_unit.get("support_linked_members") or []),
                "relation_linked_members": _json_list(concept_unit.get("relation_linked_members") or []),
                "relation_resolution": _json_safe(concept_unit.get("relation_resolution")),
            }
        )
        for key in _unit_lookup_keys(unit):
            unit_id_by_key[key] = unit_id

    return normalized, unit_id_by_key


def _provider_meta(run: P3PipelineRun, *, trace_id: str, model: str) -> dict[str, Any]:
    counts = run.runtime_metrics.get("counts", {})
    return {
        "trace_id": trace_id,
        "provider_name": "managed_remote_service",
        "mode": "api",
        "model_name": model,
        "raw_candidate_pair_count": counts.get("raw_candidate_pair_count", 0),
        "candidate_pair_count": counts.get("candidate_pair_count", 0),
        "final_pair_count": counts.get("final_pair_count", len(run.result.qa_pairs)),
        "generation_rag_unit_count": counts.get("generation_rag_unit_count", len(run.generation_rag_units)),
    }


def _source_unit_id_for_pair(
    pair: QuestionAnswerPair,
    unit_id_by_key: dict[str, str] | None,
    knowledge_units: Sequence[dict[str, Any]] | None,
    fallback_unit_id: str | None,
) -> str | None:
    metadata = dict(pair.metadata or {})
    direct = _first_non_blank(
        _metadata_text(metadata, "source_unit_id"),
        _metadata_text(metadata, "unit_id"),
        _metadata_text(metadata, "knowledge_unit_id"),
        _metadata_text(metadata, "provider_unit_id"),
    )
    if direct:
        if unit_id_by_key and direct in unit_id_by_key:
            return unit_id_by_key[direct]
        if unit_id_by_key and direct in unit_id_by_key.values():
            return direct
        return direct
    if unit_id_by_key:
        for key in (
            _metadata_text(metadata, "concept_id"),
            _metadata_text(metadata, "rag_unit_id"),
            _metadata_text(metadata, "seed_point_id"),
        ):
            if key and key in unit_id_by_key:
                return unit_id_by_key[key]
    concept_match = _knowledge_unit_id_from_concepts(pair, knowledge_units)
    if concept_match:
        return concept_match
    return fallback_unit_id


def _fallback_unit_id(unit_id_by_key: dict[str, str] | None) -> str | None:
    if not unit_id_by_key:
        return None
    unique_ids = list(dict.fromkeys(unit_id_by_key.values()))
    if len(unique_ids) == 1:
        return unique_ids[0]
    return None


def _allowed_card_types(payload: GenerateCardsRequest) -> set[str] | None:
    raw_value = payload.generation_prefs.get("card_types")
    if not isinstance(raw_value, list):
        return None
    allowed = {str(item).strip() for item in raw_value if str(item).strip()}
    return allowed or None


def _language(payload: GenerateCardsRequest) -> str:
    value = payload.generation_prefs.get("language")
    if value is None:
        return "zh"
    return str(value).strip() or "zh"


def _max_cards_per_unit(payload: GenerateCardsRequest) -> int:
    value = payload.generation_prefs.get("max_cards_per_unit", 3)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3
    return max(1, min(parsed, 10))


def _deck_name(payload: GenerateCardsRequest) -> str:
    raw_name = payload.deck.get("name") if isinstance(payload.deck, dict) else None
    name = str(raw_name or "").strip()
    return name or "AI Generated Cards"


def _request_filename(documents: Sequence[GenerateCardsDocument]) -> str:
    if len(documents) == 1:
        name = Path(documents[0].filename or "document.md").name
        if name:
            return name
    return "service-request.md"


def _combined_markdown(documents: Sequence[GenerateCardsDocument]) -> str:
    parts: list[str] = []
    for index, document in enumerate(documents, start=1):
        title = Path(document.filename or f"document-{index}.md").stem.strip() or f"Document {index}"
        parts.append(f"# {title}")
        parts.append("")
        parts.append(document.text.strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def _api_route_settings() -> tuple[str, str, str, float]:
    base_url = env_first("MCA_TEACHER_OPENAI_BASE_URL", "TEXTBOOK_QA_OPENAI_BASE_URL")
    model = env_first("MCA_TEACHER_OPENAI_MODEL", "TEXTBOOK_QA_OPENAI_MODEL")
    api_key = env_first("MCA_TEACHER_OPENAI_API_KEY", "TEXTBOOK_QA_OPENAI_API_KEY")
    timeout = float_env("MCA_TEACHER_OPENAI_TIMEOUT", float_env("TEXTBOOK_QA_OPENAI_TIMEOUT", 120.0))
    if not base_url or not model:
        raise RuntimeError(
            "api mode requires API configuration via .env.remote shared OpenAI settings."
        )
    return base_url, model, api_key, timeout


@lru_cache(maxsize=1)
def _service_runtime_settings() -> tuple[str, str, str, float]:
    load_env_file(ENV_FILE)
    return _api_route_settings()


def _api_extractor_provider(*, base_url: str, model: str, api_key: str, timeout: float) -> ApiLlmProvider:
    return ApiLlmProvider(
        {
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "timeout": timeout,
            "preselect_enabled": True,
            "adaptive_max_blocks_enabled": True,
            "adaptive_min_blocks": 12,
            "adaptive_max_blocks": 20,
        }
    )


def _default_source_document(documents: Sequence[GenerateCardsDocument]) -> str | None:
    if len(documents) != 1:
        return None
    filename = str(documents[0].filename or "").strip()
    return filename or None


def _source_span(value: EvidenceSpan | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "line_start": value.line_start,
        "line_end": value.line_end,
        "section_title": value.section_title,
        "text": value.text,
    }


def _retrieved_context_payload(context: object) -> dict[str, Any]:
    return {
        "source_id": _object_value(context, "source_id"),
        "block_id": _object_value(context, "block_id"),
        "text": _object_value(context, "text"),
        "line_start": _object_value(context, "line_start"),
        "line_end": _object_value(context, "line_end"),
        "heading_path": _json_safe(_object_value(context, "heading_path", [])),
        "metadata": _json_safe(_object_value(context, "metadata", {})),
    }


def _object_value(value: object, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _json_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        if isinstance(value, tuple):
            value = list(value)
        else:
            return []
    safe = _json_safe(value)
    return safe if isinstance(safe, list) else []


def _json_safe(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())  # type: ignore[attr-defined]
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return str(value)


def _unit_lookup_keys(unit: RAGKnowledgeUnit) -> list[str]:
    values = [
        unit.id,
        unit.concept_id,
        unit.seed_point.id,
        _metadata_text(unit.metadata, "concept_id"),
        _metadata_text(unit.metadata, "source_unit_id"),
    ]
    return [value for value in dict.fromkeys(values) if value]


def _unique_unit_id(topic: str, *, fallback: str, seen_ids: set[str]) -> str:
    base = _slugify(topic) or _slugify(fallback) or "unit"
    candidate = f"ku_{base}"
    if candidate not in seen_ids:
        seen_ids.add(candidate)
        return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in seen_ids:
        suffix += 1
    unique = f"{candidate}_{suffix}"
    seen_ids.add(unique)
    return unique


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered)
    normalized = normalized.strip("_")
    return normalized[:48]


def _metadata_text(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _first_non_blank(*values: str | None) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_topic(value: str) -> str:
    return " ".join(value.casefold().split())


def _unit_matches_topics(unit: dict[str, Any], topics: Sequence[str]) -> bool:
    haystacks = [
        _normalize_topic(str(unit.get("topic") or "")),
        _normalize_topic(str(unit.get("concept_definition") or "")),
        _normalize_topic(str(unit.get("summary") or "")),
    ]
    for topic in topics:
        for haystack in haystacks:
            if haystack and (topic in haystack or haystack in topic):
                return True
    return False


def _knowledge_unit_id_from_concepts(
    pair: QuestionAnswerPair,
    knowledge_units: Sequence[dict[str, Any]] | None,
) -> str | None:
    if not knowledge_units:
        return None
    normalized_concepts = [_normalize_topic(concept) for concept in pair.concepts if _normalize_topic(concept)]
    if not normalized_concepts:
        return None

    matches: list[str] = []
    for unit in knowledge_units:
        topic = _normalize_topic(str(unit.get("topic") or ""))
        if not topic:
            continue
        if any(topic == concept or topic in concept or concept in topic for concept in normalized_concepts):
            unit_id = str(unit.get("unit_id") or "").strip()
            if unit_id:
                matches.append(unit_id)
    unique_matches = list(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return None
