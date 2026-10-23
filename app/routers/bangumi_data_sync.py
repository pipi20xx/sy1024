from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
import logging
from .. import globals

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bangumi-data-sync", tags=["Bangumi-Data 同步"])


def _get_github_token() -> Optional[str]:
    """从系统设置中读取 GitHub Token"""
    try:
        if globals.service and globals.service.configuration_service:
            return globals.service.configuration_service.get_config().get("github_token")
    except Exception:
        pass
    return None


@router.get("/sync", summary="同步 bangumi-data 数据")
async def sync_bangumi_data(token: Optional[str] = None):
    if not globals.bangumi_data_sync_service:
        raise HTTPException(status_code=503, detail="Bangumi-Data 同步服务未初始化")
    
    # 优先使用前端传入的 token，否则从系统设置读取
    github_token = token or _get_github_token()
    
    return StreamingResponse(
        globals.bangumi_data_sync_service.sync_bangumi_data(github_token=github_token),
        media_type="text/event-stream"
    )


@router.get("/version", summary="获取最后同步版本")
async def get_sync_version():
    if not globals.bangumi_data_sync_service:
        raise HTTPException(status_code=503, detail="Bangumi-Data 同步服务未初始化")
    
    version = await globals.bangumi_data_sync_service.get_sync_version()
    return {"version": version}
