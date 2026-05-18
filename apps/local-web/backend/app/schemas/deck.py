# Input: 牌组创建/编辑 payload 与 ORM Deck 实例  |  Output: DeckCreate/DeckUpdate/DeckRead DTO
# Output: 统一 decks 路由和前端 library/review 读取的牌组数据结构
# Role: 这是牌组生命周期接口的 API 契约层
# Use: folder/visibility/description 字段有变动时，要和 service、前端列表筛选一起改
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeckCreate(BaseModel):
    name: str
    description: str = ""
    folder_id: int = 1


class DeckUpdate(BaseModel):
    name: str
    description: str = ""
    folder_id: int = 1


class DeckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    default_scheduler_type: str
    visibility: str
    folder_id: int | None
    created_at: datetime
    updated_at: datetime
