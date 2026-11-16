"""
外观 / 壁纸管理 API（移植自 Anime-Manager backend/routers/appearance.py）

- 壁纸源管理：在线源（API 随机 / 自定义 URL）/ 本地上传 / 历史壁纸
- 壁纸代理：解决 WebGL CORS 限制，后台预取由 wallpaper_service 负责
- 配置持久化到 sytmdb 配置文件（configuration_service）的 wallpaper 字段
"""
import os
import uuid
import asyncio

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import Response

from app.logger import logger
from app.wallpaper_service import (
    DEFAULT_WALLPAPER_CONFIG,
    WALLPAPER_API_SOURCES,
    WALLPAPER_DIR,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    find_latest_history_for_source,
    get_wallpaper_config,
    is_valid_image,
    list_history,
    list_uploads,
    notify_wallpaper_config_changed,
    read_local_image,
    record_history,
    remove_library_entry,
    resolve_wallpaper_target,
    save_wallpaper_config,
)

router = APIRouter(prefix="/api/appearance", tags=["appearance"])


@router.get("/wallpaper/sources", summary="获取可用的壁纸 API 源列表")
async def get_wallpaper_sources():
    """获取可用的壁纸 API 源列表"""
    return {"sources": WALLPAPER_API_SOURCES}


@router.get("/wallpaper/config", summary="获取当前壁纸配置")
async def get_wallpaper_config_route():
    """获取当前壁纸配置"""
    return get_wallpaper_config()


@router.put("/wallpaper/config", summary="更新壁纸配置")
async def update_wallpaper_config_route(payload: dict):
    """更新壁纸配置"""
    current = get_wallpaper_config()
    for key in DEFAULT_WALLPAPER_CONFIG:
        if key in payload:
            current[key] = payload[key]
    # 兼容旧字段 cache_ttl → refresh_interval
    if "cache_ttl" in payload and "refresh_interval" not in payload:
        try:
            current["refresh_interval"] = int(payload["cache_ttl"])
        except (TypeError, ValueError):
            pass
    save_wallpaper_config(current)
    notify_wallpaper_config_changed()
    logger.info(f"壁纸配置已更新: {current}")
    return {"success": True, "config": current}


@router.get("/wallpaper/uploads", summary="列出手动上传的壁纸图片")
async def list_wallpaper_uploads():
    """列出手动上传的壁纸图片"""
    return await asyncio.to_thread(list_uploads)


@router.get("/wallpaper/history", summary="列出自动收录的历史壁纸图片")
async def list_wallpaper_history():
    """列出自动收录的历史壁纸图片"""
    return await asyncio.to_thread(list_history)


@router.get("/wallpaper/uploads/{filename}", summary="读取本地壁纸图片（上传/历史通用）")
async def get_wallpaper_upload(filename: str):
    """读取本地壁纸图片"""
    result = await asyncio.to_thread(read_local_image, filename)
    if result is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    content, ct = result
    return Response(
        content=content,
        media_type=ct,
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post("/wallpaper/upload", summary="上传壁纸图片")
async def upload_wallpaper(file: UploadFile = File(...)):
    """上传壁纸图片（写入 data/wallpaper，索引由 library 回填为 upload）"""
    await asyncio.to_thread(lambda: os.makedirs(WALLPAPER_DIR, exist_ok=True))

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(WALLPAPER_DIR, filename)

    def _write_file():
        with open(filepath, "wb") as f:
            f.write(content)
    await asyncio.to_thread(_write_file)

    logger.info(f"壁纸图片已上传: {filename}")
    return {"success": True, "filename": filename}


@router.delete("/wallpaper/uploads/{filename}", summary="删除已上传的壁纸图片")
async def delete_wallpaper_upload(filename: str):
    """删除已上传的壁纸图片"""
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not await asyncio.to_thread(os.path.exists, filepath):
        raise HTTPException(status_code=404, detail="图片不存在")

    await asyncio.to_thread(remove_library_entry, filename, "upload")

    # 如果当前配置正在使用这张图片，清除引用
    wp_config = get_wallpaper_config()
    if wp_config.get("upload_filename") == filename:
        wp_config["upload_filename"] = ""
        save_wallpaper_config(wp_config)
        notify_wallpaper_config_changed()

    logger.info(f"壁纸图片已删除: {filename}")
    return {"success": True}


@router.delete("/wallpaper/history/{filename}", summary="删除历史壁纸图片")
async def delete_wallpaper_history(filename: str):
    """删除历史壁纸图片"""
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not await asyncio.to_thread(os.path.exists, filepath):
        raise HTTPException(status_code=404, detail="图片不存在")

    await asyncio.to_thread(remove_library_entry, filename, "auto")

    wp_config = get_wallpaper_config()
    if wp_config.get("history_filename") == filename:
        wp_config["history_filename"] = ""
        save_wallpaper_config(wp_config)
        notify_wallpaper_config_changed()

    logger.info(f"历史壁纸已删除: {filename}")
    return {"success": True}


@router.get("/wallpaper_proxy", summary="代理壁纸图片（解决 WebGL CORS）")
async def proxy_wallpaper(
    url: str = Query("", description="要代理的壁纸 URL，为空时使用配置中的壁纸源"),
    refresh: bool = Query(False, description="强制刷新（跳过就绪缓存）"),
):
    """
    代理壁纸图片。

    - 本地图（上传/历史）：直接读 data/wallpaper 返回。
    - 在线源：优先返回后台预取好的最新就绪图（秒开），
      只有预取尚未完成或显式传 url 时才实时下载（超时 10s）。
    """
    cfg = get_wallpaper_config()
    explicit_url = url.strip()
    target_url = explicit_url if explicit_url else resolve_wallpaper_target(cfg)

    # 本地图模式
    if target_url.startswith("local:"):
        filename = target_url[6:]
        result = await asyncio.to_thread(read_local_image, filename)
        if result is None:
            raise HTTPException(status_code=404, detail="壁纸图片不存在")
        content, ct = result
        return Response(
            content=content,
            media_type=ct,
            headers={
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*",
            },
        )

    if not target_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="无效的 URL")

    # 在线源：优先返回后台预取好的就绪图
    if not explicit_url and not refresh:
        ready = await asyncio.to_thread(find_latest_history_for_source, cfg)
        if ready:
            result = await asyncio.to_thread(read_local_image, ready.get("filename"))
            if result is not None:
                content, ct = result
                return Response(
                    content=content,
                    media_type=ct,
                    headers={
                        "Cache-Control": "no-store",
                        "Access-Control-Allow-Origin": "*",
                        "X-Wallpaper-Source": "prefetched",
                    },
                )

    # 回退：同步下载（刚启动、预取尚未完成，或显式指定 URL）
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(target_url)
            if resp.status_code == 200 and is_valid_image(resp.content):
                content_type = resp.headers.get("content-type", "image/jpeg")
                if not explicit_url:
                    st = cfg.get("source_type", "api")
                    source_id = cfg.get("api_source_id", "") if st == "api" else ""
                    source_url = target_url if st == "url" else ""
                    await asyncio.to_thread(record_history, resp.content, st, source_id, source_url, content_type)
                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": "no-store",
                        "Access-Control-Allow-Origin": "*",
                    },
                )
            else:
                raise HTTPException(status_code=502, detail="壁纸源返回无效数据")
    except httpx.RequestError as e:
        logger.warning(f"壁纸代理请求失败: {e}")
        raise HTTPException(status_code=502, detail=f"壁纸代理失败: {str(e)}")
