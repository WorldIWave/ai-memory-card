# Input: 导出格式枚举（json/csv/markdown）及导出内容  |  Output: 导出响应 Schema
# Role: 定义卡片导出 API 的响应数据结构，供 exports 路由序列化返回值
# Note: payload 可为 dict（JSON 格式）或 str（CSV/Markdown 文本），类型联合
# Usage: 在导出路由中实例化 ExportCardsResponse 并作为响应体返回
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExportCardsResponse(BaseModel):
    format: Literal["json", "csv", "markdown"]
    payload: dict[str, object] | str
