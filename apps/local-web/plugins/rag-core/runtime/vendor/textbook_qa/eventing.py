# Input: event dictionaries and optional progress labels from pipeline runners.
# Output: JSONL runtime events and optional tqdm progress updates.
# Role: keep streaming/progress UX separate from extraction and QA logic.
# Note: callers may pass None paths or disabled progress for test-friendly no-ops.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlEventWriter:
    """Append runtime events to a JSONL file."""

    def __init__(self, path: Path | None) -> None:
        self.path = Path(path) if path is not None else None
        self._handle = None

    def __enter__(self) -> "JsonlEventWriter":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def open(self) -> None:
        if self.path is None or self._handle is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def emit(self, event: str, **payload: Any) -> None:
        if self.path is None:
            return
        if self._handle is None:
            self.open()
        record = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        assert self._handle is not None
        self._handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._handle is None:
            return
        self._handle.close()
        self._handle = None


class ProgressReporter:
    """Small wrapper around tqdm with a no-op fallback."""

    def __init__(self, *, enabled: bool, total: int | None = None, description: str = "progress") -> None:
        self.enabled = enabled
        self.total = total
        self.description = description
        self.completed = 0
        self.last_label = ""
        self._bar = self._make_bar() if enabled else None

    def update(self, label: str = "", advance: int = 1) -> None:
        self.completed += advance
        self.last_label = label
        if self._bar is None:
            return
        if label:
            self._bar.set_description_str(label)
        self._bar.update(advance)

    def close(self) -> None:
        if self._bar is None:
            return
        self._bar.close()
        self._bar = None

    def _make_bar(self):
        from tqdm import tqdm

        return tqdm(total=self.total, desc=self.description)
