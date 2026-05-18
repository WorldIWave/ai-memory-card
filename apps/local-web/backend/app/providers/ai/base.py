# Input: 无（仅定义接口）  |  Output: AIProvider Protocol 类型供类型检查使用
# Role: AI 提供商抽象层，隔离解释评估、RAG 卡片生成等上层业务与具体 AI 实现
# Note: 使用 runtime_checkable，可用 isinstance() 做运行时类型校验；生成能力可由远端 provider 实现
# Usage: 其他 AI 实现类（noop/remote_http）隐式满足此 Protocol，无需显式继承
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AIProvider(Protocol):
    def get_name(self) -> str:
        ...

    def evaluate_explanation(
        self,
        *,
        target_unit: dict[str, object],
        learner_explanation: str,
        reference_material: str | None = None,
    ) -> dict[str, object]:
        ...

    def generate_rag_cards(
        self,
        *,
        deck: dict[str, object],
        documents: list[dict[str, object]],
        topics: list[str] | None = None,
        generation_prefs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...
