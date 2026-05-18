# Input: 业务逻辑中的错误信息字符串  |  Output: 可抛出的业务异常类
# Role: 统一异常层，将领域错误语义化，供 error_handlers 映射为 HTTP 状态码
# Note: 所有 Service 层只应抛出此文件定义的异常，禁止直接抛出 HTTPException
# Usage: raise NotFoundError("Deck", deck_id) 或 raise ConflictError("名称已存在")
"""
errors.py - 统一业务异常定义

职责: 定义所有业务层异常，供 Service 层抛出，Route 层通过 error_handlers 映射为 HTTP 响应
输入: 无
输出: 可抛出的业务异常类
位置: Core层
关联: api/error_handlers.py, services/*.py
"""
from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, code: str = "UNKNOWN"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: object = None):
        detail = f"{resource} not found" if identifier is None else f"{resource} {identifier} not found"
        super().__init__(detail, code="NOT_FOUND")


class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT")


class ValidationError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR")
