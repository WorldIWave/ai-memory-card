# Input: 各路由模块、Provider 实现类、alembic 迁移脚本  |  Output: FastAPI app 实例
# Role: 应用总入口，负责组装路由、中间件、错误处理器及 Provider 注册
# Note: lifespan 启动时自动执行 alembic 迁移，迁移失败会阻止服务启动
# Usage: uvicorn app.main:app 或由 Tauri sidecar 以子进程方式启动
"""
main.py - 应用入口

职责: 创建 FastAPI 应用，注册路由、错误处理器和 Provider，通过 lifespan 执行启动迁移
输入: 无
输出: FastAPI app 实例
位置: 应用入口
关联: api/routes/*.py, api/error_handlers.py, core/registry.py, db/session.py
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
import time

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.api.error_handlers import register_error_handlers
from app.api.routes.ai import router as ai_router
from app.api.routes.assets import router as assets_router
from app.api.routes.cards import router as cards_router
from app.api.routes.decks import router as decks_router
from app.api.routes.evaluations import router as evaluations_router
from app.api.routes.exports import router as exports_router
from app.api.routes.folders import router as folders_router
from app.api.routes.health import router as health_router
from app.api.routes.imports import router as imports_router
from app.api.routes.review import router as review_router
from app.api.routes.settings import router as settings_router
from app.api.routes.stats import router as stats_router
from app.api.routes.system import router as system_router
from app.api.routes.trash import router as trash_router
from app.core.config import get_settings
from app.core.logging_setup import configure_runtime_logging, shutdown_runtime_logging
from app.core.registry import get_registry
from app.core.runtime_paths import RuntimePaths
from app.db.session import get_engine
from app.providers.ai.noop import NoopAIProvider
from app.providers.ai.remote_http import RemoteHTTPAIProvider
from app.providers.importer.csv_importer import import_csv_cards
from app.providers.importer.json_importer import import_json_cards
from app.providers.importer.markdown_importer import import_markdown_cards
from app.providers.scheduler.basic import BasicSchedulerProvider
from app.services.onboarding_seed_service import (
    OnboardingSeedService,
    should_enable_onboarding_seed,
)

_STARTUP_MIGRATION_RETRY_DELAY_SECONDS = 0.1


def run_startup_migrations() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    alembic_ini = backend_root / "alembic.ini"
    database_url = get_settings().database_url

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)

    for attempt in range(2):
        try:
            command.upgrade(config, "head")
            return
        except Exception as exc:
            if attempt == 0 and _is_sqlite_already_exists_race(exc, database_url):
                time.sleep(_STARTUP_MIGRATION_RETRY_DELAY_SECONDS)
                continue
            raise


def _is_sqlite_already_exists_race(error: BaseException, database_url: str) -> bool:
    if make_url(database_url).get_backend_name() != "sqlite":
        return False
    for candidate in _iter_exception_chain(error):
        if isinstance(candidate, sqlite3.OperationalError) and "already exists" in str(candidate).lower():
            return True
    return False


def _iter_exception_chain(error: BaseException) -> list[BaseException]:
    stack = [error]
    seen: set[int] = set()
    ordered: list[BaseException] = []
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        ordered.append(current)
        for attr in ("orig", "__cause__", "__context__"):
            candidate = getattr(current, attr, None)
            if isinstance(candidate, BaseException):
                stack.append(candidate)
    return ordered


def register_default_providers() -> None:
    registry = get_registry()
    registry.register_scheduler("sm2_basic", BasicSchedulerProvider)
    registry.register_ai_provider("noop", NoopAIProvider)
    registry.register_ai_provider("remote_http", RemoteHTTPAIProvider)
    registry.register_importer("json", type("_J", (), {"get_name": lambda _: "json", "parse": staticmethod(lambda p, d=None: import_json_cards(p))}))
    registry.register_importer("csv", type("_C", (), {"get_name": lambda _: "csv", "parse": staticmethod(import_csv_cards)}))
    registry.register_importer("markdown", type("_M", (), {"get_name": lambda _: "markdown", "parse": staticmethod(import_markdown_cards)}))


def ensure_runtime_storage() -> None:
    try:
        RuntimePaths.from_settings(get_settings()).ensure_directories()
    except ValueError:
        return


def ensure_onboarding_seed() -> None:
    settings = get_settings()
    if not should_enable_onboarding_seed(settings):
        return

    with Session(get_engine()) as session:
        OnboardingSeedService().ensure(session)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_runtime_storage()
    configure_runtime_logging()
    try:
        run_startup_migrations()
        register_default_providers()
        ensure_onboarding_seed()
        yield
    finally:
        shutdown_runtime_logging()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    app.include_router(health_router, prefix="/api")
    app.include_router(decks_router, prefix="/api")
    app.include_router(cards_router, prefix="/api")
    app.include_router(trash_router, prefix="/api")
    app.include_router(system_router, prefix="/api")
    app.include_router(imports_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    app.include_router(assets_router, prefix="/api")
    app.include_router(exports_router, prefix="/api")
    app.include_router(review_router, prefix="/api")
    app.include_router(evaluations_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(folders_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
    return app


app = create_app()
