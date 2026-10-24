from __future__ import annotations

import asyncio
import binascii
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx
import aiofiles
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from .. import globals
from ..logger import log_audit
from ..services import patches as patch_store

router = APIRouter(tags=["TMDB 代理"])

# TMDB Mock API —— 把 Emby/Jellyfin 的 TMDB 请求转成本地数据。
#
# 数据优先级（与 app/services/patches.py 保持一致）：
#   1. override 主 JSON（LOCAL）
#   2. 远程 TMDB（REMOTE，受 tmdb_proxy_fallback 控制）
#   3. 只有 patches 没有主 JSON 时，用 patch 兜底（PATCH）
#   然后叠加 patches/<同名 JSON>（字段级锁定，最高优先级）
#   → 剧集组（EPG）结构变换：EPG 拥有 seasons/episodes 结构与虚拟编号
#   → 本地图片注入：本地图片 > patch
#   → 图片 URL 改写
#
# 注意：模拟器只认自己维护的 override + patches，不读 primary cache
# （那是 StrmAssistant 的刮削缓存，不属于本服务的元数据）。

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".svg")

_ALLOWED_ITEM_TYPES = frozenset({"movie", "tv", "season", "episode"})
_IMG_TYPE_RE = re.compile(r"^(?:poster|fanart|logo|season-\d+|season-\d+-episode-\d+)$")
_HEX_PATH_RE = re.compile(r"^/([0-9a-fA-F]+)\.jpg$")


# ---------------------------------------------------------------------------
# 配置与日志
# ---------------------------------------------------------------------------

def _config_get(key: str, default: Any = None) -> Any:
    service = getattr(globals, "service", None)
    config = getattr(service, "config", None) if service else None
    if isinstance(config, dict):
        return config.get(key, default)
    return default


def get_override_path() -> str:
    return _config_get("override_cache_path") or "/data/overrides"


def get_primary_path() -> Optional[str]:
    """保留给潜在扩展；模拟器当前不读取 primary cache。"""
    return None


def _base_url(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def log_access(
    request: Request,
    resource_type: str,
    resource_id: str,
    source: str = "REMOTE",
    extra: str = "",
    patched: bool = False,
):
    """记录 TMDB Mock API 的访问日志。

    Args:
        source: LOCAL（本地 override）/ PATCH（仅 patch）/ REMOTE（远程拉取）/ ERROR（出错）
        extra: 额外信息，如语言、搜索关键词等
        patched: 本次响应是否叠加了 patches
    """
    client_host = request.client.host if request.client else "Unknown"
    parts = [f"[TMDB Mock] {request.method} {client_host} | {source} | {resource_type.upper()}: {resource_id}"]
    if extra:
        parts.append(f"| {extra}")
    if patched:
        parts.append("| patches=1")
    log_audit("代理", "处理", " ".join(parts))


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 本地图片路径编解码（hex）
# ---------------------------------------------------------------------------

_image_proxy_client: Optional[httpx.AsyncClient] = None


async def get_image_client() -> httpx.AsyncClient:
    global _image_proxy_client
    if _image_proxy_client is None or _image_proxy_client.is_closed:
        service = getattr(globals, "service", None)
        proxy_url = None
        if service and getattr(service, "configuration_service", None):
            proxy_url = service.configuration_service.get_proxy_url("tmdb")
        _image_proxy_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            proxy=proxy_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
    return _image_proxy_client


def encode_local_path(item_type: str, tmdb_id: str, img_type: str) -> str:
    raw_str = f"{item_type}|{tmdb_id}|{img_type}"
    encoded = binascii.hexlify(raw_str.encode("utf-8")).decode("utf-8")
    return f"/{encoded}.jpg"


def _decode_payload(filename: str) -> Optional[Tuple[str, str, str]]:
    """解码 hex 路径并严格校验，避免未认证的 /tmdb-mock 被用于路径穿越。"""
    actual_filename = filename.rsplit("/", 1)[-1]
    if not actual_filename.endswith(".jpg"):
        return None
    payload = actual_filename[:-4]
    if not payload or len(payload) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", payload):
        return None
    try:
        decoded_str = binascii.unhexlify(payload).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None

    parts = decoded_str.split("|")
    if len(parts) != 3:
        return None
    item_type, tmdb_id, img_type = parts
    if item_type not in _ALLOWED_ITEM_TYPES or not tmdb_id.isdigit():
        return None
    if not _IMG_TYPE_RE.match(img_type):
        return None
    return item_type, tmdb_id, img_type


def _is_local_encoded_path(value: Any) -> bool:
    """判断字符串是否为本服务生成的本地图片路径（/hex.jpg）。"""
    if not isinstance(value, str) or not _HEX_PATH_RE.match(value):
        return False
    return _decode_payload(value) is not None


def decode_local_path(filename: str) -> Optional[str]:
    parts = _decode_payload(filename)
    if not parts:
        return None
    item_type, tmdb_id, img_type = parts

    base_path = get_override_path()
    dir_key = patch_store.dir_key_for(item_type)
    images_dir = os.path.join(base_path, dir_key, tmdb_id, "images")
    names = patch_store.list_dir(images_dir)

    mapping = {
        "poster": ("poster.jpg",),
        "fanart": ("fanart.jpg",),
        "logo": ("clearlogo.png", "logo.png"),
    }
    candidates = mapping.get(img_type, (f"{img_type}.jpg",))

    root = os.path.realpath(base_path)
    for name in candidates:
        if name not in names:
            continue
        path = os.path.realpath(os.path.join(images_dir, name))
        if path == root or path.startswith(root + os.sep):
            return path
    return None


# ---------------------------------------------------------------------------
# 图片 URL 改写
# ---------------------------------------------------------------------------

def _rewrite_image_value(value: str, base_url: str) -> str:
    if not value or not value.lower().endswith(IMAGE_SUFFIXES):
        return value
    # 已经是绝对地址或本服务地址，原样保留
    if value.startswith(("http://", "https://", "//")):
        return value
    if value.startswith("/tmdb-mock/"):
        return value
    # 本服务生成的 /hex.jpg（patch 里可能直接写入）
    if _is_local_encoded_path(value):
        return value
    if value.startswith("/"):
        return f"{base_url}/tmdb-mock/t/p/original{value}"
    return f"{base_url}/tmdb-mock/t/p/original/{value}"


def rewrite_tmdb_urls(data: Union[Dict, List, Any], base_url: str) -> Any:
    """把 TMDB 的图片相对路径改写成本服务的 /tmdb-mock/t/p/ 地址。

    绝对外链（http/https）与本地 hex 路径保持不变；patch 里写外链海报是常见用法。
    """
    if isinstance(data, dict):
        images = data.get("images")
        if isinstance(images, dict):
            if data.get("poster_path") is None:
                posters = images.get("posters") or []
                if posters:
                    data["poster_path"] = posters[0].get("file_path")
            if data.get("backdrop_path") is None:
                backdrops = images.get("backdrops") or []
                if backdrops:
                    data["backdrop_path"] = backdrops[0].get("file_path")
            if data.get("still_path") is None:
                stills = images.get("stills") or []
                if stills:
                    data["still_path"] = stills[0].get("file_path")

        return {
            key: (_rewrite_image_value(value, base_url) if isinstance(value, str) else rewrite_tmdb_urls(value, base_url))
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [rewrite_tmdb_urls(item, base_url) for item in data]
    return data


# ---------------------------------------------------------------------------
# 剧集组（Episode Group）
# ---------------------------------------------------------------------------

async def load_episodegroup(tmdb_id: str) -> Optional[Dict[str, Any]]:
    file_path = os.path.join(get_override_path(), "tmdb-tv", str(tmdb_id), "episodegroup.json")
    data = await asyncio.to_thread(patch_store.read_json, file_path)
    return data if isinstance(data, dict) else None


def apply_episodegroup_to_tv(tv_data: Dict[str, Any], epg_data: Dict[str, Any]) -> None:
    """用剧集组重写 seasons / number_of_seasons。

    注意：EPG 拥有 seasons 结构，因此 series.json 的 patch 若修改了 seasons，
    在这里会被覆盖（其余字段仍然保留 patch 的值）。
    """
    groups = epg_data.get("groups") or []
    if not groups:
        return

    new_seasons = []
    for index, group in enumerate(groups):
        sn = _as_int(group.get("order"))
        if sn is None:
            sn = index
        new_seasons.append({
            "air_date": group.get("air_date", tv_data.get("first_air_date")),
            "episode_count": len(group.get("episodes") or []),
            "id": 100000 + sn,
            "name": group.get("name", f"第 {sn} 季"),
            "overview": group.get("overview", ""),
            "poster_path": group.get("poster_path"),
            "season_number": sn,
        })

    tv_data["seasons"] = new_seasons
    tv_data["number_of_seasons"] = len(new_seasons)
    tv_data["number_of_episodes"] = sum(len(g.get("episodes") or []) for g in groups)


async def apply_episodegroup_to_season(
    tmdb_id: str,
    virtual_sn: int,
    epg_data: Dict[str, Any],
    lang: str,
    proxy_fallback: bool,
) -> Optional[Tuple[Dict[str, Any], bool]]:
    """用剧集组拼出一个「虚拟季」。

    patch 目标使用虚拟季号（即 Emby 请求的季号）：patches/season-{virtual_sn}.json。
    patch 允许覆盖名称/简介/海报等字段，但 episodes 列表与虚拟编号由 EPG 决定。
    """
    groups = epg_data.get("groups") or []
    target_group = next((g for g in groups if _as_int(g.get("order")) == virtual_sn), None)
    if not target_group:
        return None

    season_data: Dict[str, Any] = {
        "air_date": target_group.get("air_date"),
        "name": target_group.get("name"),
        "overview": target_group.get("overview"),
        "id": 100000 + virtual_sn,
        "poster_path": target_group.get("poster_path"),
        "season_number": virtual_sn,
        "episodes": [],
    }

    built_episodes: List[Dict[str, Any]] = []
    for index, ep_ref in enumerate(target_group.get("episodes") or []):
        real_sn = _as_int(ep_ref.get("season_number"))
        real_en = _as_int(ep_ref.get("episode_number"))
        if real_sn is None or real_en is None:
            continue

        order = _as_int(ep_ref.get("order"))
        virtual_en = (order if order is not None else index) + 1

        filename = patch_store.resolve_json_filename("episode", real_sn, real_en)
        ep_data, _source, _patched = await _load_base("episode", tmdb_id, filename)

        if ep_data is None and proxy_fallback:
            ep_data = await _fetch_remote("episode", tmdb_id, lang, real_sn, real_en)
            if ep_data is not None:
                await _apply_patch("episode", tmdb_id, filename, ep_data)

        if not ep_data:
            continue

        await inject_local_images(ep_data, "episode", tmdb_id, forced_sn=real_sn, forced_en=real_en)
        ep_data["episode_number"] = virtual_en
        ep_data["season_number"] = virtual_sn
        built_episodes.append(ep_data)

    patched = await asyncio.to_thread(
        patch_store.apply_patch_for_item,
        "season", tmdb_id, f"season-{virtual_sn}.json", season_data, get_override_path(),
    )

    # EPG 拥有结构：集列表与虚拟编号不被 patch 改写
    season_data["episodes"] = built_episodes
    season_data["season_number"] = virtual_sn

    await inject_local_images(season_data, "season", tmdb_id, forced_sn=virtual_sn)
    return season_data, patched


# ---------------------------------------------------------------------------
# 本地图片注入
# ---------------------------------------------------------------------------

def _inject_local_images_sync(
    data: Dict[str, Any],
    item_type: str,
    tmdb_id: str,
    base_path: str,
    forced_sn: Optional[int] = None,
    forced_en: Optional[int] = None,
) -> None:
    if not isinstance(data, dict):
        return

    dir_key = patch_store.dir_key_for(item_type)
    images_dir = os.path.join(base_path, dir_key, str(tmdb_id), "images")
    names = patch_store.list_dir(images_dir)
    if not names:
        return

    def _encoded(img_type: str) -> str:
        return encode_local_path(item_type, tmdb_id, img_type)

    def _images() -> Dict[str, Any]:
        if not isinstance(data.get("images"), dict):
            data["images"] = {}
        return data["images"]

    def _prepend(section: str, entry: Dict[str, Any]) -> None:
        images = _images()
        bucket = images.get(section)
        if not isinstance(bucket, list):
            bucket = []
            images[section] = bucket
        bucket.insert(0, entry)

    # 只有电影/剧集本身才用 images/poster.jpg、fanart.jpg；
    # 季/集目录共用剧集的 images 目录，套用会拿到「剧集海报」当季/集海报。
    if item_type in ("movie", "tv"):
        if "poster.jpg" in names:
            path = _encoded("poster")
            data["poster_path"] = path
            _prepend("posters", {"file_path": path})

        if "fanart.jpg" in names:
            path = _encoded("fanart")
            data["backdrop_path"] = path
            _prepend("backdrops", {"file_path": path})

        for logo_name in ("clearlogo.png", "logo.png"):
            if logo_name in names:
                _prepend("logos", {"file_path": _encoded("logo")})
                break

    if item_type == "season":
        sn = forced_sn if forced_sn is not None else _as_int(data.get("season_number"))
        if sn is not None and f"season-{sn}.jpg" in names:
            path = _encoded(f"season-{sn}")
            data["poster_path"] = path
            _prepend("posters", {"file_path": path})
    elif item_type == "episode" or (forced_sn is not None and forced_en is not None):
        sn = forced_sn if forced_sn is not None else _as_int(data.get("season_number"))
        en = forced_en if forced_en is not None else _as_int(data.get("episode_number"))
        if sn is not None and en is not None and f"season-{sn}-episode-{en}.jpg" in names:
            path = _encoded(f"season-{sn}-episode-{en}")
            data["still_path"] = path
            _prepend("stills", {"file_path": path})

    seasons = data.get("seasons")
    if isinstance(seasons, list):
        for season in seasons:
            if not isinstance(season, dict):
                continue
            sn = _as_int(season.get("season_number"))
            if sn is not None and f"season-{sn}.jpg" in names:
                season["poster_path"] = _encoded(f"season-{sn}")

    episodes = data.get("episodes")
    if isinstance(episodes, list) and forced_sn is None:
        for ep in episodes:
            if not isinstance(ep, dict):
                continue
            sn = _as_int(ep.get("season_number"))
            en = _as_int(ep.get("episode_number"))
            if sn is None or en is None:
                continue
            if f"season-{sn}-episode-{en}.jpg" not in names:
                continue
            path = _encoded(f"season-{sn}-episode-{en}")
            ep["still_path"] = path
            if not isinstance(ep.get("images"), dict):
                ep["images"] = {}
            stills = ep["images"].get("stills")
            if not isinstance(stills, list):
                stills = []
                ep["images"]["stills"] = stills
            stills.insert(0, {"file_path": path})


async def inject_local_images(
    data: Dict[str, Any],
    item_type: str,
    tmdb_id: str,
    forced_sn: Optional[int] = None,
    forced_en: Optional[int] = None,
    base_path: Optional[str] = None,
) -> None:
    await asyncio.to_thread(
        _inject_local_images_sync,
        data, item_type, str(tmdb_id), base_path or get_override_path(), forced_sn, forced_en,
    )


# ---------------------------------------------------------------------------
# 分层加载
# ---------------------------------------------------------------------------

async def _load_base(item_type: str, tmdb_id: str, filename: str) -> Tuple[Optional[Dict[str, Any]], str, bool]:
    """读取 override 主 JSON，并叠加 patch。

    注意：模拟器只认自己维护的 override + patches，不读 primary cache
    （那是 StrmAssistant 的刮削缓存，不属于本服务的元数据）。
    """
    return await asyncio.to_thread(
        patch_store.load_metadata,
        item_type, tmdb_id, filename, get_override_path(), None,
    )


async def _apply_patch(item_type: str, tmdb_id: str, filename: str, data: Dict[str, Any]) -> bool:
    return await asyncio.to_thread(
        patch_store.apply_patch_for_item,
        item_type, tmdb_id, filename, data, get_override_path(),
    )


async def _fetch_remote(
    item_type: str,
    tmdb_id: str,
    lang: str,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    service = getattr(globals, "service", None)
    if not service or not getattr(service, "tmdb_metadata_service", None):
        return None
    try:
        data = await service.tmdb_metadata_service.fetch_tmdb_data(
            item_type=item_type,
            tmdb_id=tmdb_id,
            lang=lang,
            season_number=season_number,
            episode_number=episode_number,
        )
    except Exception as e:
        log_audit("代理", "失败", f"远程拉取 TMDB 失败 {item_type}/{tmdb_id}: {e}", level="WARN")
        return None
    return data if isinstance(data, dict) else None


def _map_virtual_episode(epg_data: Dict[str, Any], season: Optional[int], episode: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    """把 Emby 传来的（虚拟季, 虚拟集）映射成 TMDB 的真实季集号。"""
    groups = epg_data.get("groups") or []
    target_group = next((g for g in groups if _as_int(g.get("order")) == season), None)
    if not target_group or episode is None:
        return season, episode

    episodes = target_group.get("episodes") or []

    def _virtual_number(item: Dict[str, Any], index: int) -> int:
        order = _as_int(item.get("order"))
        return (order if order is not None else index) + 1

    ep_ref = next(
        (e for index, e in enumerate(episodes) if _virtual_number(e, index) == episode),
        None,
    )
    if ep_ref is None and 1 <= episode <= len(episodes):
        ep_ref = episodes[episode - 1]
    if ep_ref is None:
        return season, episode

    real_sn = _as_int(ep_ref.get("season_number"))
    real_en = _as_int(ep_ref.get("episode_number"))
    if real_sn is None or real_en is None:
        return season, episode
    return real_sn, real_en


async def get_details_auto(
    request: Request,
    item_type: str,
    tmdb_id: str,
    lang: str = "zh-CN",
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> Tuple[Dict[str, Any], str, bool]:
    """返回 (data, source, patched)，source ∈ LOCAL / CACHE / PATCH / REMOTE。"""
    proxy_fallback = bool(_config_get("tmdb_proxy_fallback", True))
    episode_group_mode = bool(_config_get("tmdb_episode_group_mode", False))

    epg_data = None
    if episode_group_mode and item_type in ("tv", "season", "episode"):
        epg_data = await load_episodegroup(tmdb_id)

    real_sn, real_en = season, episode
    if item_type == "episode" and epg_data:
        real_sn, real_en = _map_virtual_episode(epg_data, season, episode)

    if item_type == "season" and epg_data:
        result = await apply_episodegroup_to_season(tmdb_id, season, epg_data, lang, proxy_fallback)
        if result:
            season_data, patched = result
            return rewrite_tmdb_urls(season_data, _base_url(request)), "LOCAL", patched

    filename = patch_store.resolve_json_filename(item_type, real_sn, real_en)
    data, source, patched = await _load_base(item_type, tmdb_id, filename)

    if data is None and proxy_fallback:
        data = await _fetch_remote(item_type, tmdb_id, lang, real_sn, real_en)
        if data is not None:
            source = "REMOTE"
            patched = await _apply_patch(item_type, tmdb_id, filename, data)

    if data is None:
        # 只有 patch、没有主 JSON（例如「仅锁定名称」且未配置远程回退）
        data = await asyncio.to_thread(
            patch_store.load_patch_only, item_type, tmdb_id, filename, get_override_path()
        )
        if data is None:
            raise HTTPException(status_code=404)
        source, patched = "PATCH", True

    if item_type == "tv" and epg_data:
        apply_episodegroup_to_tv(data, epg_data)

    await inject_local_images(data, item_type, tmdb_id, forced_sn=real_sn, forced_en=real_en)

    if item_type == "episode" and (real_sn != season or real_en != episode):
        data["season_number"], data["episode_number"] = season, episode

    return rewrite_tmdb_urls(data, _base_url(request)), source, patched


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _default_language() -> str:
    """无 language 参数时的默认元数据语言（读配置 tmdb_preferred_language）。"""
    return _config_get("tmdb_preferred_language") or "zh-CN"


async def _details_response(
    request: Request,
    item_type: str,
    tmdb_id: str,
    label: str,
    *,
    lang: Optional[str] = None,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> Dict[str, Any]:
    if not lang:
        lang = _default_language()
    try:
        data, source, patched = await get_details_auto(
            request, item_type, tmdb_id, lang=lang, season=season, episode=episode
        )
        log_access(request, item_type, label, source=source, extra=f"lang={lang}", patched=patched)
        return data
    except HTTPException:
        raise
    except Exception as e:
        log_access(request, item_type, label, source="ERROR", extra=str(e))
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/tmdb-mock/3/configuration")
async def tmdb_configuration(request: Request):
    image_base = f"{_base_url(request)}/tmdb-mock/t/p/"
    log_access(request, "configuration", image_base, source="LOCAL")
    return {
        "images": {
            "base_url": image_base,
            "secure_base_url": image_base,
            "backdrop_sizes": ["w300", "w780", "w1280", "original"],
            "logo_sizes": ["w45", "w92", "w154", "w185", "w300", "w500", "original"],
            "poster_sizes": ["w92", "w154", "w185", "w342", "w500", "w780", "original"],
            "profile_sizes": ["w45", "w185", "h632", "original"],
            "still_sizes": ["w92", "w185", "w300", "original"],
        }
    }


def get_cached_tmdb_image_path(size: str, tmdb_path: str) -> Optional[str]:
    """获取 TMDB 图片在本地缓存中的路径，独立存放在 data 目录下。"""
    data_dir = os.environ.get("DATA_PATH", ".")
    cache_base = os.path.join(data_dir, "tmdb_image_cache")
    safe_name = tmdb_path.lstrip('/').replace('/', '_')
    if not safe_name:
        return None
    return os.path.join(cache_base, size, safe_name)


# TMDB 图片下载 in-flight 去重：Emby 刮削时同一图片常被并发请求多次，
# 不加锁会重复下载并交叉写坏同一个缓存文件
_image_download_locks: Dict[str, asyncio.Lock] = {}
_image_download_locks_guard = asyncio.Lock()


@router.get("/tmdb-mock/t/p/{size}/{file_path:path}")
async def get_image(size: str, file_path: str, request: Request):
    file_path = file_path.lstrip('/')
    local_path = decode_local_path(file_path)
    if local_path and os.path.exists(local_path):
        log_access(request, "image-local", file_path, source="LOCAL")
        return FileResponse(
            local_path,
            media_type="image/png" if local_path.lower().endswith(".png") else "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    match = re.search(r't/p/([^/]+)/(.+)$', file_path)
    if match:
        size, file_path = match.group(1), match.group(2)
    tmdb_path = f"/{file_path.lstrip('/')}"

    # 检查 TMDB 图片缓存
    cached_path = get_cached_tmdb_image_path(size, tmdb_path)
    if cached_path and os.path.exists(cached_path):
        log_access(request, "image-cache", tmdb_path, source="CACHE", extra=f"size={size}")
        return FileResponse(
            cached_path,
            media_type="image/png" if tmdb_path.lower().endswith(".png") else "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    tmdb_image_url = f"https://image.tmdb.org/t/p/{size}{tmdb_path}"
    log_access(request, "image-proxy", tmdb_path, source="REMOTE", extra=f"size={size}")

    try:
        client = await get_image_client()

        dl_lock: Optional[asyncio.Lock] = None
        if cached_path:
            async with _image_download_locks_guard:
                dl_lock = _image_download_locks.setdefault(cached_path, asyncio.Lock())

        async def image_stream():
            if dl_lock is not None:
                async with dl_lock:
                    # 排队期间前一个并发请求可能已完成下载并写好缓存
                    if cached_path and os.path.exists(cached_path):
                        async with aiofiles.open(cached_path, 'rb') as f:
                            while True:
                                chunk = await f.read(256 * 1024)
                                if not chunk:
                                    break
                                yield chunk
                        return
                    async for chunk in _download_and_cache():
                        yield chunk
            else:
                async for chunk in _download_and_cache():
                    yield chunk

        async def _download_and_cache():
            cache_file = None
            try:
                if cached_path:
                    os.makedirs(os.path.dirname(cached_path), exist_ok=True)
                    cache_file = await aiofiles.open(cached_path, 'wb')
                async with client.stream('GET', tmdb_image_url) as response:
                    if response.status_code == 200:
                        async for chunk in response.aiter_bytes():
                            if cache_file:
                                await cache_file.write(chunk)
                            yield chunk
                    elif cache_file:
                        await cache_file.close()
                        cache_file = None
                        # 远程返回非 200，删除空缓存文件
                        try:
                            os.remove(cached_path)
                        except OSError:
                            pass
            except Exception:
                # 下载失败时关闭并删除不完整的缓存文件
                if cache_file:
                    await cache_file.close()
                    try:
                        os.remove(cached_path)
                    except OSError:
                        pass
            finally:
                if cache_file:
                    await cache_file.close()
                if dl_lock is not None:
                    async with _image_download_locks_guard:
                        if _image_download_locks.get(cached_path) is dl_lock and not dl_lock.locked():
                            _image_download_locks.pop(cached_path, None)

        return StreamingResponse(
            image_stream(),
            media_type="image/png" if tmdb_path.lower().endswith(".png") else "image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502)


@router.get("/tmdb-mock/3/movie/{movie_id}")
async def get_movie(movie_id: str, request: Request, language: Optional[str] = None):
    return await _details_response(request, "movie", movie_id, movie_id, lang=language)


@router.get("/tmdb-mock/3/tv/{tv_id}")
async def get_tv(tv_id: str, request: Request, language: Optional[str] = None):
    return await _details_response(request, "tv", tv_id, tv_id, lang=language)


@router.get("/tmdb-mock/3/tv/{tv_id}/season/{season_number}")
async def get_tv_season(tv_id: str, season_number: int, request: Request, language: Optional[str] = None):
    return await _details_response(
        request, "season", tv_id, f"{tv_id}-S{season_number}", lang=language, season=season_number
    )


@router.get("/tmdb-mock/3/tv/{tv_id}/season/{season_number}/episode/{episode_number}")
async def get_tv_episode(
    tv_id: str,
    season_number: int,
    episode_number: int,
    request: Request,
    language: Optional[str] = None,
):
    return await _details_response(
        request,
        "episode",
        tv_id,
        f"{tv_id}-S{season_number}E{episode_number}",
        lang=language,
        season=season_number,
        episode=episode_number,
    )


@router.get("/tmdb-mock/3/person/{person_id}")
async def get_person(person_id: str, request: Request, language: Optional[str] = None):
    if not language:
        language = _default_language()
    try:
        # 优先从本地演员库查询
        from ..database import ActorsSessionLocal
        from ..models import Actor
        from sqlalchemy import select

        async with ActorsSessionLocal() as session:
            stmt = select(Actor).where(Actor.tmdb_id == int(person_id))
            result = await session.execute(stmt)
            actor = result.scalar_one_or_none()
            if actor and actor.metadata_json:
                data = json.loads(actor.metadata_json)
                log_access(request, "person", person_id, source="LOCAL", extra=f"lang={language}")
                return rewrite_tmdb_urls(data, _base_url(request))

        # 本地没有，从 TMDB 拉取
        data = await globals.service.tmdb_metadata_service.fetch_tmdb_data(
            item_type="person", tmdb_id=person_id, lang=language
        )
        log_access(request, "person", person_id, source="REMOTE", extra=f"lang={language}")
        return rewrite_tmdb_urls(data, _base_url(request))
    except Exception as e:
        log_access(request, "person", person_id, source="ERROR", extra=str(e))
        raise HTTPException(status_code=404)


@router.get("/tmdb-mock/3/search/movie")
async def search_movie(query: str, request: Request, language: Optional[str] = None, page: int = 1):
    return await _search_response(request, "movie", query, language, page)


@router.get("/tmdb-mock/3/search/tv")
async def search_tv(query: str, request: Request, language: Optional[str] = None, page: int = 1):
    return await _search_response(request, "tv", query, language, page)


@router.get("/tmdb-mock/3/search/multi")
async def search_multi(query: str, request: Request, language: Optional[str] = None, page: int = 1):
    return await _search_response(request, "multi", query, language, page)


async def _search_response(
    request: Request,
    item_type: str,
    query: str,
    language: Optional[str],
    page: int,
):
    if not language:
        language = _default_language()
    try:
        data = await globals.service.tmdb_metadata_service.search_tmdb(
            item_type, query, lang=language, page=page
        )
        log_access(request, f"search-{item_type}", query, source="REMOTE", extra=f"lang={language} page={page}")
        return rewrite_tmdb_urls(data, _base_url(request))
    except Exception as e:
        log_access(request, f"search-{item_type}", query, source="ERROR", extra=str(e))
        raise HTTPException(status_code=502, detail=str(e))
