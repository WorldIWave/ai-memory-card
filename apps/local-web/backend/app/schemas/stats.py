# Input: analytics service 聚合出的趋势、分布、摘要结果  |  Output: 数据页使用的 summary/trend/distribution/deck-activity DTO
# Output: 统一 /stats/summary 与 /stats/analytics 的响应结构
# Role: 这是数据分析页与后端统计服务之间的稳定契约层
# Use: 新增图表维度时优先在这里加类型，再同步 analytics service 和前端 data page
from __future__ import annotations

from pydantic import BaseModel


class StatsSummaryRead(BaseModel):
    total_cards: int
    today_reviewed: int
    daily_new_avg: float
    daily_review_avg: float


class StatsTrendPointRead(BaseModel):
    date: str
    review_count: int


class StatsTrendRead(BaseModel):
    range_days: int
    points: list[StatsTrendPointRead]


class GradeDistributionItemRead(BaseModel):
    grade: str
    count: int
    ratio: float


class GradeDistributionRead(BaseModel):
    total_reviews: int
    items: list[GradeDistributionItemRead]


class DeckActivityItemRead(BaseModel):
    deck_id: int
    deck_name: str
    review_count: int
    unique_cards: int


class DeckActivityRead(BaseModel):
    range_days: int
    items: list[DeckActivityItemRead]


class StatsAnalyticsRead(BaseModel):
    summary: StatsSummaryRead
    trend: StatsTrendRead
    grade_distribution: GradeDistributionRead
    deck_activity: DeckActivityRead
