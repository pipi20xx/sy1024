from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
from app.services.preview_generator import preview_service
from fastapi.responses import FileResponse
import os
import shutil
import asyncio
from .. import globals
from app.logger import log_audit
from ..common import SOURCE_OVERRIDE

router = APIRouter(tags=["预览图生成"])

class GenerateRequest(BaseModel):
    item_id: str
    count: int = 12
    start_pct: int = 10
    end_pct: int = 90
    path_mappings: Optional[List[Dict[str, str]]] = []

class GenerateResponse(BaseModel):
    success: bool
    message: str
    images: List[str] = []
    session_id: Optional[str] = None

class UploadRequest(BaseModel):
    item_id: str
    image_url: str

class UploadResponse(BaseModel):
    success: bool
    message: str

class ConfigRequest(BaseModel):
    count: Optional[int] = 12
    start_pct: Optional[int] = 10
    end_pct: Optional[int] = 90
    path_mappings: Optional[List[Dict[str, str]]] = []

class GenerateByTmdbRequest(BaseModel):
    item_type: str  # 'tmdb-movies2' or 'tmdb-tv'
    tmdb_id: str
    count: Optional[int] = None
    start_pct: Optional[int] = None
    end_pct: Optional[int] = None
    path_mappings: Optional[List[Dict[str, str]]] = []
    # 剧集专用：指定季/集以定位到单集视频文件
    season_number: Optional[int] = None
    episode_number: Optional[int] = None

class SaveToOverrideRequest(BaseModel):
    item_type: str  # 'tmdb-movies2' or 'tmdb-tv'
    tmdb_id: str
    image_url: str  # relative URL: /static/temp_previews/{session_id}/preview_1.jpg
    image_type: str = 'poster'  # target image type: poster / fanart / thumb
    # 剧集专用：指定季/集时，按集级别命名规则保存（season-X-episode-Y.jpg）
    season_number: Optional[int] = None
    episode_number: Optional[int] = None

@router.get("/api/previews/config", summary="获取预览图配置")
async def get_preview_config():
    """获取视频预览图生成的默认参数配置。"""
    return preview_service.get_config()

@router.post("/api/previews/config", summary="保存预览图配置")
async def save_preview_config(req: ConfigRequest):
    """更新并保存视频预览图生成的参数配置。"""
    success, msg = preview_service.save_config(req.dict())
    if not success:
        raise HTTPException(status_code=500, detail=msg)
    log_audit("预览图", "保存配置", f"数量: {req.count}, 范围: {req.start_pct}%-{req.end_pct}%")
    return {"message": msg, "success": True}

@router.post("/api/previews/generate", summary="开始生成预览图", response_model=GenerateResponse)
async def generate_previews(req: GenerateRequest):
    """根据视频文件生成指定数量的截图预览。"""
    log_audit("预览图", "生成", f"ID: {req.item_id}, 数量: {req.count}", level="START")
    success, msg, images, session_id = await preview_service.generate_previews(
        req.item_id, req.count, req.start_pct, req.end_pct, req.path_mappings
    )
    if not success:
        log_audit("预览图", "生成失败", f"ID: {req.item_id}, 错误: {msg}", level="ERROR")
    else:
        log_audit("预览图", "生成完成", f"ID: {req.item_id}, 截图: {len(images)}张", level="SUCCESS")
    return GenerateResponse(success=success, message=msg, images=images, session_id=session_id)

@router.post("/api/previews/upload", summary="上传选中的预览图", response_model=UploadResponse)
async def upload_preview(req: UploadRequest):
    """将选中的预览图上传并应用为该集的海报。"""
    success, msg = await preview_service.upload_selected_image(req.item_id, req.image_url)
    if success:
        log_audit("预览图", "上传", f"ID: {req.item_id}", level="SUCCESS")
    else:
        log_audit("预览图", "上传失败", f"ID: {req.item_id}, 错误: {msg}", level="ERROR")
    return UploadResponse(success=success, message=msg)


@router.post("/api/previews/generate-by-tmdb", summary="通过 TMDB ID 生成视频截图", response_model=GenerateResponse)
async def generate_previews_by_tmdb(req: GenerateByTmdbRequest):
    """
    通过 TMDB ID 自动查找 Emby Item ID，然后使用 ffmpeg 截取视频画面。
    用于详情页图片管理中直接从视频文件截取画面作为图片。
    对于剧集 (tmdb-tv)，可通过 season_number + episode_number 定位到单集视频文件。
    """
    if not globals.service or not globals.service.emby_client:
        raise HTTPException(status_code=400, detail="Emby 客户端未连接")

    log_audit("预览图", "生成", f"TMDB ID: {req.tmdb_id}, 类型: {req.item_type}, 数量: {req.count}, 季: {req.season_number}, 集: {req.episode_number}", level="START")

    # 1. 从本地缓存读取标题（优先标题搜索 Emby）
    titles = await asyncio.to_thread(
        globals.service.emby_integration_service._get_titles_from_local_cache,
        req.item_type, req.tmdb_id
    )

    # 2. 确定要截图的 Emby Item ID
    emby_item_id = None
    item_name = "未知"

    if req.item_type == "tmdb-tv" and req.season_number is not None and req.episode_number is not None:
        # 剧集模式：通过季/集号定位到单集的 Emby Episode ID
        episode_info = await globals.service.emby_client.get_episode_info(
            req.tmdb_id, req.season_number, req.episode_number, titles=titles
        )
        if not episode_info or not episode_info.get('exists'):
            msg = f"在 Emby 中找不到 TMDB ID {req.tmdb_id} 的 S{req.season_number}E{req.episode_number}"
            log_audit("预览图", "生成失败", msg, level="ERROR")
            return GenerateResponse(success=False, message=msg, images=[], session_id=None)

        emby_item_id = episode_info.get('episode_id')
        item_name = episode_info.get('series_name', '未知')
        log_audit("预览图", "处理", f"找到单集: '{item_name}' S{req.season_number}E{req.episode_number} (ID: {emby_item_id})")
    else:
        # 电影模式或剧集整体模式：通过 TMDB ID 直接查找
        found_items, error = await globals.service.emby_client.find_items_by_tmdb_id(
            req.tmdb_id, req.item_type, titles=titles
        )
        if error or not found_items:
            msg = f"在 Emby 中找不到 TMDB ID 为 {req.tmdb_id} 的项目: {error or '未找到'}"
            log_audit("预览图", "生成失败", msg, level="ERROR")
            return GenerateResponse(success=False, message=msg, images=[], session_id=None)

        emby_item_id = found_items[0].get("Id")
        item_name = found_items[0].get("Name", "未知")
        log_audit("预览图", "处理", f"找到 Emby 项目: '{item_name}' (ID: {emby_item_id})")

    # 3. 从已保存的配置中读取截图参数（与"封面预览截图生成"页面共用同一套配置）
    saved_config = preview_service.get_config()
    count = req.count if req.count is not None else saved_config.get('count', 12)
    start_pct = req.start_pct if req.start_pct is not None else saved_config.get('start_pct', 10)
    end_pct = req.end_pct if req.end_pct is not None else saved_config.get('end_pct', 90)
    path_mappings = req.path_mappings if req.path_mappings else saved_config.get('path_mappings', [])

    # 4. 调用现有截图生成逻辑
    success, msg, images, session_id = await preview_service.generate_previews(
        emby_item_id, count, start_pct, end_pct, path_mappings
    )
    if not success:
        log_audit("预览图", "生成失败", f"TMDB ID: {req.tmdb_id}, 错误: {msg}", level="ERROR")
    else:
        log_audit("预览图", "生成完成", f"TMDB ID: {req.tmdb_id}, 截图: {len(images)}张", level="SUCCESS")
    return GenerateResponse(success=success, message=msg, images=images, session_id=session_id)


@router.post("/api/previews/save-to-override", summary="保存截图到覆盖缓存目录", response_model=UploadResponse)
async def save_preview_to_override(req: SaveToOverrideRequest):
    """
    将选中的视频截图保存到 Override 目录。
    - 剧集模式（传入 season_number + episode_number）：按集级别命名规则保存为缩略图
      （season-{s_num}-episode-{e_num}.jpg），与从 Emby 下载集图片的命名一致。
    - 电影/剧集整体模式：按 poster/fanart/thumb 类型命名保存。
    """
    try:
        override_path = globals.service.configuration_service.get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            raise HTTPException(status_code=500, detail="覆盖缓存目录未配置")

        # 将相对 URL 转换为本地文件路径
        clean_path = req.image_url.lstrip('/')
        if clean_path.startswith('static/'):
            clean_path = clean_path[7:]
        full_path = os.path.join("app", "static", clean_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="图片文件已失效或被删除")

        target_images_dir = os.path.join(override_path, req.item_type, req.tmdb_id, "images")
        os.makedirs(target_images_dir, exist_ok=True)

        if req.season_number is not None and req.episode_number is not None:
            # 集级别命名：season-{s_num}-episode-{e_num}.jpg
            # 与 Emby 下载集图片和 find_image_files_for_item 的命名规则一致
            base_name = f"season-{req.season_number}-episode-{req.episode_number}"
            target_filename = f"{base_name}.jpg"
        else:
            # 电影/剧集整体级别命名
            filename_map = {
                "poster": "poster.jpg",
                "fanart": "fanart.jpg",
                "thumb": "landscape.jpg",
            }
            target_filename = filename_map.get(req.image_type, "poster.jpg")
            base_name = os.path.splitext(target_filename)[0]

        # 清除同名旧图片（不同扩展名）
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            possible = os.path.join(target_images_dir, base_name + ext)
            if os.path.isfile(possible):
                try:
                    os.remove(possible)
                except OSError:
                    pass

        target_path = os.path.join(target_images_dir, target_filename)
        await asyncio.to_thread(shutil.copy2, full_path, target_path)

        # 更新数据库
        await globals.service.scanner_service._refresh_item_in_db(req.item_type, req.tmdb_id)

        log_audit("预览图", "保存", f"已保存截图到覆盖目录: {target_filename} (TMDB ID: {req.tmdb_id})", level="SUCCESS")
        return UploadResponse(success=True, message=f"截图已保存为 {target_filename}")
    except HTTPException:
        raise
    except Exception as e:
        log_audit("预览图", "保存失败", f"TMDB ID: {req.tmdb_id}, 错误: {e}", level="ERROR")
        return UploadResponse(success=False, message=str(e))
