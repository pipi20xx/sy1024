from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List
from app import globals
from app.schemas import TmdbMetadataUpdateRequest, TmdbManualGenerateRequest
from app.services.tmdb_update_config import load_config, save_config
from app.logger import logger, log_audit

router = APIRouter(tags=["TMDB 元数据"])

@router.get("/api/tmdb/update-config", summary="获取更新配置")
async def get_tmdb_update_config():
    """获取 TMDB 元数据更新的默认行为配置。"""
    return load_config()

@router.post("/api/tmdb/update-config", summary="保存更新配置")
async def set_tmdb_update_config(config = Body(...)):
    """保存 TMDB 元数据更新的行为配置。"""
    save_config(config)
    return {"status": "success"}

@router.post("/api/tmdb/{item_type}/{tmdb_id}/update-metadata", summary="更新 TMDB 元数据")
async def update_tmdb_metadata(
    item_type: str,
    tmdb_id: str,
    request: TmdbMetadataUpdateRequest,
    lang = Query("zh-CN"),
    season_number = Query(None),
    episode_number = Query(None)
):
    """
    直接从 TMDB 官方 API 拉取最新元数据并更新到本地 Override 文件。
    """

    s_num = None
    if season_number is not None:
        try:
            s_num = int(season_number)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="season_number 必须是整数")

    e_num = None
    if episode_number is not None:
        try:
            e_num = int(episode_number)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="episode_number 必须是整数")

    # 验证逻辑
    if item_type in ["season", "episode"] and s_num is None:
        raise HTTPException(status_code=400, detail="季/集类型需要季号参数")
    if item_type == "episode" and e_num is None:
        raise HTTPException(status_code=400, detail="集类型需要集号参数")

    success, message = await globals.service.tmdb_metadata_service.update_metadata(
        item_type=item_type,
        tmdb_id=str(tmdb_id),
        lang=str(lang),
        fields=request.fields_to_update,
        overwrite=request.overwrite,
        season_number=s_num,
        episode_number=e_num,
        trigger_refresh=request.trigger_emby_refresh,
        update_season_episodes=request.update_season_episodes
    )

    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {"status": "success", "message": message}

@router.get("/api/tmdb/bangumi-preview/{subject_id}", summary="获取 Bangumi 预览")
async def preview_bangumi_subject(subject_id: int):
    """获取指定 Bangumi ID 的精简预览信息（用于映射校验）。"""
    try:
        return await globals.service.tmdb_metadata_service.get_bangumi_preview(subject_id)
    except Exception as e:
        log_audit("元数据", "失败", f"Bangumi 预览错误: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/tmdb/manual-generate", summary="手动生成覆盖数据")
async def manual_generate_tmdb_override(request: TmdbManualGenerateRequest):
    """根据输入的源 TMDB ID 手动为目标项目生成本地元数据覆盖文件。"""
    success, message = await globals.service.tmdb_metadata_service.generate_custom_override(
        source_item_type=request.source_item_type,
        source_tmdb_id=str(request.source_tmdb_id),
        target_tmdb_id=str(request.target_tmdb_id),
        lang=request.lang,
        source_season=request.source_season,
        target_season=request.target_season,
        source_episode=request.source_episode,
        target_episode=request.target_episode,
        overwrite=request.overwrite,
        recursive=request.recursive,
        trigger_refresh=request.trigger_emby_refresh,
        source=request.source,
        target_item_type=request.target_item_type
    )

    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {"status": "success", "message": message}
