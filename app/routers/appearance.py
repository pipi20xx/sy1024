"""
外观 / 壁纸管理 API（移植自 Anime-Manager backend/routers/appearance.py）

- 壁纸源管理：随机 API 源 / 自定义 URL / 本地上传
- 壁纸代理：解决 WebGL CORS 限制，附带磁盘缓存
- 配置持久化到 sytmdb 配置文件（configuration_service）的 wallpaper 字段
"""
import os
import time
import uuid
import hashlib
import logging
import asyncio
import mimetypes
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import Response

from .. import globals
from app.logger import logger

router = APIRouter(prefix="/api/appearance", tags=["appearance"])

# 数据目录 —— 与 tmdb_proxy 等模块一致，遵循 DATA_PATH 环境变量
DATA_DIR = os.environ.get("DATA_PATH", ".")
WALLPAPER_DIR = os.path.join(DATA_DIR, "wallpaper")
WALLPAPER_CACHE_DIR = os.path.join(DATA_DIR, "tmp", "wallpaper")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 预设壁纸 API 源列表 —— 前端展示给用户选择
WALLPAPER_API_SOURCES = [
    {
        "id": "loliapi_acg_pc",
        "name": "LoliAPI ACG (横屏)",
        "url": "https://www.loliapi.com/acg/pc/",
        "category": "acg",
        "orientation": "landscape",
        "is_random": True,
    },
    {
        "id": "loliapi_acg_pe",
        "name": "LoliAPI ACG (竖屏)",
        "url": "https://www.loliapi.com/acg/pe/",
        "category": "acg",
        "orientation": "portrait",
        "is_random": True,
    },
    {
        "id": "loliapi_acg_auto",
        "name": "LoliAPI ACG (双端自适应)",
        "url": "https://www.loliapi.com/acg/",
        "category": "acg",
        "orientation": "any",
        "is_random": True,
    },
    {
        "id": "loliapi_bg",
        "name": "LoliAPI 随机二次元",
        "url": "https://www.loliapi.com/bg/",
        "category": "acg",
        "orientation": "any",
        "is_random": True,
    },
]

# 已知的随机壁纸 API 域名 —— 这些 URL 不变但每次请求返回不同图片
# 用于判断是否需要添加 cache-buster 和使用短缓存
RANDOM_WALLPAPER_DOMAINS = {
    "loliapi.com",
    "www.loliapi.com",
    "api.loliapi.com",
}

# 默认壁纸配置
DEFAULT_WALLPAPER_CONFIG = {
    "source_type": "api",          # "api" | "upload" | "url"
    "api_source_id": "loliapi_acg_pc",  # 选择哪个预设 API 源
    "custom_url": "",              # 自定义固定 URL
    "upload_filename": "",         # 本地上传图片文件名
    "cache_ttl": 30,               # 缓存时间（秒），0 = 不缓存
}


def _get_wallpaper_config() -> dict:
    """从配置文件读取壁纸配置，合并默认值"""
    config = globals.service.configuration_service.get_config()
    wallpaper = config.get("wallpaper", {})
    return {**DEFAULT_WALLPAPER_CONFIG, **wallpaper}


def _save_wallpaper_config(wallpaper: dict):
    """保存壁纸配置到配置文件"""
    globals.service.configuration_service.update_config({"wallpaper": wallpaper})


def _is_random_wallpaper_url(url: str) -> bool:
    """判断 URL 是否指向随机壁纸 API（URL 不变但每次返回不同图片）"""
    try:
        host = urlparse(url).hostname or ""
        return host.lower() in RANDOM_WALLPAPER_DOMAINS
    except Exception:
        return False


def _ensure_wallpaper_dir():
    os.makedirs(WALLPAPER_DIR, exist_ok=True)


def _is_valid_image(data: bytes) -> bool:
    """校验数据是否为有效图片"""
    if not data or len(data) < 16:
        return False
    if data[:3] == b'\xff\xd8\xff':  # JPEG
        return True
    if data[:8] == b'\x89PNG\r\n\x1a\n':  # PNG
        return True
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':  # WebP
        return True
    if data[:6] in (b'GIF87a', b'GIF89a'):  # GIF
        return True
    return False


def _resolve_wallpaper_target_url() -> str:
    """根据壁纸配置解析出最终要请求的目标 URL"""
    wp_config = _get_wallpaper_config()
    source_type = wp_config.get("source_type", "api")

    if source_type == "upload":
        filename = wp_config.get("upload_filename", "")
        if filename:
            return f"local:{filename}"
        # 没有上传图片则回退到 API
        source_type = "api"

    if source_type == "url":
        custom_url = wp_config.get("custom_url", "").strip()
        if custom_url:
            return custom_url
        # 没有自定义 URL 则回退到 API
        source_type = "api"

    if source_type == "api":
        api_id = wp_config.get("api_source_id", "loliapi_acg_pc")
        # 查找预设 API 源
        for source in WALLPAPER_API_SOURCES:
            if source["id"] == api_id:
                return source["url"]
        # 找不到则用默认
        return "https://www.loliapi.com/acg/pc/"

    return "https://www.loliapi.com/acg/pc/"


def _image_content_type(filename_or_path: str) -> str:
    ext = os.path.splitext(filename_or_path)[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".bmp": "image/bmp",
    }.get(ext, mimetypes.guess_type(filename_or_path)[0] or "image/jpeg")


def _local_image_response(filename: str, cache_ttl: int) -> Response:
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="壁纸图片不存在")
    with open(filepath, "rb") as f:
        content = f.read()
    return Response(
        content=content,
        media_type=_image_content_type(filename),
        headers={
            "Cache-Control": f"public, max-age={cache_ttl}",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.get("/wallpaper/sources")
async def get_wallpaper_sources():
    """获取可用的壁纸 API 源列表"""
    return {"sources": WALLPAPER_API_SOURCES}


@router.get("/wallpaper/config")
async def get_wallpaper_config():
    """获取当前壁纸配置"""
    return _get_wallpaper_config()


@router.put("/wallpaper/config")
async def update_wallpaper_config(payload: dict):
    """更新壁纸配置"""
    current = _get_wallpaper_config()
    for key in DEFAULT_WALLPAPER_CONFIG:
        if key in payload:
            current[key] = payload[key]
    _save_wallpaper_config(current)
    logger.info(f"壁纸配置已更新: {current}")
    return {"success": True, "config": current}


@router.get("/wallpaper/uploads")
async def list_wallpaper_uploads():
    """列出所有已上传的壁纸图片"""
    await asyncio.to_thread(_ensure_wallpaper_dir)

    def _list():
        images = []
        for f in sorted(os.listdir(WALLPAPER_DIR)):
            ext = os.path.splitext(f)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                filepath = os.path.join(WALLPAPER_DIR, f)
                images.append({
                    "filename": f,
                    "size": os.path.getsize(filepath),
                })
        return images
    return await asyncio.to_thread(_list)


@router.get("/wallpaper/uploads/{filename}")
async def get_wallpaper_upload(filename: str):
    """读取已上传的壁纸图片"""
    return await asyncio.to_thread(_local_image_response, filename, 3600)


@router.post("/wallpaper/upload")
async def upload_wallpaper(file: UploadFile = File(...)):
    """上传壁纸图片"""
    await asyncio.to_thread(_ensure_wallpaper_dir)

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


@router.delete("/wallpaper/uploads/{filename}")
async def delete_wallpaper_upload(filename: str):
    """删除已上传的壁纸图片"""
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not await asyncio.to_thread(os.path.exists, filepath):
        raise HTTPException(status_code=404, detail="图片不存在")

    await asyncio.to_thread(os.remove, filepath)

    # 如果当前配置正在使用这张图片，清除引用
    wp_config = _get_wallpaper_config()
    if wp_config.get("upload_filename") == filename:
        wp_config["upload_filename"] = ""
        _save_wallpaper_config(wp_config)

    logger.info(f"壁纸图片已删除: {filename}")
    return {"success": True}


@router.get("/wallpaper_proxy")
async def proxy_wallpaper(
    url: str = Query("", description="要代理的壁纸 URL，为空时使用配置中的壁纸源"),
    refresh: bool = Query(False, description="强制刷新（跳过缓存），用于随机壁纸 API"),
):
    """
    代理壁纸图片，解决 WebGL CORS 限制。

    工作模式：
    1. 如果传了 url 参数，直接代理该 URL（兼容前端旧逻辑）。
    2. 如果不传 url，从配置文件的 wallpaper 配置中读取壁纸源：
       - source_type="api": 从预设 API 源列表中获取 URL，代理请求
       - source_type="url": 代理自定义 URL
       - source_type="upload": 直接返回本地 wallpaper 目录中的图片

    缓存策略：
    - 缓存时间由 wallpaper.cache_ttl 配置控制（默认 30 秒）
    - 随机壁纸 API 建议设 30 秒，固定图片建议设 3600 秒
    - refresh=True 可强制跳过缓存
    """
    wp_config = _get_wallpaper_config()

    # 如果传了 url，直接使用；否则从配置解析
    if url.strip():
        target_url = url.strip()
    else:
        target_url = _resolve_wallpaper_target_url()

    # 本地图片模式 —— 读取文件并返回，确保 CORS 头和 Content-Type 正确
    if target_url.startswith("local:"):
        filename = target_url[6:]
        return await asyncio.to_thread(
            _local_image_response, filename, wp_config.get("cache_ttl", 30)
        )

    if not target_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="无效的 URL")

    # 缓存时间由配置控制
    cache_ttl = wp_config.get("cache_ttl", 30)
    if cache_ttl < 0:
        cache_ttl = 0
    skip_cache = refresh or cache_ttl == 0

    # 使用 URL hash 作为缓存 key
    url_hash = hashlib.md5(target_url.encode()).hexdigest()

    # 尝试读取缓存
    cached_files = []
    if not skip_cache:
        try:
            for f in os.listdir(WALLPAPER_CACHE_DIR):
                if f.startswith(url_hash):
                    cached_files.append(f)
        except FileNotFoundError:
            pass

        if cached_files:
            cached_file = os.path.join(WALLPAPER_CACHE_DIR, cached_files[0])
            try:
                stat = os.stat(cached_file)
                age = time.time() - stat.st_mtime
                if age < cache_ttl:
                    def _read_cache():
                        with open(cached_file, "rb") as f:
                            return f.read()
                    cached = await asyncio.to_thread(_read_cache)
                    if cached and _is_valid_image(cached):
                        ct = _image_content_type(cached_files[0])
                        return Response(
                            content=cached,
                            media_type=ct,
                            headers={
                                "Cache-Control": f"public, max-age={cache_ttl}",
                                "Access-Control-Allow-Origin": "*",
                            },
                        )
            except (OSError, IOError):
                pass

    # 下载新图片
    await asyncio.to_thread(lambda: os.makedirs(WALLPAPER_CACHE_DIR, exist_ok=True))
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(target_url)
            if resp.status_code == 200 and _is_valid_image(resp.content):
                content_type = resp.headers.get("content-type", "image/jpeg")
                ext_map = {
                    "image/jpeg": ".jpg", "image/png": ".png",
                    "image/webp": ".webp", "image/gif": ".gif",
                }
                ext = ext_map.get(content_type, ".jpg")

                cache_filename = f"{url_hash}{ext}"
                cache_filepath = os.path.join(WALLPAPER_CACHE_DIR, cache_filename)

                for old in cached_files:
                    try:
                        os.remove(os.path.join(WALLPAPER_CACHE_DIR, old))
                    except OSError:
                        pass

                def _write():
                    with open(cache_filepath, "wb") as f:
                        f.write(resp.content)
                await asyncio.to_thread(_write)

                return Response(
                    content=resp.content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": f"public, max-age={cache_ttl}",
                        "Access-Control-Allow-Origin": "*",
                    },
                )
            else:
                raise HTTPException(status_code=502, detail="壁纸源返回无效数据")
    except httpx.RequestError as e:
        logger.warning(f"壁纸代理请求失败: {e}")
        raise HTTPException(status_code=502, detail=f"壁纸代理失败: {str(e)}")
