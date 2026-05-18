# Input: 无（无请求体，无查询参数）
# Output: {"status": "ok"} 固定 JSON 响应
# Role: 健康检查路由，供负载均衡器、桌面端 runtime 探活确认后端进程存活
# Usage: 由 app/main.py 直接挂载（无前缀），GET /health 即可调用
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
