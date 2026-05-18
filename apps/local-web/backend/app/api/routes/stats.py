# Input: /stats 的时间范围查询参数与数据库 Session  |  Output: StatsSummaryRead / StatsAnalyticsRead
# Output: 向数据页提供摘要卡片、趋势、评分分布和牌组活跃度 API
# Role: 这是 analytics service 的 HTTP 暴露层，保持统计逻辑不泄漏到路由
# Use: 所有新分析接口优先复用 AnalyticsService，避免在这里直接写聚合 SQL
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.dependencies import get_analytics_service
from app.db.session import get_session
from app.schemas.stats import StatsAnalyticsRead, StatsSummaryRead
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummaryRead)
def get_summary(
    session: Session = Depends(get_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> StatsSummaryRead:
    return service.get_summary(session)


@router.get("/analytics", response_model=StatsAnalyticsRead)
def get_analytics(
    range_days: str = Query("7"),
    session: Session = Depends(get_session),
    service: AnalyticsService = Depends(get_analytics_service),
) -> StatsAnalyticsRead:
    return service.get_analytics(session, range_days=range_days)
