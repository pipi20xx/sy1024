from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Response
from fastapi.responses import FileResponse
import os
import json
import asyncio
from typing import Optional, List
from .. import globals
from app.logger import logger, log_audit
from ..emby_collection_service import EmbyCollectionService
from ..backup_service import BackupService
from ..services.preview_generator import preview_service
from ..services.scheduler_service import scheduler_service
from pydantic import BaseModel
from app.services.shenyi_config import ShenYiConfigService


class EmbyLoginRequest(BaseModel):
    username: str
    password: str

# --- [已迁移至 scheduler_service] ---

def start_scheduler():
    scheduler_service.start()

# --- 调度器逻辑结束 ---

router = APIRouter(tags=["系统管理"])


@router.get("/api/browse_path", summary="浏览文件路径")
async def browse_path(request: Request):
    """浏览服务器文件系统路径，返回子目录列表。"""
    path_param = request.query_params.get('path', '/')
    if not os.path.isabs(path_param):
        raise HTTPException(status_code=400, detail="只支持绝对路径。")
    try:
        if not os.path.isdir(path_param):
             return []
        items = []
        for item in os.listdir(path_param):
            item_path = os.path.join(path_param, item)
            if os.path.isdir(item_path):
                items.append({"name": item, "type": "directory", "path": item_path})
        return sorted(items, key=lambda x: x['name'].lower())
    except OSError as e:
        log_audit("系统", "失败", f"浏览路径失败: {path_param}, 错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=f"无法读取路径: {e}")

@router.get("/api/settings/all", summary="获取所有设置")
async def get_all_settings():
    """获取应用的所有配置项信息。"""
    settings = globals.service.configuration_service.get_config().copy()
    settings.pop("data_path", None)
    return settings

@router.post("/api/settings/all", summary="保存所有设置")
async def save_all_settings(request: Request):
    """保存应用配置并重启相关后台服务。"""
    try:
        new_settings = await request.json()
        success, message = globals.service.configuration_service.update_config(new_settings)
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        # 重新加载服务和任务
        log_audit("系统", "配置变更", "正在重新加载服务和后台任务", level="START")
        
        # Reload internal services (EmbyClient, WebImageService)
        globals.service.reload_services()
        
        # Reload LLMService if initialized
        if hasattr(globals, "llm_service") and globals.llm_service:
            await globals.llm_service.reload_client()
        
        # Reload external services (Collection, Backup) which depend on config/system
        current_config = globals.service.configuration_service.get_config()
        globals.collection_service = EmbyCollectionService(current_config.get("emby_collections_path"), system_service=globals.service)
        globals.service.collection_service = globals.collection_service
        globals.backup_service = BackupService(current_config)
        
        # 重启调度器
        start_scheduler()
        
        log_audit("系统", "配置更新", "服务和后台任务已重启", level="DONE")
        return {"message": "设置已成功保存！后台服务将根据新设置重启。"}
    except Exception as e:
        log_audit("系统", "配置保存失败", str(e), level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/scan", summary="开始全量扫描")
async def trigger_scan(background_tasks: BackgroundTasks):
    """触发全量数据扫描任务。"""
    scan_progress = globals.service.scanner_service.get_scan_progress()
    if scan_progress["status"] == "scanning":
        raise HTTPException(status_code=400, detail="扫描已在进行中。")
    background_tasks.add_task(globals.service.scanner_service.scan_all_data)
    return {"message": "扫描已开始，请使用 /api/scan/status 查询进度。"}

@router.get("/api/scan/status", summary="获取扫描状态")
async def get_scan_status():
    """查询当前扫描任务的进度和状态。"""
    return globals.service.scanner_service.get_scan_progress()

@router.get("/api/config/status", summary="获取 Emby 配置状态")
async def get_config_status():
    """检查 Emby 服务器连接是否已配置。"""
    return globals.service.get_emby_config_status()

@router.get("/media-content/{item_type}/{item_id}/images/{image_name}", summary="获取缓存图片")
async def get_item_image(item_type: str, item_id: str, image_name: str):
    """从覆盖缓存中获取项目图片文件。"""
    override_path = globals.service.configuration_service.get_cache_path_for_source("override")
    if not override_path:
        raise HTTPException(status_code=404, detail="Override cache path not configured.")
    original_image_path = os.path.join(override_path, item_type, item_id, "images", image_name)
    if not os.path.isfile(original_image_path):
        raise HTTPException(status_code=404, detail="Image not found in override cache")
    return FileResponse(original_image_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@router.get("/api/system/file-watcher/status", summary="获取文件监控状态")
async def get_file_watcher_status():
    """获取实时文件监控的运行状态。"""
    if not globals.service:
        raise HTTPException(status_code=503, detail="System service not ready")
    return globals.service.file_watcher_service.get_status()

@router.get("/api/system/check-update", summary="检查系统更新")
async def check_update(force: bool = False):
    """检查 Docker Hub 是否有新版本。"""
    if not globals.service:
        raise HTTPException(status_code=503, detail="System service not ready")
    return await globals.service.get_latest_version(force=force)

@router.post("/api/system/emby-login", summary="Emby账号登录获取会话令牌")
async def emby_login(request: EmbyLoginRequest):
    """使用Emby账号密码登录获取会话令牌，用于神医配置等功能。"""
    try:
        emby_client = None
        if globals.service and hasattr(globals.service, 'emby_integration_service'):
            emby_client = globals.service.emby_integration_service.emby_client
        
        if not emby_client:
            raise HTTPException(status_code=400, detail="Emby客户端未配置，请先配置Emby服务器")
        
        service = ShenYiConfigService(emby_client)
        result = await service.login(request.username, request.password)
        
        return {
            "success": True,
            "data": result,
            "message": "登录成功"
        }
    except Exception as e:
        log_audit("Emby", "登录失败", str(e), level="ERROR")
        raise HTTPException(status_code=400, detail=str(e))

# --- [新增] 分级映射文件管理 ---
RATING_FILES_MAPPING = {
    "movies_us": ("tmdb-movies2", "us_content_rating_fallback.json"),
    "movies_jp": ("tmdb-movies2", "jp_content_rating_fallback.json"),
    "tv_us": ("tmdb-tv", "us_content_rating_fallback.json"),
    "tv_jp": ("tmdb-tv", "jp_content_rating_fallback.json"),
}

@router.get("/api/system/rating-files", summary="获取分级映射文件")
async def get_rating_files():
    """读取位于 override 目录下的内容分级映射配置文件。"""
    override_path = globals.service.configuration_service.get_cache_path_for_source("override")
    if not override_path:
        raise HTTPException(status_code=400, detail="未配置 override 缓存路径。")
    
    result = {}
    for key, (folder, filename) in RATING_FILES_MAPPING.items():
        file_path = os.path.join(override_path, folder, filename)
        content = "{}" # 默认空 JSON
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                log_audit("系统", "失败", f"读取分级文件 {file_path} 失败: {e}", level="ERROR")
                content = f"Error reading file: {e}"
        result[key] = content
    return result

@router.post("/api/system/rating-files", summary="保存分级映射文件")
async def save_rating_files(request: Request):
    """保存内容分级映射配置文件到 override 目录。"""
    data = await request.json()
    override_path = globals.service.configuration_service.get_cache_path_for_source("override")
    if not override_path:
        raise HTTPException(status_code=400, detail="未配置 override 缓存路径。")

    saved_files = []
    try:
        for key, content_str in data.items():
            if key not in RATING_FILES_MAPPING:
                continue
            
            # 验证 JSON 格式
            try:
                json.loads(content_str)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail=f"'{key}' 的内容不是有效的 JSON 格式。")

            folder, filename = RATING_FILES_MAPPING[key]
            full_dir = os.path.join(override_path, folder)
            file_path = os.path.join(full_dir, filename)

            os.makedirs(full_dir, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_str)
            saved_files.append(filename)
        
        return {"message": f"成功保存 {len(saved_files)} 个配置文件。", "files": saved_files}
    except HTTPException:
        raise
    except Exception as e:
        log_audit("系统", "保存分级文件失败", str(e), level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/system/test-emby", summary="测试 Emby 连接")
async def test_emby_connection(request: Request):
    """测试 Emby 服务器连接设置（不保存）。"""
    try:
        data = await request.json()
        server_url = data.get("emby_server_url")
        api_key = data.get("emby_api_key")
        user_id = data.get("emby_user_id", "")
        
        if not server_url or not api_key:
            return {"success": False, "message": "请提供 Emby 服务器地址和 API 密钥。"}
            
        from ..emby_client import EmbyClient
        
        # 确保 URL 格式正确 (rstrip /)
        server_url = server_url.rstrip('/')
        
        client = EmbyClient(server_url, api_key, user_id)
        
        # 1. 测试基础连通性 (无需 UserID)
        system_info, error = await client._make_request("GET", "/System/Info", exclude_user_id=True)
        if error:
            error_msg = f"无法连接到 Emby 服务器。\n诊断信息: {error}"
            if "ConnectError" in error or "ConnectTimeout" in error:
                error_msg += "\n\n提示: 请检查服务器地址是否正确，防火墙是否允许连接，以及 Docker 容器网络是否互通。如果是本地 Docker 环境，尝试使用宿主机真实 IP 而非 localhost。"
            elif "SSL" in error or "Cert" in error:
                error_msg += "\n\n提示: 看起来是 SSL 证书问题，请确保地址协议（http/https）正确。"
            elif "401" in error:
                error_msg += "\n\n提示: 401 Unauthorized，请检查 API 密钥是否正确且具有足够权限。"
            
            return {"success": False, "message": error_msg}
        
        server_version = system_info.get('Version', '未知')
        server_name = system_info.get('ServerName', 'Emby')

        # 2. 如果提供了 User ID，测试其有效性
        if user_id:
            user_info, user_error = await client._make_request("GET", f"/Users/{user_id}")
            if user_error:
                error_msg = f"服务器连接成功 ({server_name} v{server_version})，但 User ID 验证失败。\n诊断信息: {user_error}"
                if "404" in user_error:
                    error_msg += "\n\n提示: 找不到该 User ID。请在 Emby 后台 -> 用户 -> 点击进入用户 -> URL 中查看真正的 ID (不是用户名)。"
                return {"success": False, "message": error_msg}
            
            user_display_name = user_info.get('Name', user_id)
            return {
                "success": True, 
                "message": f"连接成功！\n服务器: {server_name} (v{server_version})\n验证用户: {user_display_name}"
            }
        
        return {
            "success": True, 
            "message": f"连接成功！\n服务器: {server_name} (v{server_version})\n(未验证用户 ID)"
        }
        
    except Exception as e:
        log_audit("Emby", "连接测试失败", str(e), level="ERROR")
        return {"success": False, "message": f"测试过程中发生内部错误: {str(e)}"}
    finally:
        if 'client' in locals():
            await client.close()

# --- [新增] 日志管理接口 ---
@router.get("/api/system/logs/dates", summary="获取所有日志日期")
async def get_log_dates():
    """获取所有已归档日志的日期列表"""
    from ..logger import get_log_dates as get_dates_impl
    return get_dates_impl()

@router.get("/api/system/logs", summary="获取日志文件列表")
async def list_logs():
    """获取 data/logs 目录下的所有日志文件列表。"""
    from ..logger import get_log_dates as get_dates_impl
    
    files = []
    # 始终包含当前的 monitor.log
    files.append({"name": "当前运行日志 (monitor)", "type": "monitor"})

    dates = get_dates_impl()
    for d in dates:
        files.append({
            "name": f"{d} 归档日志",
            "type": d
        })
    
    return files

@router.get("/api/system/logs/raw", summary="获取原始日志流")
async def get_raw_log(type: str = "monitor"):
    """
    通过快捷类型获取原始日志文本。
    支持: /api/system/logs/raw?type=monitor
    """
    from ..logger import get_log_content
    
    # get_log_content 内部已处理 'monitor' -> 今天日期
    # 并支持 reverse=True (倒序)
    content = get_log_content(type, reverse=True)
    
    if content == "Log file not found.":
        raise HTTPException(status_code=404, detail="日志文件不存在")
    if content.startswith("Error reading log"):
         raise HTTPException(status_code=500, detail=content)

    return Response(content=content, media_type="text/plain; charset=utf-8")
