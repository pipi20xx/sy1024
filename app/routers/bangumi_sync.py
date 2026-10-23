from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
from .. import globals
from app.logger import log_audit

router = APIRouter(prefix="/api/bangumi-sync", tags=["Bangumi 同步器"])

class SyncConfigPayload(BaseModel):
    allowed_tags: Optional[List[str]] = None
    access_token: Optional[str] = None

async def format_sse(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"

@router.get("/config", summary="获取同步配置")
async def get_config():
    """获取同步配置（允许的标签和 token）。"""
    if not globals.bangumi_service:
        raise HTTPException(status_code=503, detail="Bangumi 服务未初始化")
    
    config = await globals.bangumi_service.get_scheduler_config()
    sync_config = config.get("sync_config", {})
    
    return {
        "allowed_tags": sync_config.get("allowed_tags", []),
        "access_token": sync_config.get("access_token", "")
    }

@router.post("/config", summary="更新同步配置")
async def update_config(payload: SyncConfigPayload):
    """更新同步配置。"""
    if not globals.bangumi_service:
        raise HTTPException(status_code=503, detail="Bangumi 服务未初始化")
    
    current_config = await globals.bangumi_service.get_scheduler_config()
    current_sync_config = current_config.get("sync_config", {})
    
    if payload.allowed_tags is not None:
        current_sync_config["allowed_tags"] = payload.allowed_tags
        
    if payload.access_token is not None:
        current_sync_config["access_token"] = payload.access_token
    
    globals.bangumi_service.update_scheduler_config({"sync_config": current_sync_config})
    log_audit("Bangumi同步", "更新配置", f"标签: {payload.allowed_tags}, Token: {'***' if payload.access_token else '未设置'}")
    return {"status": "success"}

@router.post("/run", summary="执行同步过程")
async def run_sync(request: Request):
    """
    运行同步过程（通过 SSE 返回进度）。
    """
    if not globals.emby_tag_writer_service:
        raise HTTPException(status_code=503, detail="写入服务未初始化")
    
    try:
        options = await request.json()
    except Exception:
        options = {}

    log_audit("Bangumi同步", "执行", "开始同步到 Emby", level="START")

    async def event_generator():
        try:
            async for event in globals.emby_tag_writer_service.sync_to_emby(options):
                yield event
        except Exception as e:
            log_audit("Bangumi同步", "同步异常", str(e), level="ERROR")
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
