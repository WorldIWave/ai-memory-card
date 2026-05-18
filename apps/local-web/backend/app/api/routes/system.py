# Input: 无（查询）或 RestoreBackupRequest（filename 字段）（恢复）
# Output: 备份元数据、备份列表、诊断快照、运行时信息或纯文本日志文件
# Role: 系统运维路由层，提供备份/恢复、诊断快照和日志导出功能
# Note: 恢复操作会覆盖当前数据库，需谨慎调用；日志以附件形式下载
# Usage: 由 app/main.py 以 /system 前缀挂载，供桌面端设置页或运维使用
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.api.dependencies import get_backup_service, get_diagnostics_service
from app.services.backup_service import BackupService
from app.services.diagnostics_service import DiagnosticsService

router = APIRouter(prefix="/system", tags=["system"])


class RestoreBackupRequest(BaseModel):
    filename: str


@router.post("/backup", status_code=status.HTTP_201_CREATED)
def create_backup(service: BackupService = Depends(get_backup_service)) -> dict[str, Any]:
    return service.create_backup()


@router.post("/restore")
def restore_backup(payload: RestoreBackupRequest, service: BackupService = Depends(get_backup_service)) -> dict[str, str]:
    return service.restore_backup(payload.filename)


@router.get("/backups")
def list_backups(service: BackupService = Depends(get_backup_service)) -> list[dict[str, Any]]:
    return service.list_backups()


@router.get("/diagnostics")
def diagnostics(service: DiagnosticsService = Depends(get_diagnostics_service)) -> dict[str, Any]:
    return service.diagnostics_snapshot()


@router.get("/logs/export", response_class=PlainTextResponse)
def export_logs(service: DiagnosticsService = Depends(get_diagnostics_service)) -> PlainTextResponse:
    return PlainTextResponse(service.export_logs(), headers={"Content-Disposition": 'attachment; filename="ai-memory-card-logs.txt"'})


@router.get("/runtime")
def runtime_info(service: DiagnosticsService = Depends(get_diagnostics_service)) -> dict[str, Any]:
    return service.runtime_snapshot()
