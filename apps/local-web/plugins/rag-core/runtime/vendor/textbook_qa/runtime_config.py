# Input: environment files and extractor runtime options for supported routes.
# Output: runtime config files and resolved environment settings.
# Role: keep route runner configuration separate from deleted evaluation scripts.
# Note: callers use these helpers to build local extractor configs and read optional API env vars.

from __future__ import annotations

import json
import os
from pathlib import Path


def write_runtime_extractor_config(
    output_dir: Path,
    *,
    base_config_path: Path | None,
    local_base_url: str,
    local_model: str,
    local_api_key: str,
    local_timeout: float,
    extractor_max_blocks: int | None,
    extractor_max_tokens: int | None,
    extractor_batch_mode: str,
    extractor_batch_max_chars: int | None,
    extractor_preselect_max_blocks: int | None,
    extractor_preselect_min_score: float | None,
    extractor_disable_preselect: bool,
    extractor_adaptive_max_blocks: bool,
    extractor_adaptive_min_blocks: int | None,
    extractor_adaptive_max_blocks_limit: int | None,
) -> Path:
    config = {"providers": {}}
    if base_config_path is not None and Path(base_config_path).is_file():
        config = json.loads(Path(base_config_path).read_text(encoding="utf-8"))
    providers = config.setdefault("providers", {})
    local_config = dict(providers.get("local_llm", {})) if isinstance(providers.get("local_llm", {}), dict) else {}
    local_config.update(
        {
            "base_url": local_base_url,
            "model": local_model,
            "api_key": local_api_key,
            "timeout": local_timeout,
        }
    )
    if extractor_max_blocks is not None:
        local_config["max_blocks"] = extractor_max_blocks
    if extractor_max_tokens is not None:
        local_config["max_tokens"] = extractor_max_tokens
    if extractor_batch_mode:
        local_config["batch_mode"] = extractor_batch_mode
    if extractor_batch_max_chars is not None:
        local_config["batch_max_chars"] = extractor_batch_max_chars
    if extractor_disable_preselect:
        local_config["preselect_enabled"] = False
    if extractor_preselect_max_blocks is not None:
        local_config["preselect_max_blocks"] = extractor_preselect_max_blocks
    if extractor_preselect_min_score is not None:
        local_config["preselect_min_score"] = extractor_preselect_min_score
    local_config["adaptive_max_blocks_enabled"] = bool(extractor_adaptive_max_blocks)
    if extractor_adaptive_max_blocks:
        if extractor_adaptive_min_blocks is not None:
            local_config["adaptive_min_blocks"] = extractor_adaptive_min_blocks
        if extractor_adaptive_max_blocks_limit is not None:
            local_config["adaptive_max_blocks"] = extractor_adaptive_max_blocks_limit
    providers["local_llm"] = local_config
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "runtime_model_extractors.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_env_file(path: Path) -> None:
    if not path or not Path(path).is_file():
        return
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :]
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default
