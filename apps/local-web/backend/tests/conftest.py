# Input: pytest 启动时自动加载  |  Output: session / memory_client / reset_app_database fixtures
# Role: 全局测试基础设施，提供内存 SQLite 引擎和 TestClient，并在每个测试前后清理磁盘 DB
# Note: reset_app_database 为 autouse，所有测试均受其隔离；memory_client 覆盖 get_session 依赖
# Usage: 在测试函数参数中声明 session 或 memory_client 即可自动注入
from collections.abc import Generator
from pathlib import Path
import gc
import sys
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
backend_root_str = str(BACKEND_ROOT)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)

import app.db.models  # noqa: F401  # ensure SQLModel metadata is populated explicitly


def _default_app_db_path() -> Path | None:
    from app.core.config import get_settings

    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or url.database in (None, ":memory:"):
        return None

    db_path = Path(url.database)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return db_path


def _cleanup_db_path(db_path: Path | None, *, attempts: int = 40, delay_seconds: float = 0.1) -> None:
    from app.db.session import get_engine

    if db_path is None:
        return

    last_error: PermissionError | None = None
    for attempt in range(attempts):
        get_engine().dispose()
        gc.collect()
        if not db_path.exists():
            return

        try:
            db_path.unlink()
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)

    if last_error is not None:
        raise last_error


@pytest.fixture(autouse=True)
def reset_app_database() -> Generator[None, None, None]:
    db_path = _default_app_db_path()
    _cleanup_db_path(db_path)
    yield
    _cleanup_db_path(db_path)


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture()
def memory_client() -> Generator[TestClient, None, None]:
    """内存数据库 TestClient，所有集成测试统一使用"""
    from app.db.session import get_session
    from app.main import app

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as db:
            yield db

    def collect_session_dependencies(dependant) -> set:
        dependencies = set()
        for dependency in getattr(dependant, "dependencies", []):
            call = getattr(dependency, "call", None)
            if getattr(call, "__module__", None) == "app.db.session" and getattr(call, "__name__", None) == "get_session":
                dependencies.add(call)
            dependencies.update(collect_session_dependencies(dependency))
        return dependencies

    override_keys = {get_session}
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            override_keys.update(collect_session_dependencies(dependant))

    previous_overrides = {key: app.dependency_overrides.get(key) for key in override_keys}
    for key in override_keys:
        app.dependency_overrides[key] = override_get_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for key, previous_override in previous_overrides.items():
            if previous_override is None:
                app.dependency_overrides.pop(key, None)
            else:
                app.dependency_overrides[key] = previous_override
        engine.dispose()
