from __future__ import annotations

from runtime.app.document_budget import estimate_text_tokens, optimize_generation_prefs


def test_estimate_text_tokens_counts_english_and_chinese_text() -> None:
    english = " ".join(["memory"] * 1000)
    chinese = "记忆卡片复习策略" * 100

    assert 740 <= estimate_text_tokens(english) <= 820
    assert 1100 <= estimate_text_tokens(chinese) <= 1400


def test_optimize_generation_prefs_batches_medium_document_for_long_context_models() -> None:
    document = {"filename": "chapter.md", "text": "\n\n".join(["机器学习模型需要泛化能力。"] * 3000)}

    optimized = optimize_generation_prefs(
        [document],
        {
            "language": "zh",
            "extractor_batch_mode": "block",
            "max_cards_per_unit": 3,
        },
    )

    assert optimized["extractor_batch_mode"] == "token-window"
    assert optimized["extractor_batch_max_chars"] >= 120_000
    assert optimized["extractor_max_chars"] >= 16_000
    assert optimized["candidate_unit_batch_size"] >= 4
    assert optimized["judge_max_pairs_per_call"] >= 20
    assert optimized["adaptive_batching"]["strategy"] == "single-pass"


def test_optimize_generation_prefs_respects_explicit_batch_overrides() -> None:
    optimized = optimize_generation_prefs(
        [{"filename": "note.md", "text": "short note"}],
        {
            "adaptive_batching_enabled": True,
            "extractor_batch_mode": "section",
            "extractor_batch_max_chars": 12_000,
            "candidate_unit_batch_size": 2,
            "judge_max_pairs_per_call": 6,
        },
    )

    assert optimized["extractor_batch_mode"] == "section"
    assert optimized["extractor_batch_max_chars"] == 12_000
    assert optimized["candidate_unit_batch_size"] == 2
    assert optimized["judge_max_pairs_per_call"] == 6


def test_optimize_generation_prefs_marks_oversized_documents_for_chunk_safe_processing() -> None:
    huge_text = "世界模型假设与工作记忆眨眼机制。" * 260_000

    optimized = optimize_generation_prefs(
        [{"filename": "huge.md", "text": huge_text}],
        {
            "model_context_tokens": 400_000,
            "reserved_output_tokens": 40_000,
            "target_chunk_tokens": 100_000,
        },
    )

    assert optimized["adaptive_batching"]["strategy"] == "chunk-safe"
    assert optimized["adaptive_batching"]["estimated_tokens"] > 360_000
    assert optimized["extractor_batch_mode"] == "token-window"
    assert optimized["extractor_batch_max_chars"] <= 180_000
