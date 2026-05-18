# Input: core/registry.py 中注册的 Provider  |  Output: 各 Service 实例（供 Depends 注入）
# Role: API 层与 Service 层的桥梁，集中管理所有依赖的构造逻辑
# Note: 每次请求都会新建 Service 实例；AI/RAG 服务按环境变量选择远端 provider
# Usage: 路由函数参数中声明 svc: DeckService = Depends(get_deck_service)
"""
dependencies.py - FastAPI 依赖注入

职责: 提供所有 Service 的工厂函数，通过 FastAPI Depends 注入到 Route 层
输入: 无
输出: Service 实例
位置: API层
关联: api/routes/*.py, services/*.py, core/registry.py
"""
from __future__ import annotations

from app.core.registry import get_registry
from app.providers.scheduler.basic import BasicSchedulerProvider, BasicSessionScheduler
from app.services.analytics_service import AnalyticsService
from app.services.activity_service import ActivityService
from app.services.ai_plugin_host_service import AIPluginHostService
from app.services.card_service import CardService
from app.services.deck_service import DeckService
from app.services.evaluation_service import EvaluationService
from app.services.export_service import ExportService
from app.services.import_service import ImportService
from app.services.knowledge_unit_service import KnowledgeUnitService
from app.services.rag_import_service import RAGImportService
from app.services.review_service import ReviewService
from app.services.study_settings_service import StudySettingsService
from app.services.trash_service import TrashService
from app.services.backup_service import BackupService
from app.services.diagnostics_service import DiagnosticsService


def get_deck_service() -> DeckService:
    return DeckService()


def get_card_service() -> CardService:
    return CardService()


def get_review_service() -> ReviewService:
    registry = get_registry()
    try:
        scheduler = registry.get_scheduler("sm2_basic")
    except KeyError:
        scheduler = BasicSchedulerProvider()
    try:
        session_scheduler = registry.get_scheduler("sm2_basic_v3")
    except KeyError:
        session_scheduler = BasicSessionScheduler()
    return ReviewService(
        scheduler=scheduler,
        session_scheduler=session_scheduler,
        study_settings_service=get_study_settings_service(),
        ai_plugin_host_service=get_ai_plugin_host_service(),
    )


def get_import_service() -> ImportService:
    return ImportService()


def get_ai_plugin_host_service() -> AIPluginHostService:
    return AIPluginHostService.from_settings()


def get_rag_import_service() -> RAGImportService:
    return RAGImportService(plugin_host_service=get_ai_plugin_host_service())


def get_knowledge_unit_service() -> KnowledgeUnitService:
    return KnowledgeUnitService()


def get_export_service() -> ExportService:
    return ExportService()


def get_evaluation_service() -> EvaluationService:
    return EvaluationService()


def get_trash_service() -> TrashService:
    return TrashService()


def get_backup_service() -> BackupService:
    return BackupService()


def get_diagnostics_service() -> DiagnosticsService:
    return DiagnosticsService()


def get_activity_service() -> ActivityService:
    return ActivityService()


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


def get_study_settings_service() -> StudySettingsService:
    return StudySettingsService()
