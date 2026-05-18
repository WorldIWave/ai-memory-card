from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI

from .config import load_runtime_config
from .contracts import (
    PluginEvaluationTaskRequest,
    PluginSchedulerTaskRequest,
    PluginTaskError,
    PluginTaskRequest,
    PluginTaskResponse,
)
from .errors import map_runtime_exception
from .provider_adapters import build_provider_adapter
from .scheduler_core import plan_review

app = FastAPI(title="rag-core plugin", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    config = load_runtime_config()
    return {
        "status": "ok",
        "plugin_id": config.plugin_id,
        "plugin_version": config.plugin_version,
        "protocol_version": config.protocol_version,
        "configuration": {
            "provider_ready": bool(config.available_provider_profiles()),
            "provider_profile": config.default_provider_profile,
            "base_url": config.base_url,
            "api_key_configured": bool(config.api_key),
            "model": config.model or None,
            "last_error_code": config.last_error_code,
            "last_error_summary": config.last_error_summary,
        },
    }


@app.get("/capabilities")
def capabilities() -> dict[str, object]:
    config = load_runtime_config()
    provider_profiles = config.available_provider_profiles()
    return {
        "plugin_id": config.plugin_id,
        "plugin_version": config.plugin_version,
        "protocol_version": config.protocol_version,
        "capabilities": [
            {
                "name": "rag.generate_cards",
                "modes": [
                    {
                        "name": "api",
                        "available": bool(provider_profiles),
                        "provider_profiles": provider_profiles,
                    }
                ],
            },
            {
                "name": "evaluation.score_explanation",
                "modes": [
                    {
                        "name": "api",
                        "available": bool(provider_profiles),
                        "provider_profiles": provider_profiles,
                    }
                ],
            },
            {
                "name": "scheduler.plan_review",
                "modes": [
                    {
                        "name": "local",
                        "available": True,
                    }
                ],
            }
        ],
        "configuration": {
            "provider_ready": bool(provider_profiles),
            "provider_profile": config.default_provider_profile,
            "base_url": config.base_url,
            "api_key_configured": bool(config.api_key),
            "model": config.model or None,
            "last_error_code": config.last_error_code,
            "last_error_summary": config.last_error_summary,
        },
    }


def generate_cards_with_provider(payload: dict[str, object]) -> dict[str, object]:
    request = PluginTaskRequest.model_validate(payload)
    config = load_runtime_config()
    adapter = build_provider_adapter(config=config, provider_profile=request.provider_profile)
    try:
        return adapter.generate_rag_cards(request)
    finally:
        adapter.close()


def score_explanation_with_provider(payload: dict[str, object]) -> dict[str, object]:
    request = PluginEvaluationTaskRequest.model_validate(payload)
    config = load_runtime_config()
    adapter = build_provider_adapter(config=config, provider_profile=request.provider_profile)
    try:
        return adapter.score_explanation(request)
    finally:
        adapter.close()


@app.post("/provider/check")
def check_provider() -> dict[str, object]:
    config = load_runtime_config()
    adapter = build_provider_adapter(config=config, provider_profile=config.default_provider_profile)
    try:
        return adapter.probe_provider()
    except Exception as exc:
        mapped = map_runtime_exception(exc)
        return {
            "ok": False,
            "provider_name": "openai_compatible_local",
            "model": config.model or None,
            "error": {"code": mapped.code, "message": mapped.message},
        }
    finally:
        adapter.close()


@app.post("/tasks/rag.generate_cards", response_model=PluginTaskResponse)
def run_rag_generate_cards(payload: PluginTaskRequest) -> PluginTaskResponse:
    task_id = f"task-{uuid4().hex[:12]}"
    try:
        result = generate_cards_with_provider(payload.model_dump())
    except Exception as exc:
        mapped = map_runtime_exception(exc)
        return PluginTaskResponse(
            task_id=task_id,
            status="failed",
            result=None,
            error=PluginTaskError(code=mapped.code, message=mapped.message),
        )
    return PluginTaskResponse(task_id=task_id, status="succeeded", result=result, error=None)


@app.post("/tasks/evaluation.score_explanation", response_model=PluginTaskResponse)
def run_evaluation_score_explanation(payload: PluginEvaluationTaskRequest) -> PluginTaskResponse:
    task_id = f"task-{uuid4().hex[:12]}"
    try:
        result = score_explanation_with_provider(payload.model_dump())
    except Exception as exc:
        mapped = map_runtime_exception(exc)
        return PluginTaskResponse(
            task_id=task_id,
            status="failed",
            result=None,
            error=PluginTaskError(code=mapped.code, message=mapped.message),
        )
    return PluginTaskResponse(task_id=task_id, status="succeeded", result=result, error=None)


@app.post("/tasks/scheduler.plan_review", response_model=PluginTaskResponse)
def run_scheduler_plan_review(payload: PluginSchedulerTaskRequest) -> PluginTaskResponse:
    task_id = f"task-{uuid4().hex[:12]}"
    try:
        result = plan_review(payload.model_dump())
    except Exception as exc:
        mapped = map_runtime_exception(exc)
        return PluginTaskResponse(
            task_id=task_id,
            status="failed",
            result=None,
            error=PluginTaskError(code=mapped.code, message=mapped.message),
        )
    return PluginTaskResponse(task_id=task_id, status="succeeded", result=result, error=None)
