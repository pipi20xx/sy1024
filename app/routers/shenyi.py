from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.services.shenyi_config import ShenYiConfigService
from app import globals
from app.logger import log_audit

router = APIRouter(prefix="/api/shenyi", tags=["神医配置"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ConfigSaveRequest(BaseModel):
    config_data: Dict[str, Any]
    session_token: str


@router.post("/login", summary="Emby账号登录")
async def login(request: LoginRequest):
    try:
        emby_client = None
        if globals.service and hasattr(globals.service, 'emby_integration_service'):
            emby_client = globals.service.emby_integration_service.emby_client
        
        if not emby_client:
            raise HTTPException(status_code=400, detail="Emby客户端未配置，请在系统设置中配置Emby服务器")
        
        service = ShenYiConfigService(emby_client)
        result = await service.login(request.username, request.password)
        
        log_audit("神医", "登录", f"用户: {request.username}", level="SUCCESS")
        return {
            "success": True,
            "data": result,
            "message": "登录成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        log_audit("神医", "登录失败", f"用户: {request.username}, 错误: {str(e)}", level="ERROR")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config", summary="获取神医配置")
async def get_config(session_token: str, page_id: str = '63c322:Settings'):
    try:
        emby_client = None
        if globals.service and hasattr(globals.service, 'emby_integration_service'):
            emby_client = globals.service.emby_integration_service.emby_client
        
        if not emby_client:
            raise HTTPException(status_code=400, detail="Emby客户端未配置，请在系统设置中配置Emby服务器")
        
        if not session_token:
            raise HTTPException(status_code=400, detail="请提供会话令牌")
        
        service = ShenYiConfigService(emby_client)
        result = await service.get_shenyi_config(page_id, session_token)
        
        return {
            "success": True,
            "data": result,
            "message": "获取配置成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        log_audit("神医", "获取配置失败", f"错误: {str(e)}", level="ERROR")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/config", summary="保存神医配置")
async def save_config(request: ConfigSaveRequest):
    try:
        emby_client = None
        if globals.service and hasattr(globals.service, 'emby_integration_service'):
            emby_client = globals.service.emby_integration_service.emby_client
        
        if not emby_client:
            raise HTTPException(status_code=400, detail="Emby客户端未配置，请在系统设置中配置Emby服务器")
        
        if not request.session_token:
            raise HTTPException(status_code=400, detail="请提供会话令牌")
        
        service = ShenYiConfigService(emby_client)
        result = await service.save_shenyi_config(request.config_data, request.session_token)
        
        log_audit("神医", "保存配置", "配置已保存", level="SUCCESS")
        return {
            "success": True,
            "data": result,
            "message": "保存配置成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        log_audit("神医", "保存配置失败", f"错误: {str(e)}", level="ERROR")
        raise HTTPException(status_code=400, detail=str(e))
