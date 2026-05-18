# Input: Service 层抛出的 AppError 子类（NotFoundError/ConflictError/ValidationError）
# Output: 带 detail 和 code 字段的 JSONResponse（404/409/400）
# Role: 异常处理中间层，将领域异常统一转换为规范 HTTP 响应，避免 500 泄漏
# Usage: 在 main.py 的 create_app() 中调用 register_error_handlers(app) 完成注册
"""
error_handlers.py - 异常到 HTTP 响应映射

职责: 将 Service 层抛出的业务异常映射为标准 HTTP 响应
输入: AppError 子类异常
输出: JSONResponse
位置: API层
关联: core/errors.py, main.py
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import ConflictError, NotFoundError, ValidationError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": exc.message, "code": exc.code})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": exc.message, "code": exc.code})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError):
        return JSONResponse(status_code=400, content={"detail": exc.message, "code": exc.code})
