# Input: /settings 下的学习设置读写与 AI provider 测试请求  |  Output: StudySettingsRead 与 provider 测试结果
# Output: 暴露全局学习设置和外部 AI provider 连通性检查的 HTTP 接口
# Role: 这是设置页和后端配置/评估能力之间的路由边界
# Use: provider 测试不会持久化配置；学习设置变更要和 StudySettingsService 保持一致
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.api.dependencies import get_study_settings_service
from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.evaluation import EvaluationRequest
from app.schemas.study_settings import StudySettingsRead, StudySettingsUpdate
from app.services.evaluation_service import EvaluationService
from app.services.study_settings_service import StudySettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


class ProviderTestRequest(BaseModel):
    base_url: str | None = None


@router.get("")
def get_settings_view() -> dict[str, str | None]:
    settings = get_settings()
    return {
        "app_name": settings.app_name,
        "ai_provider": "remote_http" if settings.ai_provider_base_url else "none",
        "ai_provider_base_url": settings.ai_provider_base_url,
    }


@router.get("/study", response_model=StudySettingsRead)
def get_study_settings(
    session: Session = Depends(get_session),
    service: StudySettingsService = Depends(get_study_settings_service),
) -> StudySettingsRead:
    return StudySettingsRead.model_validate(service.get(session))


@router.put("/study", response_model=StudySettingsRead)
def update_study_settings(
    payload: StudySettingsUpdate,
    session: Session = Depends(get_session),
    service: StudySettingsService = Depends(get_study_settings_service),
) -> StudySettingsRead:
    return StudySettingsRead.model_validate(service.update(session, payload))


@router.post("/test-ai-provider")
def test_ai_provider(payload: ProviderTestRequest) -> dict[str, object]:
    if not payload.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url is required to test a remote AI provider",
        )

    service = EvaluationService(payload.base_url)
    try:
        result = service.evaluate(
            EvaluationRequest(
                target_unit={"topic": "test"},
                learner_explanation="test",
            )
        )
    finally:
        service.close()

    return {
        "ok": True,
        "ai_provider": service.provider.get_name(),
        "result": result,
    }
