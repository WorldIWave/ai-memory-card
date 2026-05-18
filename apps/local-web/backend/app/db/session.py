# Input: core/config.py 中的 database_url  |  Output: Engine 单例、Session 生成器
# Role: DB 层连接管理，隔离 SQLAlchemy 引擎创建细节，统一提供 Session 依赖
# Note: engine 由 lru_cache 保证单例；SQLite 需 check_same_thread=False 才能跨线程使用
# Usage: FastAPI 路由通过 Depends(get_session) 注入；直接使用时 with Session(get_engine()) as s
"""
session.py - 数据库会话管理

职责: 提供 SQLAlchemy engine 工厂和 FastAPI session 依赖
输入: 应用配置中的 database_url
输出: Engine 实例、Session 生成器
位置: DB层
关联: core/config.py, api/routes/*.py
"""
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        connect_args={"check_same_thread": False},
    )


def __getattr__(name: str):
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_session():
    with Session(get_engine()) as session:
        yield session
