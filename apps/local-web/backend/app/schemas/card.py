# Input: 前端创建/编辑卡片时的 payload 与 ORM Card 实例  |  Output: CardCreate/CardUpdate/CardRead DTO
# Output: 统一 cards 路由的请求校验与响应序列化格式
# Role: 这是卡片 CRUD 在 API 层和 service 层之间共享的数据契约
# Use: 改卡片字段时先同步这里、db model、前端 types 和表单组件
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CardCreate(BaseModel):
    deck_id: int
    card_type: str
    front: str
    back: str
    render_format: str = "markdown"
    tags: list[str] = Field(default_factory=list)


class CardUpdate(BaseModel):
    deck_id: int
    card_type: str
    front: str
    back: str
    render_format: str = "markdown"
    tags: list[str] = Field(default_factory=list)


class CardRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deck_id: int
    knowledge_unit_ref_id: int | None = None
    card_type: str
    front: str
    back: str
    render_format: str
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    content_version: int
