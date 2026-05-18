# Input: 导入格式、原始文本内容及可选目标牌组名  |  Output: 导入请求/响应 Schema
# Role: 定义卡片导入 API 的请求与响应数据结构，供 imports 路由验证与序列化
# Note: deck_name 为空时由 importer 自动推断牌组名；响应含完整 DeckRead 与卡片列表
# Usage: 路由层用 ImportCardsRequest 解析请求体，返回值用 ImportCardsResponse 包装
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.card import CardRead
from app.schemas.deck import DeckRead


class ImportCardsRequest(BaseModel):
    format: Literal["json", "csv", "markdown"]
    payload: str
    deck_name: str | None = None


class ImportCardsResponse(BaseModel):
    deck: DeckRead
    cards: list[CardRead] = Field(default_factory=list)
    imported_count: int
