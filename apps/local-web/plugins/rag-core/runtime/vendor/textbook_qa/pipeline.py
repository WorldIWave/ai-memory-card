# Input: validated pipeline results and output directories.
# Output: JSON and Markdown artifacts for the supported routes.
# Role: keep shared serialization helpers separate from route orchestration.
# Note: this module intentionally no longer contains the removed legacy rule pipeline.

from __future__ import annotations

import json
from pathlib import Path

from textbook_qa.optimization import artifacts_to_jsonable, markdown_report, qa_pairs_to_jsonable
from textbook_qa.schemas import PipelineResult


class InvalidInputError(ValueError):
    """Raised when an input document cannot be processed."""



def write_pipeline_outputs(result: PipelineResult, output_dir: Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "qa_pairs.json").write_text(
        json.dumps(qa_pairs_to_jsonable(result.qa_pairs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "qa_pairs.md").write_text(
        markdown_report(result.qa_pairs),
        encoding="utf-8",
    )
    (output_dir / "artifacts.json").write_text(
        json.dumps(
            artifacts_to_jsonable(result.artifacts),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
