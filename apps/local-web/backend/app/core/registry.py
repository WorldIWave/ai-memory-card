# Input: Provider 类名及实现类（scheduler/ai_provider/importer）  |  Output: Provider 实例
# Role: 可插拔 Provider 的注册与检索中心，实现运行时策略切换
# Note: 全局单例 _registry 在 main.py lifespan 中初始化，之后只读；非线程安全写入
# Usage: get_registry().get_scheduler("sm2_basic") 获取调度器实例
"""
registry.py - Provider 注册中心

职责: 管理 scheduler、ai、importer 三类可插拔 Provider 的注册与获取
输入: Provider 类和名称
输出: Provider 实例
位置: Core层
关联: main.py, api/dependencies.py, providers/
"""
from __future__ import annotations

from app.providers.scheduler.base import SchedulerProvider
from app.providers.ai.base import AIProvider


class ProviderRegistry:
    def __init__(self):
        self._schedulers: dict[str, type] = {}
        self._ai_providers: dict[str, type] = {}
        self._importers: dict[str, type] = {}

    def register_scheduler(self, name: str, provider_cls: type) -> None:
        self._schedulers[name] = provider_cls

    def get_scheduler(self, name: str) -> SchedulerProvider:
        return self._schedulers[name]()

    def register_ai_provider(self, name: str, provider_cls: type) -> None:
        self._ai_providers[name] = provider_cls

    def get_ai_provider(self, name: str, **kwargs) -> AIProvider:
        return self._ai_providers[name](**kwargs)

    def register_importer(self, name: str, provider_cls: type) -> None:
        self._importers[name] = provider_cls

    def get_importer(self, name: str):
        return self._importers[name]()


_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    return _registry
