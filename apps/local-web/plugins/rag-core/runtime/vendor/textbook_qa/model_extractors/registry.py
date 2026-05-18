# Input: provider names, provider factories, and model extractor JSON config paths.
# Output: provider registry instances and parsed extractor configuration data.
# Role: centralize creation of optional model-backed extractor providers.
# Note: keep imports lazy so optional pretrained dependencies are not required at import time.

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

ProviderFactory = Callable[[dict[str, Any] | None], Any]


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        self._factories[name] = factory

    def create(self, name: str, config: dict[str, Any] | None = None) -> Any:
        try:
            factory = self._factories[name]
        except KeyError as exc:
            available = ", ".join(self.names()) or "none"
            raise KeyError(
                f"Unknown model extractor provider {name!r}. Available providers: {available}"
            ) from exc
        return factory(config)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


def load_extractor_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {"providers": {}}
    with config_path.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def _lazy_provider_factory(module_name: str, class_name: str) -> ProviderFactory:
    def factory(config: dict[str, Any] | None = None) -> Any:
        module = importlib.import_module(module_name)
        provider_class = getattr(module, class_name)
        return provider_class(config)

    return factory


def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        "local_llm",
        _lazy_provider_factory("textbook_qa.model_extractors.local_llm", "LocalLlmProvider"),
    )
    return registry
