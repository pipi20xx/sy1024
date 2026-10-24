from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, Response
from typing import Optional, List
import asyncio
import os
import json
from .. import globals
from app.logger import logger, log_audit
from ..schemas import (
    BatchDetailsRequest, ResourceUpdateRequest, LockNameRequest
)

router = APIRouter(tags=["媒体项目"])

# --- 核心媒体查询接口 ---

@router.post("/api/items/batch-details", summary="批量获取项目详情")
async def get_items_batch_details(request: BatchDetailsRequest):
    """批量获取电影或剧集的详细信息。"""
    try:
        items_details = await globals.service.scanner_service.get_items_by_ids(
            movie_ids=request.movie_ids,
            series_ids=request.series_ids
        )
        return items_details
    except Exception as e:
        log_audit("项目", "失败", f"批量获取详情时出错: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/items/{item_type}", summary="按类型获取项目列表")
async def get_items_by_type(item_type: str, request: Request):
    """按类型获取项目列表，支持搜索、过滤和分页。"""
    params = request.query_params
    try:
        page = int(params.get("page", 1))
        limit = int(params.get("limit", 50))
    except (ValueError, TypeError):
        page = 1
        limit = 50

    if page < 1: page = 1
    if limit < 1: limit = 1
    if limit > 200: limit = 200
    
    year_str = params.get("year")
    month_str = params.get("month")
    
    return await globals.service.scanner_service.get_items(
        item_type, 
        search_term=params.get("search_term"),
        source=params.get("source"),
        poster_status=params.get("poster_status"),
        genres=params.getlist("genre"),
        year=int(year_str) if year_str and year_str.isdigit() else None,
        month=int(month_str) if month_str and month_str.isdigit() else None,
        sort_by=params.get("sort_by"),
        page=page,
        limit=limit
    )

@router.get("/api/items/{item_type}/{item_id}/details", summary="获取项目详情")
async def get_item_details(item_type: str, item_id: str, request: Request):
    """获取指定项目的详细元数据和状态。"""
    view_mode = request.query_params.get('view_mode', 'standard')
    details = await globals.service.editor_service.get_item_full_details(item_type, item_id, view_mode=view_mode)
    if not details:
        raise HTTPException(status_code=404, detail="未找到项目详情或加载失败")
    return details

@router.put("/api/items/{item_type}/{item_id}", summary="更新项目元数据")
async def update_item(item_type: str, item_id: str, request: Request):
    """更新指定项目的元数据信息。"""
    try:
        updated_data = await request.json()
        success, message, new_item_id = await globals.service.editor_service.update_item_metadata(item_type, item_id, updated_data)
        if success and new_item_id:
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, new_item_id)})
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        log_audit("项目", "更新", f"更新项目 {item_type}/{item_id} 时发生错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/items/{item_type}/{item_id}/full-save", summary="全量保存项目详情")
async def save_full_details(item_type: str, item_id: str, request: Request):
    """
    保存项目的所有元数据，包括主条目、季和集。
    主要用于 AI 批量翻译后的持久化。
    """
    try:
        data = await request.json()
        # 1. 保存主条目
        full_metadata = data.get("full_metadata", {})
        if full_metadata:
            success, msg, _ = await globals.service.editor_service.update_item_metadata(item_type, item_id, full_metadata)
            if not success:
                raise HTTPException(status_code=400, detail=f"主条目保存失败: {msg}")

        # 2. 如果是剧集，保存季和集
        if item_type == "tmdb-tv" and "seasons" in data:
            for season in data["seasons"]:
                s_num = season.get("season_number")
                s_meta = season.get("metadata")
                if s_num is not None and s_meta:
                    s_success, s_msg = await globals.service.editor_service.update_season_metadata(item_id, s_num, s_meta, update_episodes=False)
                    if not s_success:
                        raise HTTPException(status_code=400, detail=f"季 {s_num} 保存失败: {s_msg}")
                
                # 保存集
                if "episodes" in season:
                    for episode in season["episodes"]:
                        e_num = episode.get("episode_number")
                        e_meta = episode.get("metadata")
                        if e_num is not None and e_meta:
                            e_success, e_msg = await globals.service.editor_service.update_episode_metadata(item_id, s_num, e_num, e_meta)
                            if not e_success:
                                raise HTTPException(status_code=400, detail=f"集 S{s_num}E{e_num} 保存失败: {e_msg}")

        return {"message": "全量数据已成功持久化到磁盘", "success": True}
    except HTTPException:
        raise
    except Exception as e:
        log_audit("项目", "失败", f"全量保存失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

# --- 资源 (Resources/Attachments) ---

@router.get("/api/items/{item_type}/{item_id}/resources", summary="获取项目资源")
async def get_item_resources(item_type: str, item_id: str):
    """获取指定项目关联的所有附件资源结构。"""
    success, data_or_msg = globals.resource_service.get_resources(item_type, item_id)
    if not success:
        raise HTTPException(status_code=500, detail=data_or_msg)
    return data_or_msg

@router.post("/api/items/{item_type}/{item_id}/resources", summary="保存项目资源")
async def save_item_resources(item_type: str, item_id: str, data: ResourceUpdateRequest):
    """保存并更新指定项目的附件资源结构。"""
    success, message = globals.resource_service.save_resources(item_type, item_id, data.root)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"message": message, "success": True}

@router.post("/api/items/{item_type}/{item_id}/attachments", summary="上传附件")
async def upload_attachment(item_type: str, item_id: str, file: UploadFile = File(...)):
    """为项目上传一个新的附件文件。"""
    success, message = await globals.resource_service.save_attachment(item_type, item_id, file)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"message": "附件上传成功。", "filename": message, "success": True}

@router.get("/api/items/{item_type}/{item_id}/attachments/{filename}", summary="下载附件")
async def download_attachment(item_type: str, item_id: str, filename: str):
    """下载指定项目的特定附件文件。"""
    success, path_or_msg = globals.resource_service.get_attachment_path(item_type, item_id, filename)
    if not success:
        raise HTTPException(status_code=404, detail=path_or_msg)
    return FileResponse(path_or_msg, filename=filename)

# --- 图片相关 ---

@router.get("/api/items/{item_type}/{item_id}/web-images", summary="获取网络图片")
async def get_web_images_for_item(item_type: str, item_id: str, request: Request): 
    """从网络（如 TMDB、Fanart）搜索并获取可选的项目图片。"""
    final_image_types = []
    final_sources = []
    
    # 手动解析 query params 以兼容加密环境的严格类型检查
    # 前端发送格式: ?image_types=poster,logo
    image_types_param = request.query_params.get("image_types")
    sources_param = request.query_params.get("sources")
    
    if image_types_param:
        final_image_types.extend([t.strip() for t in image_types_param.split(',') if t.strip()])
    
    if sources_param:
        final_sources.extend([s.strip().lower() for s in sources_param.split(',') if s.strip()])
            
    # get_web_images 内部是同步 requests + 文件读取，必须放线程池避免阻塞事件循环
    success, data_or_msg = await asyncio.to_thread(
        globals.service.image_service.get_web_images, item_type, item_id, final_image_types, final_sources
    )
    if not success:
        raise HTTPException(status_code=404, detail=data_or_msg)
    return data_or_msg

# --- 季/集 网络图片相关 ---

@router.get("/api/tv/{series_id}/seasons/{season_number}/web-images", summary="获取季度网络图片")
async def get_season_web_images(series_id: str, season_number: int, request: Request):
    """从 TMDb 获取指定季度的可选图片（海报等）。"""
    final_image_types = []
    final_sources = []
    image_types_param = request.query_params.get("image_types")
    sources_param = request.query_params.get("sources")
    if image_types_param:
        final_image_types.extend([t.strip() for t in image_types_param.split(',') if t.strip()])
    if sources_param:
        final_sources.extend([s.strip().lower() for s in sources_param.split(',') if s.strip()])

    success, data_or_msg = await asyncio.to_thread(
        globals.service.image_service.get_season_web_images, series_id, season_number, final_image_types, final_sources
    )
    if not success:
        raise HTTPException(status_code=404, detail=data_or_msg)
    return data_or_msg

@router.post("/api/tv/{series_id}/seasons/{season_number}/web-images", summary="保存季度网络图片")
async def save_season_web_images(series_id: str, season_number: int, request: Request):
    """保存选中的季度网络图片到本地 Override。"""
    try:
        behavior = request.query_params.get("behavior", "overwrite")
        images_to_save = await request.json()
        if not isinstance(images_to_save, list):
            raise HTTPException(status_code=400, detail="请求体必须是一个JSON数组。")
        success, message = await globals.service.image_service.save_season_web_images(series_id, season_number, images_to_save, behavior=behavior)
        if not success:
            raise HTTPException(status_code=500, detail=message)
        return {
            "message": message,
            "success": True,
            "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON格式。")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        log_audit("项目", "失败", f"保存季度网络图片时发生未知错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/tv/{series_id}/episodes/{season_number}/{episode_number}/web-images", summary="获取集网络图片")
async def get_episode_web_images(series_id: str, season_number: int, episode_number: int, request: Request):
    """从 TMDb 获取指定集的可选图片（剧照 stills）。"""
    final_image_types = []
    final_sources = []
    image_types_param = request.query_params.get("image_types")
    sources_param = request.query_params.get("sources")
    if image_types_param:
        final_image_types.extend([t.strip() for t in image_types_param.split(',') if t.strip()])
    if sources_param:
        final_sources.extend([s.strip().lower() for s in sources_param.split(',') if s.strip()])

    success, data_or_msg = await asyncio.to_thread(
        globals.service.image_service.get_episode_web_images, series_id, season_number, episode_number, final_image_types, final_sources
    )
    if not success:
        raise HTTPException(status_code=404, detail=data_or_msg)
    return data_or_msg

@router.post("/api/tv/{series_id}/episodes/{season_number}/{episode_number}/web-images", summary="保存集网络图片")
async def save_episode_web_images(series_id: str, season_number: int, episode_number: int, request: Request):
    """保存选中的集网络图片到本地 Override。"""
    try:
        behavior = request.query_params.get("behavior", "overwrite")
        images_to_save = await request.json()
        if not isinstance(images_to_save, list):
            raise HTTPException(status_code=400, detail="请求体必须是一个JSON数组。")
        success, message = await globals.service.image_service.save_episode_web_images(series_id, season_number, episode_number, images_to_save, behavior=behavior)
        if not success:
            raise HTTPException(status_code=500, detail=message)
        return {
            "message": message,
            "success": True,
            "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON格式。")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        log_audit("项目", "失败", f"保存集网络图片时发生未知错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/items/{item_type}/{item_id}/web-images", summary="保存网络图片")
async def save_web_images_for_item(item_type: str, item_id: str, request: Request):
    """保存并应用选中的网络图片到本地 Override。"""
    try:
        behavior = request.query_params.get("behavior", "overwrite")
        images_to_save = await request.json()
        if not isinstance(images_to_save, list):
            raise HTTPException(status_code=400, detail="请求体必须是一个JSON数组。")

        success, message = await globals.service.image_service.save_web_images(item_type, item_id, images_to_save, behavior=behavior)

        if not success:
            raise HTTPException(status_code=500, detail=message)

        return {
            "message": message,
            "success": True,
            "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的JSON格式。")
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        log_audit("项目", "失败", f"保存在线图片时发生未知错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

# --- Override & Cache Ops ---

@router.get("/api/items/override/metadata", summary="扫描所有覆盖元数据")
async def get_all_override_metadata():
    """
    直接扫描磁盘上的 override 目录并返回所有项目的元数据列表。
    """
    success, result = await globals.service.editor_service.get_all_override_items_metadata()
    if not success:
        raise HTTPException(status_code=500, detail=result)
    
    # 手动格式化 JSON 以满足用户需求
    content = json.dumps(result, indent=2, ensure_ascii=False)
    return Response(content=content, media_type="application/json")

@router.post("/api/items/{item_type}/{item_id}/copy-to-override", summary="复制到覆盖目录")
async def copy_to_override(item_type: str, item_id: str):
    """将项目当前的原始数据复制到 Override 目录以便编辑。"""
    success, message = await globals.service.editor_service.copy_item_to_override(item_type, item_id)
    if not success: raise HTTPException(status_code=400, detail=message)

@router.post("/api/items/{item_type}/{item_id}/lock-name", summary="锁定/解锁项目名称")
async def lock_name(item_type: str, item_id: str, request: LockNameRequest):
    """防止自动扫描时覆盖手动修改的项目名称。"""
    success, message = await globals.service.editor_service.lock_item_name(item_type, item_id, request.mode)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})

@router.put("/api/items/{item_type}/{item_id}/patch-name", summary="更新 Patches 中的名称")
async def update_patch_name(item_type: str, item_id: str, request: Request):
    """直接更新 patches 文件中的名称字段，不需要 Override 有主 JSON。"""
    try:
        data = await request.json()
        new_name = str(data.get("name", "")).strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="名称不能为空")
        success, message = await globals.service.editor_service.update_patch_name(item_type, item_id, new_name)
        if success:
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        log_audit("编辑", "更新", f"更新 Patches 名称失败: {item_type}/{item_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/items/{item_type}/{item_id}/refresh-cache", summary="刷新项目缓存")
async def refresh_item_cache(item_type: str, item_id: str):
    """强制刷新指定项目的内存缓存。"""
    success, message = await globals.service.scanner_service.refresh_item_cache(item_type, item_id)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})

@router.delete("/api/items/{item_type}/{item_id}/override", summary="删除覆盖目录")
async def delete_override(item_type: str, item_id: str):
    """删除该项目的整个 Override 文件夹。"""
    success, message = await globals.service.editor_service.delete_override_folder(item_type, item_id)
    if not success: raise HTTPException(status_code=500, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True})

@router.delete("/api/items/{item_type}/{item_id}/cache", summary="删除主缓存目录")
async def delete_cache(item_type: str, item_id: str):
    """删除该项目的原始元数据缓存文件夹。"""
    success, message = await globals.service.editor_service.delete_cache_folder(item_type, item_id)
    if not success: raise HTTPException(status_code=500, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True})

@router.delete("/api/items/{item_type}/{item_id}/override/images", summary="删除覆盖图片")
async def delete_override_images(item_type: str, item_id: str):
    """删除该项目在 Override 目录下的所有本地图片。"""
    success, message = await globals.service.editor_service.delete_item_images(item_type, item_id)
    if not success: raise HTTPException(status_code=500, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})

@router.delete("/api/items/{item_type}/{item_id}/override/patches", summary="删除 Patches 文件夹")
async def delete_override_patches(item_type: str, item_id: str):
    """删除该项目在 Override 目录下的 Patches 文件夹。"""
    success, message = await globals.service.editor_service.delete_patches_folder(item_type, item_id)
    if not success: raise HTTPException(status_code=500, detail=message)
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})

@router.delete("/api/items/{item_type}/{item_id}/override/metadata", summary="删除覆盖元数据")
async def delete_override_metadata(item_type: str, item_id: str, request: Request):
    """从本地 Override 目录中删除指定的元数据字段。"""
    mode = request.query_params.get("mode", "all")
    success, message = await globals.service.editor_service.delete_item_metadata(item_type, item_id, mode=mode)
    if not success: raise HTTPException(status_code=500, detail=message)

@router.post("/api/items/{item_type}/{item_id}/refresh-metadata-from-bangumi", summary="从 Bangumi 刷新元数据")
async def refresh_metadata_from_bangumi(item_type: str, item_id: str, request: Request):
    """从 Bangumi 获取最新信息并更新到本地 Override 覆盖文件。"""
    try:
        data = await request.json()
    except Exception:
        data = {}
    
    bangumi_id = data.get('bangumi_id')
    if bangumi_id is not None:
        try:
            bangumi_id = int(bangumi_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="无效的 Bangumi ID，必须为整数。")

    fields = data.get('fields') # List[str] or None
    force_refresh = data.get('force_refresh', False)
    use_whitelist = data.get('use_whitelist', False)
    mode = data.get('mode', 'merge')
    
    success, message = await globals.service.editor_service.update_metadata_from_bangumi(
        item_type, item_id, bangumi_id, fields, force_refresh, use_whitelist, mode
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
        
    return {
        "message": message,
        "success": True,
        "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)
    }

@router.get("/api/items/{item_type}/{item_id}/bangumi-recommendation", summary="获取 Bangumi 推荐")
async def get_bangumi_recommendation(item_type: str, item_id: str):
    """
    根据 TMDB ID 获取智能 Bangumi 关联推荐。
    """
    # Map item_type to tmdb_type
    tmdb_type = 'movie' if item_type == 'tmdb-movies2' else 'tv'
    
    # 1. Check existing
    existing = await globals.relation_service.get_relation(item_id, tmdb_type)
    if existing:
        rel = existing[0]

        def _rel_summary(r: dict) -> dict:
            return {
                "bangumi_id": r.get('bangumi_id'),
                "bangumi_title": r.get('bangumi_name_cn') or r.get('bangumi_name'),
                "score": r.get('score'),
                "type": r.get('bangumi_type'),
                "platform_cn": r.get('bangumi_platform_cn'),
                "year": r.get('bangumi_date'),
                "source": r.get('source', ''),
                "season_number": r.get('season_number'),
            }

        return {
            "status": "linked",
            "bangumi_id": rel['bangumi_id'],
            "bangumi_title": rel.get('bangumi_name_cn') or rel.get('bangumi_name'),
            "score": rel.get('score'),
            "note": rel.get('note'),
            "type": rel.get('bangumi_type'),
            "platform_cn": rel.get('bangumi_platform_cn'),
            "year": rel.get('bangumi_date'),
            "source": rel.get('source', ''),
            "relations": [_rel_summary(r) for r in existing]
        }
    
    # 2. Get Recommendation
    rec = await globals.relation_service.get_single_recommendation(item_id, tmdb_type)
    if rec.get('found'):
        return {
            "status": "recommended",
            "bangumi_id": rec['bangumi_id'],
            "bangumi_title": rec['bangumi_title'],
            "score": rec['score'],
            "year": rec.get('year'),
            "type": rec.get('type'),
            "platform_cn": rec.get('platform_cn')
        }
    else:
        return {
            "status": "none",
            "message": "未找到匹配的 Bangumi 条目"
        }

# --- 辅助接口 (Genres/Years) ---

@router.get("/api/genres/{item_type}", summary="获取可用流派")
async def get_genres(item_type: str):
    """获取指定媒体库类型下的所有流派列表。"""
    if item_type not in ["tmdb-tv", "tmdb-movies2"]: return []
    return globals.service.scanner_service.get_available_genres(item_type)

@router.get("/api/years/{item_type}", summary="获取可用年份")
async def get_years(item_type: str):
    """获取指定媒体库类型下的所有发布年份列表。"""
    if item_type not in ["tmdb-tv", "tmdb-movies2"]: return []
    return await globals.service.scanner_service.get_available_years(item_type)

# --- 剧集相关 (TV Seasons/Episodes/Groups) ---

@router.put("/api/tv/{series_id}/seasons/{season_number}", summary="更新季度元数据")
async def update_season(series_id: str, season_number: int, request: Request):
    """更新指定剧集季度的元数据信息。"""
    update_episodes = request.query_params.get('update_episodes', 'false').lower() == 'true'
    try:
        updated_data = await request.json()
        success, message = await globals.service.editor_service.update_season_metadata(series_id, season_number, updated_data, update_episodes)
        if success:
            log_audit("编辑", "更新", f"已更新季度元数据: {series_id} S{season_number}" + (" (含分集)" if update_episodes else ""), level="SUCCESS")
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        log_audit("编辑", "更新", f"更新季度元数据失败: {series_id} S{season_number}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/api/tv/{series_id}/episodes/{season_number}/{episode_number}", summary="更新分集元数据")
async def update_episode(series_id: str, season_number: int, episode_number: int, request: Request):
    """更新指定剧集分集的元数据信息。"""
    try:
        updated_data = await request.json()
        success, message = await globals.service.editor_service.update_episode_metadata(series_id, season_number, episode_number, updated_data)
        if success:
            log_audit("编辑", "更新", f"已更新分集元数据: {series_id} S{season_number}E{episode_number}", level="SUCCESS")
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        log_audit("编辑", "更新", f"更新分集元数据失败: {series_id} S{season_number}E{episode_number}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/tv/{series_id}/seasons/{season_number}/override/metadata", summary="删除季度覆盖元数据")
async def delete_season_metadata(series_id: str, season_number: int, request: Request):
    """删除指定剧集季度的本地 Override 覆盖数据。"""
    include_episodes = request.query_params.get('include_episodes', 'false').lower() == 'true'
    success, message = await globals.service.editor_service.delete_season_metadata(series_id, season_number, include_episodes)
    if not success: raise HTTPException(status_code=400, detail=message)
    log_audit("编辑", "删除", f"已删除季度覆盖: {series_id} S{season_number}" + (" (含分集)" if include_episodes else ""), level="CLEAN")
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})

@router.delete("/api/tv/{series_id}/episodes/{season_number}/{episode_number}/override/metadata", summary="删除分集覆盖元数据")
async def delete_episode_metadata(series_id: str, season_number: int, episode_number: int):
    """删除指定剧集分集的本地 Override 覆盖数据。"""
    success, message = await globals.service.editor_service.delete_episode_metadata(series_id, season_number, episode_number)
    if not success: raise HTTPException(status_code=400, detail=message)
    log_audit("编辑", "删除", f"已删除分集覆盖: {series_id} S{season_number}E{episode_number}", level="CLEAN")
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})

@router.get("/api/tv/{series_id}/aggregated-credits", summary="获取全剧聚合演职员表")
async def get_tv_aggregated_credits(series_id: str):
    """
    聚合该剧集下所有季和集的所有演职员信息，并按 (ID, 角色名) 去重。
    """
    try:
        credits = await globals.service.editor_service.get_series_aggregated_credits(series_id)
        return credits
    except Exception as e:
        log_audit("项目", "失败", f"聚合演职员失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

# Episode Group/Order handlers
@router.get("/api/tv/{series_id}/episodegroup", summary="获取剧集组内容")
async def get_episode_group(series_id: str):
    """获取指定剧集的剧集组（Episode Group）配置内容。"""
    success, data_or_msg = globals.service.editor_service.get_episode_group_content(series_id)
    if not success: raise HTTPException(status_code=500, detail=data_or_msg)
    return JSONResponse(status_code=200, content=data_or_msg)

@router.put("/api/tv/{series_id}/episodegroup", summary="更新剧集组内容")
async def update_episode_group_route(series_id: str, request: Request):
    """保存并更新指定剧集的剧集组配置。"""
    try:
        updated_data = await request.json()
        success, message = await globals.service.editor_service.update_episode_group_content(series_id, updated_data)
        if success:
            log_audit("编辑", "更新", f"已更新剧集组内容: {series_id}", level="SUCCESS")
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        log_audit("编辑", "更新", f"更新剧集组内容失败: {series_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tv/{series_id}/episodegroup", summary="创建剧集组文件")
async def create_episode_group(series_id: str):
    """为指定剧集创建一个新的剧集组配置文件。"""
    success, message = await globals.service.editor_service.create_episode_group_file(series_id)
    if not success: raise HTTPException(status_code=400, detail=message)
    log_audit("编辑", "创建", f"已创建剧集组文件: {series_id}", level="SUCCESS")
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})

@router.delete("/api/tv/{series_id}/episodegroup", summary="删除剧集组文件")
async def delete_episode_group(series_id: str):
    """删除指定剧集的剧集组配置文件。"""
    success, message = await globals.service.editor_service.delete_episode_group_file(series_id)
    if not success: raise HTTPException(status_code=500, detail=message)
    log_audit("编辑", "删除", f"已删除剧集组文件: {series_id}", level="CLEAN")
    return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})

@router.get("/api/tv/{series_id}/episodeorder", summary="获取剧集排序内容")
async def get_episode_order(series_id: str):
    """获取指定剧集的自定义剧集排序配置。"""
    success, data_or_msg = globals.service.editor_service.get_episode_order_content(series_id)
    if not success: raise HTTPException(status_code=500, detail=data_or_msg)
    return JSONResponse(status_code=200, content=data_or_msg)

@router.put("/api/tv/{series_id}/episodeorder", summary="更新剧集排序内容")
async def update_episode_order_route(series_id: str, request: Request):
    """保存并更新指定剧集的自定义剧集排序。"""
    try:
        updated_data = await request.json()
        success, message = await globals.service.editor_service.update_episode_order_content(series_id, updated_data)
        if success:
            log_audit("编辑", "更新", f"已更新剧集排序内容: {series_id}", level="SUCCESS")
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details("tmdb-tv", series_id)})
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        log_audit("编辑", "更新", f"更新剧集排序内容失败: {series_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/tv/{series_id}/episodeorder", summary="删除剧集排序文件")
async def delete_episode_order_route(series_id: str):
    """删除指定剧集的自定义剧集排序配置文件。"""
    try:
        success, message = await globals.service.editor_service.delete_episode_order_file(series_id) 
        if success:
            log_audit("编辑", "删除", f"已删除剧集排序文件: {series_id}", level="CLEAN")
            return JSONResponse(status_code=200, content={"message": message, "success": True})
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        log_audit("编辑", "删除", f"删除剧集排序文件失败: {series_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

# External IDs handlers
@router.get("/api/items/{item_type}/{item_id}/externalids", summary="获取自定义外部ID内容")
async def get_external_ids(item_type: str, item_id: str):
    """获取指定项目的自定义外部ID配置内容。"""
    success, data_or_msg = globals.service.editor_service.get_external_ids_content(item_type, item_id)
    if not success: raise HTTPException(status_code=500, detail=data_or_msg)
    return JSONResponse(status_code=200, content=data_or_msg)

@router.put("/api/items/{item_type}/{item_id}/externalids", summary="更新自定义外部ID内容")
async def update_external_ids_route(item_type: str, item_id: str, request: Request):
    """保存并更新指定项目的自定义外部ID配置。"""
    try:
        updated_data = await request.json()
        success, message = await globals.service.editor_service.update_external_ids_content(item_type, item_id, updated_data)
        if success:
            log_audit("编辑", "更新", f"已更新外部ID: {item_id} ({item_type})", level="SUCCESS")
            return JSONResponse(status_code=200, content={"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)})
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        log_audit("编辑", "更新", f"更新外部ID失败: {item_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/items/{item_type}/{item_id}/externalids", summary="删除自定义外部ID文件")
async def delete_external_ids_route(item_type: str, item_id: str):
    """删除指定项目的自定义外部ID配置文件。"""
    try:
        success, message = await globals.service.editor_service.delete_external_ids_file(item_type, item_id)
        if success:
            log_audit("编辑", "删除", f"已删除外部ID文件: {item_id} ({item_type})", level="CLEAN")
            return JSONResponse(status_code=200, content={"message": message, "success": True})
        raise HTTPException(status_code=400, detail=message)
    except Exception as e:
        log_audit("编辑", "删除", f"删除外部ID文件失败: {item_id}: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))
