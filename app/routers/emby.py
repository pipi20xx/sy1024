from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from typing import Dict, Any
import json
import os
import asyncio
from .. import globals
from app.logger import logger, log_audit
from ..schemas import EmbyMetadataUpdateRequest

router = APIRouter(tags=["Emby 集成"])

# --- Emby Operations on Items ---

@router.post("/api/items/{item_type}/{item_id}/emby-refresh", summary="刷新 Emby 项目")
async def emby_refresh_item(item_type: str, item_id: str):
    """请求 Emby 服务器刷新指定项目的媒体信息。"""
    success, message = await globals.service.emby_integration_service.refresh_item_in_emby(item_type, item_id)
    if not success: raise HTTPException(status_code=400, detail=message)
    return {"message": message}

@router.post("/api/items/{item_type}/{item_id}/emby-download-images", summary="从 Emby 下载图片")
async def emby_download_images(item_type: str, item_id: str):
    """从 Emby 下载并同步指定项目的海报等图片。"""
    success, message = await globals.service.image_service.download_images_from_emby(item_type, item_id)
    if not success: raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}

@router.post("/api/items/{item_type}/{item_id}/emby-update-metadata", summary="更新 Emby 元数据")
async def emby_update_metadata(item_type: str, item_id: str, request: EmbyMetadataUpdateRequest):
    """根据本地 Override 数据更新 Emby 服务器上的项目元数据。"""
    if not globals.service.emby_client:
        raise HTTPException(status_code=400, detail="Emby客户端未配置")

    # 从本地缓存 JSON 读取标题，优先用标题搜索 Emby
    titles = await asyncio.to_thread(globals.service.emby_integration_service._get_titles_from_local_cache, item_type, item_id)
    found_items, error = await globals.service.emby_client.find_items_by_tmdb_id(item_id, item_type, titles=titles)
    if error:
        raise HTTPException(status_code=500, detail=f"查找Emby项目失败: {error}")
    if not found_items:
        raise HTTPException(status_code=404, detail=f"在Emby中找不到TMDB ID为 {item_id} 的项目")
    
    emby_item_id = found_items[0].get("Id")
    original_emby_item_type = found_items[0].get("Type") 

    if not emby_item_id or not original_emby_item_type:
        raise HTTPException(status_code=500, detail="无法从Emby获取有效的项目ID或类型")

    success, message = await globals.service.editor_service.update_metadata_from_emby(
        item_type=item_type,
        emby_item_id=emby_item_id,
        folder_tmdb_id=item_id,
        original_emby_item_type=original_emby_item_type,
        fields_to_update=request.fields_to_update,
        update_children=request.update_children
    )
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)}

@router.get("/api/items/{item_type}/{item_id}/emby-weblink", summary="获取 Emby 网页链接")
async def get_emby_weblink(item_type: str, item_id: str):
    """获取指定项目在 Emby 管理界面的跳转链接。"""
    success, data_or_msg = await globals.service.emby_integration_service.get_emby_web_url_info(item_type, item_id)
    if not success:
        log_audit("Emby", "查找", f"未找到 TMDB {item_id} ({item_type}) 的 Emby 链接: {data_or_msg}", level="WARN")
        raise HTTPException(status_code=404, detail=data_or_msg)
    log_audit("Emby", "查找", f"已获取 TMDB {item_id} ({item_type}) 的 Emby 链接")
    return JSONResponse(status_code=200, content=data_or_msg)

@router.post("/api/emby/specify-scrape", summary="指定 Emby 刮削 ID")
async def emby_specify_scrape(request: Request):
    """手动指定项目在 Emby 中的 TMDB 刮削 ID。"""
    params = await request.json()
    emby_item_id = params.get("emby_item_id")
    new_tmdb_id = params.get("new_tmdb_id")
    if not all([emby_item_id, new_tmdb_id]):
        raise HTTPException(status_code=400, detail="缺少必要的参数 (emby_item_id, new_tmdb_id)")
    success, message = await globals.service.emby_integration_service.specify_scrape_in_emby(emby_item_id, new_tmdb_id)
    if not success: 
        raise HTTPException(status_code=400, detail=message)
    return {"message": message}

# --- Emby Collections ---

@router.get("/api/emby-collections/apply-single/{filename}", summary="应用单个合集到 Emby")
async def apply_single_collection_stream(filename: str):
    """将指定的本地合集配置同步到 Emby 服务器（SSE 流）。"""
    async def event_stream():
        async for progress_update in globals.collection_service.apply_single_collection_to_emby(filename):
            yield f"data: {json.dumps(progress_update)}\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.get("/api/emby-collections/apply-all-to-emby", summary="应用所有合集到 Emby (同步)")
async def apply_all_collections_to_emby_stream():
    """将所有本地合集配置同步到 Emby 服务器（SSE 流）。"""
    async def event_stream():
        async for progress_update in globals.collection_service.apply_all_collections_to_emby():
            yield f"data: {json.dumps(progress_update)}\n\n"
            await asyncio.sleep(0.01)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/api/emby-collections/apply-all-to-emby-bg", summary="应用所有合集到 Emby (后台)")
async def apply_all_collections_to_emby_bg(background_tasks: BackgroundTasks):
    """
    在后台启动同步所有合集到 Emby 的任务。
    """
    background_tasks.add_task(globals.collection_service.apply_all_collections_to_emby_task)
    return {"message": "任务已在后台启动，请查看顶部进度条", "success": True}

@router.post("/api/emby-collections/import-all-from-emby", summary="从 Emby 导入所有合集")
async def import_all_collections_from_emby_bg(request: Request, background_tasks: BackgroundTasks):
    """
    从 Emby 服务器批量导入所有合集到本地。
    """
    # 改为POST并使用后台任务，立即返回让前端可以关闭弹窗
    overwrite_json = request.query_params.get('overwrite_json', 'false').lower() == 'true'
    overwrite_images = request.query_params.get('overwrite_images', 'false').lower() == 'true'
    
    # 尝试从body获取参数（兼容性）
    try:
        data = await request.json()
        overwrite_json = data.get('overwrite_json', overwrite_json)
        overwrite_images = data.get('overwrite_images', overwrite_images)
    except: pass

    background_tasks.add_task(
        globals.collection_service.import_all_collections_from_emby, 
        overwrite_json, 
        overwrite_images
    )
    return {"message": "批量导入任务已在后台启动，请查看顶部进度条", "success": True}

@router.get("/api/emby-collections", summary="获取所有合集")
async def get_all_emby_collections():
    """获取所有已保存的合集列表。"""
    return {"collections": await globals.collection_service.get_all_collections()}

@router.post("/api/emby-collections/scan", summary="扫描磁盘合集")
async def scan_emby_collections():
    """强制从磁盘扫描合集文件到数据库。"""
    try:
        await globals.collection_service.sync_db_from_disk()
        return {"message": "合集库扫描完成，缓存已刷新。", "success": True}
    except Exception as e:
        log_audit("Emby", "扫描失败", str(e), level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/emby-collections/{filename}", summary="获取合集详情")
async def get_emby_collection_details(filename: str):
    """获取特定合集文件的详细信息。"""
    details = await globals.collection_service.get_collection_details(filename)
    if details is None: raise HTTPException(status_code=404, detail=f"名为 '{filename}' 的合集文件未找到或无法读取")
    return details

@router.post("/api/emby-collections/import-from-emby", summary="从 Emby 导入单个合集")
async def import_collection_from_emby(request: Request):
    """从 Emby 服务器导入指定的单个合集。"""
    try:
        data = await request.json()
        collection_name = data.get("collection_name")
        if not collection_name: raise HTTPException(status_code=400, detail="必须提供 'collection_name'")
        success, message, new_data = await globals.collection_service.import_collection_from_emby(collection_name, data.get("overwrite_json", False), data.get("overwrite_images", False))
        if not success: raise HTTPException(status_code=409, detail=message)
        return {"message": message, "new_collection": new_data}
    except Exception as e:
        log_audit("Emby", "导入合集异常", str(e), level="ERROR")
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")

@router.get("/api/emby-collections/images/{image_filename}", summary="获取合集图片")
async def get_emby_collection_image(image_filename: str):
    """获取合集的海报或 Logo 图片文件。"""
    if not globals.collection_service.collections_path or ".." in image_filename or "/" in image_filename or "\\" in image_filename:
        raise HTTPException(status_code=400, detail="无效的文件名或路径未配置")
    image_path = os.path.join(globals.collection_service.collections_path, image_filename)
    if not os.path.isfile(image_path): raise HTTPException(status_code=404, detail="图片未找到")
    return FileResponse(image_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@router.post("/api/emby-collections", summary="创建合集")
async def create_emby_collection(collection_data: Dict[str, Any]):
    """创建一个新的合集配置。"""
    success, message, filename = await globals.collection_service.save_collection(collection_data)
    if not success: raise HTTPException(status_code=400, detail=message)
    return {"message": message, "filename": filename}

@router.put("/api/emby-collections/{original_filename}", summary="更新合集")
async def update_emby_collection(original_filename: str, collection_data: Dict[str, Any]):
    """更新已有的合集配置。"""
    success, message, filename = await globals.collection_service.save_collection(collection_data, original_filename=original_filename)
    if not success: raise HTTPException(status_code=400, detail=message)
    return {"message": message, "filename": filename}

@router.delete("/api/emby-collections/{filename}", summary="删除合集")
async def delete_emby_collection(filename: str):
    """删除特定的合集配置及其图片。"""
    success, message = await globals.collection_service.delete_collection(filename)
    if not success: raise HTTPException(status_code=400, detail=message)
    return {"message": message}

@router.post("/api/emby-collections/{filename}/images", summary="上传合集图片")
async def upload_emby_collection_image(filename: str, file: UploadFile = File(...), image_type: str = "poster"):
    """上传合集的海报、背景或 Logo 图片。"""
    # Manual validation to replace Query(regex=...)
    if image_type not in ["poster", "backdrop", "logo"]:
        raise HTTPException(status_code=422, detail="图片类型必须是: poster, backdrop, logo 之一")

    try:
        content = await file.read()
        success, message = await globals.collection_service.save_collection_image(filename, image_type, content)
        if not success:
            raise HTTPException(status_code=400, detail=message)
        return {"message": message, "success": True}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

# --- Config/ID ---

@router.get("/api/config/last-emby-id", summary="获取最后处理的 ID")
async def get_last_emby_id():
    """获取最后一次处理的 Emby 项目 ID。"""
    last_id = globals.service.configuration_service.get("last_emby_item_id", "")
    return {"emby_item_id": last_id}

@router.post("/api/config/last-emby-id", summary="保存最后处理的 ID")
async def save_last_emby_id(request: Request):
    """保存当前处理的 Emby 项目 ID 到配置。"""
    try:
        data = await request.json()
        emby_item_id = data.get("emby_item_id")
        if isinstance(emby_item_id, str):
            success, msg = globals.service.configuration_service.save_last_emby_item_id(emby_item_id)
            if success:
                return {"message": "ID 保存成功"}
            raise HTTPException(status_code=500, detail=msg)
        raise HTTPException(status_code=400, detail="无效的请求数据")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Webhook ---

@router.post("/api/webhook/emby/{token}", summary="接收 Emby Webhook")
async def receive_emby_webhook(token: str, request: Request, background_tasks: BackgroundTasks):
    """接收来自 Emby 服务器的 Webhook 实时通知。"""
    if not globals.service.configuration_service.get("emby_webhook_enabled", False):
        raise HTTPException(status_code=404, detail="设置中已禁用 Webhook 功能。")

    secret_token = globals.service.configuration_service.get("webhook_secret_token")
    if not secret_token or token != secret_token:
        log_audit("Emby", "Webhook拒绝", f"无效Token", level="WARN")
        raise HTTPException(status_code=403, detail="令牌无效或缺失。")
    
    try:
        payload = await request.json()
        event_type = payload.get("Event")
        
        # 处理查询存储信息事件（同步返回）
        if event_type == "query_storage":
            log_audit("Emby", "存储查询", "收到查询存储信息请求")
            
            if not globals.service.configuration_service.get("webhook_action_storage_query_enabled", True):
                log_audit("Emby", "存储查询", "功能已禁用", level="WARN")
                return {"error": "查询存储信息功能已禁用。"}
            
            item_data = payload.get("Item", {})
            
            # 直接从payload中获取TMDB ID
            provider_ids = item_data.get("ProviderIds", {})
            tmdb_id = str(provider_ids.get("Tmdb", ""))
            
            log_audit("Emby", "查询", f"[存储信息查询] TMDB ID: {tmdb_id}, 项目类型: {item_data.get('Type')}")
            if not tmdb_id:
                log_audit("Emby", "存储查询", "Item缺少TMDB ID", level="WARN")
                return {"error": "Item数据中缺少TMDB ID。"}
            
            # 根据Emby项目类型确定item_type（只处理Movie和Series，过滤掉Season）
            emby_item_type = item_data.get("Type", "")
            if emby_item_type == "Movie":
                item_type = "tmdb-movies2"
            elif emby_item_type == "Series":
                item_type = "tmdb-tv"
            else:
                log_audit("Emby", "存储查询", f"不支持的项目类型: {emby_item_type}", level="WARN")
                return {"error": f"不支持的Emby项目类型: {emby_item_type}（仅支持Movie和Series）"}
            
            # 使用TMDB ID查询存储信息
            log_audit("Emby", "开始", f"[存储信息查询] 开始查询, item_type: {item_type}, tmdb_id: {tmdb_id}")
            storage_info = await globals.service.editor_service.get_item_full_details(item_type, tmdb_id)
            
            if not storage_info:
                log_audit("Emby", "存储查询", f"未找到 TMDB ID: {tmdb_id}", level="WARN")
                return {"error": f"未找到TMDB ID为 {tmdb_id} 的项目存储信息"}
            
            log_audit("Emby", "完成", f"[存储信息查询] 成功获取, 项目: {storage_info.get('name', 'N/A')}")
            # 对于剧集类型，添加每季的集数统计信息
            if item_type == "tmdb-tv" and "seasons" in storage_info:
                log_audit("Emby", "查询", f"[存储信息查询] 剧集类型, 季度数: {len(storage_info['seasons'])}")
                for season in storage_info["seasons"]:
                    episodes = season.get("episodes", [])
                    total_episodes = len(episodes)
                    override_episodes = sum(1 for ep in episodes if ep.get("source") == "override")
                    season["episode_stats"] = {
                        "total": total_episodes,
                        "override": override_episodes,
                        "primary": total_episodes - override_episodes
                    }
                    log_audit("Emby", "查询", f"[存储信息查询] S{season.get('season_number')}: 总计={total_episodes}, Override={override_episodes}, 主缓存={total_episodes - override_episodes}", level="DEBUG")
            log_audit("Emby", "存储查询完成", f"TMDB ID: {tmdb_id}", level="SUCCESS")
            return storage_info
        
        # 其他事件，异步处理
        background_tasks.add_task(globals.webhook_service.handle_emby_webhook, payload)
        return {"status": "success", "message": "Webhook 已接收并加入处理队列。"}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的 JSON 负载。")
    except HTTPException:
        raise
    except Exception as e:
        log_audit("Emby", "Webhook异常", str(e), level="ERROR")
        raise HTTPException(status_code=500, detail="处理 Webhook 时发生服务器内部错误。")
