# Input: 原始文本 payload 及可选 deck 名称  |  Output: ImportBundle（deck + cards）
# Role: 定义所有数据导入器必须满足的 Protocol 接口，实现可插拔导入架构
# Note: 使用 runtime_checkable，csv/json/markdown 实现类无需显式继承此接口
# Usage: core/registry.py 按格式选择对应 importer，统一通过 parse() 调用
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.providers.importer.json_importer import ImportBundle


@runtime_checkable
class ImporterProvider(Protocol):
    def get_name(self) -> str: ...
    def parse(self, payload: str, deck_name: str | None = None) -> ImportBundle: ...
