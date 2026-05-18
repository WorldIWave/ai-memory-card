from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-_'][A-Za-z0-9]+)*")
_DEFAULT_MODEL_CONTEXT_TOKENS = 400_000
_DEFAULT_RESERVED_OUTPUT_TOKENS = 40_000
_DEFAULT_TARGET_CHUNK_TOKENS = 100_000
_MIN_BATCH_CHARS = 16_000
_MAX_BATCH_CHARS = 180_000


def estimate_text_tokens(text: str) -> int:
    value = str(text or "")
    cjk_count = len(_CJK_RE.findall(value))
    latin_word_count = len(_LATIN_WORD_RE.findall(value))
    non_space_count = sum(1 for char in value if not char.isspace())
    accounted_chars = cjk_count + sum(len(match.group(0)) for match in _LATIN_WORD_RE.finditer(value))
    symbol_count = max(0, non_space_count - accounted_chars)
    estimate = cjk_count * 1.5 + latin_word_count * 0.78 + symbol_count * 0.35
    return max(1, int(round(estimate)))


def optimize_generation_prefs(
    documents: Sequence[Mapping[str, Any]],
    preferences: Mapping[str, Any] | None,
) -> dict[str, Any]:
    optimized = dict(preferences or {})
    if not _bool_pref(optimized, "adaptive_batching_enabled", True):
        return optimized

    estimated_tokens = sum(estimate_text_tokens(str(document.get("text") or "")) for document in documents)
    context_tokens = _int_pref(optimized, "model_context_tokens", _DEFAULT_MODEL_CONTEXT_TOKENS, minimum=16_000)
    reserved_tokens = _int_pref(
        optimized,
        "reserved_output_tokens",
        min(_DEFAULT_RESERVED_OUTPUT_TOKENS, max(4_000, context_tokens // 10)),
        minimum=1_000,
    )
    usable_tokens = max(4_000, context_tokens - reserved_tokens)
    target_chunk_tokens = min(
        _int_pref(optimized, "target_chunk_tokens", _DEFAULT_TARGET_CHUNK_TOKENS, minimum=4_000),
        usable_tokens,
    )
    batch_chars = _batch_chars_for_token_budget(target_chunk_tokens)
    strategy = "chunk-safe" if estimated_tokens > usable_tokens else "single-pass"

    _set_default(optimized, "extractor_batch_mode", "token-window", replace_values={"block", ""})
    _set_default(optimized, "extractor_batch_max_chars", batch_chars)
    _set_default(optimized, "extractor_max_chars", min(batch_chars, 16_000))
    _set_default(optimized, "candidate_unit_batch_size", 6)
    _set_default(optimized, "candidate_batch_max_chars", min(batch_chars, 80_000))
    _set_default(optimized, "candidate_context_max_chars", 4_000)
    _set_default(optimized, "judge_max_pairs_per_call", 20)

    adaptive_meta = dict(optimized.get("adaptive_batching") or {})
    adaptive_meta.update(
        {
            "enabled": True,
            "strategy": strategy,
            "estimated_tokens": estimated_tokens,
            "model_context_tokens": context_tokens,
            "reserved_output_tokens": reserved_tokens,
            "usable_input_tokens": usable_tokens,
            "target_chunk_tokens": target_chunk_tokens,
            "batch_max_chars": batch_chars,
        }
    )
    optimized["adaptive_batching"] = adaptive_meta
    return optimized


def _batch_chars_for_token_budget(token_budget: int) -> int:
    return max(_MIN_BATCH_CHARS, min(_MAX_BATCH_CHARS, int(token_budget * 1.6)))


def _set_default(
    target: dict[str, Any],
    key: str,
    value: Any,
    *,
    replace_values: set[Any] | None = None,
) -> None:
    current = target.get(key)
    if current is None or current == "" or (replace_values is not None and current in replace_values):
        target[key] = value


def _bool_pref(preferences: Mapping[str, Any], key: str, default: bool) -> bool:
    value = preferences.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _int_pref(preferences: Mapping[str, Any], key: str, default: int, *, minimum: int) -> int:
    value = preferences.get(key)
    if value is None or value == "":
        return max(minimum, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return max(minimum, default)
    return max(minimum, parsed)
