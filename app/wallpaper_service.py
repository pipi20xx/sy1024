"""
壁纸服务：后台自动预取 + 历史图库索引 + 就绪图查找。

设计目标（解决「打开页面实时下载导致卡住」的问题）：
- 在线壁纸（API 随机 / 自定义 URL）由后台循环按 refresh_interval 预取，
  下载成功后写入本地图库 data/wallpaper/（origin=auto），并登记到 library.json。
- /wallpaper_proxy 优先返回「当前源最近一次预取好的图」，前端秒开，不再等网络。
- 手动上传的图（origin=upload）与自动收录的历史图（origin=auto）统一存放于
  data/wallpaper/，用 library.json 区分，前端分两个 TAB 展示。

本模块只依赖 configuration_service / httpx，无循环依赖。
"""
import asyncio
import hashlib
import json
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import httpx

from app import globals
from app.logger import logger

# 统一本地图库目录：手动上传 + 自动收录历史图
DATA_DIR = os.environ.get("DATA_PATH", ".")
WALLPAPER_DIR = os.path.join(DATA_DIR, "wallpaper")
LIBRARY_INDEX_PATH = os.path.join(WALLPAPER_DIR, "library.json")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_FILE_SIZE = 10 * 1024 * 1024
# 自动收录的历史图上限，超出后清理最旧的（不会清理当前配置引用与当前就绪图）
HISTORY_LIMIT = 50

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

DEFAULT_WALLPAPER_CONFIG = {
    "source_type": "api",              # "api" | "url" | "upload" | "history"
    "api_source_id": "loliapi_acg_pc",
    "custom_url": "",
    "upload_filename": "",
    "history_filename": "",
    "refresh_interval": 60,            # 后台自动下载新图的间隔（秒），0 = 停止下载
    "display_mode": "latest",          # 显示方式："latest" 跟随最新 | "rotation" 图库轮播
    "rotation_interval": 60,           # 图库轮播间隔（秒），仅在 display_mode=rotation 时使用
    "rotation_include_history": True,  # 轮播范围：包含历史图库
    "rotation_include_uploads": False, # 轮播范围：包含上传壁纸
}

# 预取触发事件：配置变更时 set，让循环立刻预取一次并重置计时
_prefetch_wake = asyncio.Event()


def _ensure_wallpaper_dir():
    os.makedirs(WALLPAPER_DIR, exist_ok=True)


def _read_raw_config() -> Dict:
    """读取应用配置（若服务尚未初始化则返回空字典，避免导入期崩溃）。"""
    service = getattr(globals, "service", None)
    if service is None or getattr(service, "configuration_service", None) is None:
        return {}
    return service.configuration_service.get_config() or {}


def get_wallpaper_config() -> Dict:
    """从配置文件读取壁纸配置，合并默认值，并兼容旧字段 cache_ttl。"""
    wallpaper = _read_raw_config().get("wallpaper", {}) or {}
    merged = {**DEFAULT_WALLPAPER_CONFIG, **wallpaper}
    # 兼容旧版本：cache_ttl 迁移为 refresh_interval
    if "refresh_interval" not in wallpaper and "cache_ttl" in wallpaper:
        try:
            merged["refresh_interval"] = int(wallpaper.get("cache_ttl"))
        except (TypeError, ValueError):
            pass
    merged.pop("cache_ttl", None)
    return merged


def save_wallpaper_config(wallpaper: Dict):
    """保存壁纸配置到配置文件（清理旧字段后写入）。"""
    wallpaper = {**wallpaper}
    wallpaper.pop("cache_ttl", None)
    service = getattr(globals, "service", None)
    if service is None or getattr(service, "configuration_service", None) is None:
        logger.warning("[壁纸] 配置服务尚未初始化，壁纸配置未保存")
        return
    service.configuration_service.update_config({"wallpaper": wallpaper})


def resolve_wallpaper_target(cfg: Optional[Dict] = None) -> str:
    """根据壁纸配置解析出最终要请求的目标 URL / 本地引用。"""
    wp = cfg or get_wallpaper_config()
    source_type = wp.get("source_type", "api")

    if source_type == "upload":
        filename = wp.get("upload_filename", "")
        if filename:
            return f"local:{filename}"
        source_type = "api"

    if source_type == "history":
        filename = wp.get("history_filename", "")
        if filename:
            return f"local:{filename}"
        source_type = "api"

    if source_type == "url":
        custom_url = (wp.get("custom_url", "") or "").strip()
        if custom_url:
            return custom_url
        source_type = "api"

    if source_type == "api":
        api_id = wp.get("api_source_id", "loliapi_acg_pc")
        for source in WALLPAPER_API_SOURCES:
            if source["id"] == api_id:
                return source["url"]
        return "https://www.loliapi.com/acg/pc/"

    return "https://www.loliapi.com/acg/pc/"


def is_valid_image(data: bytes) -> bool:
    """校验数据是否为有效图片。"""
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


def _compute_source_key(source_type: str, source_id: str, source_url: str) -> Optional[str]:
    """给在线源算一个稳定的 key，用于匹配「当前源最近一次预取的图」。"""
    if source_type == "api":
        return f"api:{source_id or ''}"
    if source_type == "url":
        url = (source_url or "").strip()
        return f"url:{hashlib.md5(url.encode()).hexdigest()}" if url else None
    return None


def _source_key_for_config(cfg: Dict) -> Optional[str]:
    st = cfg.get("source_type")
    if st == "api":
        return _compute_source_key("api", cfg.get("api_source_id", ""), "")
    if st == "url":
        return _compute_source_key("url", "", (cfg.get("custom_url", "") or "").strip())
    return None


def _ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    if "bmp" in ct:
        return ".bmp"
    return ".jpg"


def content_type_for_filename(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".bmp": "image/bmp",
    }.get(ext, "image/jpeg")


# ── 图库索引 ──────────────────────────────────────────────

def _load_library() -> List[Dict]:
    """读取 library.json，并对目录中遗留的未索引文件回填为 upload。"""
    _ensure_wallpaper_dir()
    entries: List[Dict] = []
    if os.path.exists(LIBRARY_INDEX_PATH):
        try:
            with open(LIBRARY_INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                entries = [e for e in data if isinstance(e, dict)]
        except Exception:
            logger.warning("[壁纸] 图库索引读取失败，将重建")
            entries = []

    indexed = {e.get("filename") for e in entries}
    changed = False
    try:
        files = os.listdir(WALLPAPER_DIR)
    except FileNotFoundError:
        files = []
    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in ALLOWED_EXTENSIONS or fname in indexed:
            continue
        filepath = os.path.join(WALLPAPER_DIR, fname)
        try:
            size = os.path.getsize(filepath)
            mtime = os.path.getmtime(filepath)
        except OSError:
            continue
        entries.append({
            "filename": fname,
            "size": size,
            "origin": "upload",
            "source_type": "upload",
            "source_id": "",
            "source_url": "",
            "source_key": None,
            "created_at": mtime,
        })
        changed = True

    if changed:
        _save_library(entries)
    return entries


def _save_library(entries: List[Dict]):
    _ensure_wallpaper_dir()
    try:
        tmp = LIBRARY_INDEX_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, LIBRARY_INDEX_PATH)
    except Exception as e:
        logger.warning(f"[壁纸] 图库索引写入失败: {e}")


def list_uploads() -> List[Dict]:
    """手动上传的壁纸列表（新→旧）。"""
    items = [
        {
            "filename": e.get("filename"),
            "size": e.get("size", 0),
            "created_at": e.get("created_at", 0),
        }
        for e in _load_library()
        if e.get("origin") == "upload"
    ]
    items.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    return items


def list_history() -> List[Dict]:
    """自动收录的历史壁纸列表（新→旧）。"""
    items = [
        {
            "filename": e.get("filename"),
            "size": e.get("size", 0),
            "created_at": e.get("created_at", 0),
            "source_type": e.get("source_type", ""),
            "source_id": e.get("source_id", ""),
            "source_url": e.get("source_url", ""),
        }
        for e in _load_library()
        if e.get("origin") == "auto"
    ]
    items.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    return items


def find_latest_history_for_source(cfg: Optional[Dict] = None, library: Optional[List[Dict]] = None) -> Optional[Dict]:
    """查找当前在线源最近一次预取好的历史图（即「就绪图」）。"""
    wp = cfg or get_wallpaper_config()
    key = _source_key_for_config(wp)
    if key is None:
        return None
    entries = library if library is not None else _load_library()
    matches = [
        e for e in entries
        if e.get("origin") == "auto" and e.get("source_key") == key
    ]
    if not matches:
        return None
    matches.sort(key=lambda e: e.get("created_at", 0), reverse=True)
    return matches[0]


def _prune_library(library: List[Dict]) -> List[Dict]:
    """限制历史图数量，超出 HISTORY_LIMIT 时清理最旧的（保护当前引用与当前就绪图）。"""
    auto = [e for e in library if e.get("origin") == "auto"]
    if len(auto) <= HISTORY_LIMIT:
        return library

    cfg = get_wallpaper_config()
    protected = set()
    if cfg.get("upload_filename"):
        protected.add(cfg["upload_filename"])
    if cfg.get("history_filename"):
        protected.add(cfg["history_filename"])
    latest = find_latest_history_for_source(cfg, library=library)
    if latest:
        protected.add(latest.get("filename"))

    auto_sorted = sorted(auto, key=lambda e: e.get("created_at", 0))
    removable = [e for e in auto_sorted if e.get("filename") not in protected]
    to_remove = removable[: max(0, len(auto) - HISTORY_LIMIT)]
    remove_names = {e.get("filename") for e in to_remove}
    for name in remove_names:
        filepath = os.path.join(WALLPAPER_DIR, name)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass
    return [e for e in library if e.get("filename") not in remove_names]


def record_history(
    content: bytes,
    source_type: str,
    source_id: str,
    source_url: str,
    content_type: str,
) -> Optional[str]:
    """把一张在线壁纸收录进历史图库（内容 md5 去重），返回文件名。"""
    if not content or not is_valid_image(content):
        return None
    _ensure_wallpaper_dir()

    md5 = hashlib.md5(content).hexdigest()
    library = _load_library()
    for e in library:
        if e.get("origin") == "auto" and e.get("content_md5") == md5:
            # 内容去重：刷新来源信息与时间，保证「最近使用」排序与当前源就绪图正确
            e["source_type"] = source_type
            e["source_id"] = source_id
            e["source_url"] = source_url
            e["source_key"] = _compute_source_key(source_type, source_id, source_url)
            e["created_at"] = time.time()
            _save_library(library)
            return e.get("filename")

    ext = _ext_from_content_type(content_type)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(WALLPAPER_DIR, filename)
    try:
        with open(filepath, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.warning(f"[壁纸] 历史图写入失败: {e}")
        return None

    library.append({
        "filename": filename,
        "size": len(content),
        "origin": "auto",
        "source_type": source_type,
        "source_id": source_id,
        "source_url": source_url,
        "source_key": _compute_source_key(source_type, source_id, source_url),
        "content_md5": md5,
        "created_at": time.time(),
    })
    library = _prune_library(library)
    _save_library(library)
    return filename


def remove_library_entry(filename: str, origin: str) -> bool:
    """删除图库中某个文件（文件 + 索引）。"""
    _ensure_wallpaper_dir()
    filepath = os.path.join(WALLPAPER_DIR, filename)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        return False

    library = _load_library()
    library = [e for e in library if not (e.get("filename") == filename and e.get("origin") == origin)]
    _save_library(library)
    return True


def read_local_image(filename: str) -> Optional[Tuple[bytes, str]]:
    """读取本地图库图片，返回 (内容, content_type)。"""
    filepath = os.path.join(WALLPAPER_DIR, filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f:
            content = f.read()
    except OSError:
        return None
    if not content:
        return None
    return content, content_type_for_filename(filename)


# ── 后台预取 ──────────────────────────────────────────────

async def _download_online(url: str) -> Optional[Tuple[bytes, str]]:
    """下载在线壁纸并校验，返回 (内容, content_type)。"""
    if not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        logger.warning(f"[壁纸] 预取请求失败: {e}")
        return None

    if resp.status_code == 200 and is_valid_image(resp.content):
        return resp.content, resp.headers.get("content-type", "image/jpeg")
    return None


async def prefetch_once() -> bool:
    """预取一次当前源。本地图无需预取，直接视为就绪。"""
    cfg = get_wallpaper_config()
    target = resolve_wallpaper_target(cfg)

    if target.startswith("local:"):
        return True

    downloaded = await _download_online(target)
    if not downloaded:
        logger.warning("[壁纸] 预取失败：壁纸源返回无效数据")
        return False

    content, content_type = downloaded
    st = cfg.get("source_type", "api")
    source_id = cfg.get("api_source_id", "") if st == "api" else ""
    source_url = target if st == "url" else ""
    filename = record_history(content, st, source_id, source_url, content_type)
    if filename:
        logger.info(f"[壁纸] 后台预取完成并收录历史: {filename}")
        return True
    return False


async def wallpaper_prefetch_loop():
    """后台预取循环：启动即预取一次，之后按 refresh_interval 定时预取；0 = 停止下载。"""
    logger.info("[壁纸] 后台预取循环已启动")
    while True:
        cfg = get_wallpaper_config()
        try:
            interval = int(cfg.get("refresh_interval", 60))
        except (TypeError, ValueError):
            interval = 60

        if interval <= 0:
            # 0/负值 = 停止后台下载：仅等待配置变更后重新评估
            try:
                await _prefetch_wake.wait()
            finally:
                _prefetch_wake.clear()
            continue

        interval = max(interval, 10)
        try:
            await prefetch_once()
        except Exception as e:
            logger.warning(f"[壁纸] 预取异常: {e}")

        try:
            await asyncio.wait_for(_prefetch_wake.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        finally:
            _prefetch_wake.clear()


def notify_wallpaper_config_changed():
    """配置变更后调用：唤醒预取循环，立即按新配置预取一次。"""
    try:
        _prefetch_wake.set()
    except RuntimeError:
        pass
