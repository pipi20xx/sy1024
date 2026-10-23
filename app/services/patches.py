# app/services/patches.py
"""统一的元数据分层读取 + Patches 合并层。

背景
----
引入 patches 之后，元数据的读取优先级变成：

    override 主 JSON  >  远程 TMDB
    → 最后叠加 patches/<同名 JSON>（字段级锁定，优先级最高）

注意：patches 层只覆盖本服务自己维护的 override 数据；primary cache
（StrmAssistant 的刮削缓存）不属于本服务的元数据，不在读取链路里。

模拟器（app/routers/tmdb_proxy.py）、详情页（app/services/editor/details.py）、
文件监控（app/services/file_watcher.py）此前各自实现了一遍读取与合并逻辑，
已经出现语义漂移（例如剧集组模式下季 patch 被绕过、模拟器完全不读 primary cache）。
本模块把「按层读取 + 合并 patch」收敛到一处，供上述模块逐步复用。

约定
----
* patches 只覆盖、不新增层级：合并是深合并，list 类型的值整体替换。
* 本地图片（images/*.jpg）由调用方在 patch 之后注入，即「本地图片 > patch」。
* JSON 按 (路径, mtime_ns, size) 缓存原文，每次返回新解析的对象，避免调用方
  深合并时污染缓存；目录列举按目录 mtime 缓存，减少网络共享（SMB/NFS）上的 stat。
"""

from __future__ import annotations

import json
import os
import stat
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from ..common import MAIN_JSON_FILENAMES, deep_merge_dict
from ..logger import log_audit

# item_type（模拟器/接口语义）→ 元数据目录名（磁盘布局）
ITEM_TYPE_TO_DIR_KEY: Dict[str, str] = {
    "movie": "tmdb-movies2",
    "tv": "tmdb-tv",
    "season": "tmdb-tv",
    "episode": "tmdb-tv",
}

# 主 JSON 文件名（季/集是动态文件名，见 resolve_json_filename）
MAIN_FILENAMES: Dict[str, str] = {
    "movie": MAIN_JSON_FILENAMES["tmdb-movies2"],
    "tv": MAIN_JSON_FILENAMES["tmdb-tv"],
}

_JSON_CACHE_MAX = 256
_JSON_CACHE_MAX_CHARS = 64 * 1024 * 1024   # 缓存总量上限（约 64MB），避免大库吃满内存
_JSON_MAX_ITEM_CHARS = 4 * 1024 * 1024     # 单个文件超过 4MB 不缓存
_DIR_CACHE_MAX = 512

_json_text_cache: "OrderedDict[Tuple[str, int, int], str]" = OrderedDict()
_json_cache_chars = 0
_dir_cache: "OrderedDict[Tuple[str, int], frozenset]" = OrderedDict()
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# 基础缓存
# ---------------------------------------------------------------------------

def _json_cache_get(key):
    with _cache_lock:
        text = _json_text_cache.get(key)
        if text is not None:
            _json_text_cache.move_to_end(key)
        return text


def _json_cache_put(key, text: str) -> None:
    global _json_cache_chars
    if len(text) > _JSON_MAX_ITEM_CHARS:
        return
    with _cache_lock:
        old = _json_text_cache.pop(key, None)
        if old is not None:
            _json_cache_chars = max(0, _json_cache_chars - len(old))
        _json_text_cache[key] = text
        _json_cache_chars += len(text)
        while _json_text_cache and (
            len(_json_text_cache) > _JSON_CACHE_MAX or _json_cache_chars > _JSON_CACHE_MAX_CHARS
        ):
            _, evicted = _json_text_cache.popitem(last=False)
            _json_cache_chars = max(0, _json_cache_chars - len(evicted))


def _dir_cache_get(key):
    with _cache_lock:
        names = _dir_cache.get(key)
        if names is not None:
            _dir_cache.move_to_end(key)
        return names


def _dir_cache_put(key, names: frozenset) -> None:
    with _cache_lock:
        _dir_cache[key] = names
        _dir_cache.move_to_end(key)
        while len(_dir_cache) > _DIR_CACHE_MAX:
            _dir_cache.popitem(last=False)


def clear_cache() -> None:
    """清空所有缓存（测试或配置变更后使用）。"""
    global _json_cache_chars
    with _cache_lock:
        _json_text_cache.clear()
        _dir_cache.clear()
        _json_cache_chars = 0


def invalidate(path: Optional[str]) -> None:
    """让某个文件的 JSON 缓存与父目录的列举缓存失效。"""
    global _json_cache_chars
    if not path:
        return
    abs_path = os.path.abspath(path)
    parent = os.path.abspath(os.path.dirname(path))
    with _cache_lock:
        for key in [k for k in _json_text_cache if k[0] == abs_path]:
            _json_cache_chars = max(0, _json_cache_chars - len(_json_text_cache.pop(key)))
        for key in [k for k in _dir_cache if k[0] == parent]:
            _dir_cache.pop(key, None)


def read_json(path: Optional[str]) -> Optional[Any]:
    """读取 JSON 文件（带 mtime 缓存）。文件不存在或解析失败返回 None。

    返回的是每次重新解析的对象，调用方可以安全地就地修改。
    """
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None

    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    text = _json_cache_get(key)
    if text is None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            log_audit("缓存", "失败", f"读取 JSON 失败 {path}: {e}", level="WARN")
            return None
        _json_cache_put(key, text)

    try:
        return json.loads(text)
    except ValueError as e:
        log_audit("缓存", "失败", f"解析 JSON 失败 {path}: {e}", level="WARN")
        return None


def list_dir(path: Optional[str]) -> frozenset:
    """列举目录内容（带目录 mtime 缓存）。目录不存在返回空集合。"""
    if not path:
        return frozenset()
    try:
        st = os.stat(path)
    except OSError:
        return frozenset()
    if not stat.S_ISDIR(st.st_mode):
        return frozenset()

    key = (os.path.abspath(path), st.st_mtime_ns)
    names = _dir_cache_get(key)
    if names is None:
        try:
            names = frozenset(os.listdir(path))
        except OSError:
            return frozenset()
        _dir_cache_put(key, names)
    return names


def write_json(path: str, data: Any) -> None:
    """原子写入 JSON（先写临时文件再替换），并让相关缓存失效。"""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # 某些网络文件系统不支持 fsync，忽略即可（os.replace 仍是原子的）
            pass
    os.replace(tmp_path, path)
    invalidate(path)


# ---------------------------------------------------------------------------
# 文件名 / 路径解析
# ---------------------------------------------------------------------------

def dir_key_for(item_type: str) -> str:
    """item_type → 磁盘目录名，未知类型直接抛错，避免静默写错位置。"""
    try:
        return ITEM_TYPE_TO_DIR_KEY[item_type]
    except KeyError:
        raise ValueError(f"不支持的元数据类型: {item_type}")


def resolve_json_filename(
    item_type: str,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> str:
    """根据类型（和季/集号）解析出磁盘上的 JSON 文件名。"""
    if item_type in MAIN_FILENAMES:
        return MAIN_FILENAMES[item_type]
    if item_type == "season":
        if season_number is None:
            raise ValueError("读取季元数据需要季号")
        return f"season-{int(season_number)}.json"
    if item_type == "episode":
        if season_number is None or episode_number is None:
            raise ValueError("读取集元数据需要季号和集号")
        return f"season-{int(season_number)}-episode-{int(episode_number)}.json"
    raise ValueError(f"不支持的元数据类型: {item_type}")


def item_dir(base_path: Optional[str], item_type: str, tmdb_id: Any) -> Optional[str]:
    if not base_path:
        return None
    return os.path.join(base_path, dir_key_for(item_type), str(tmdb_id))


def patch_file_path(
    item_type: str,
    tmdb_id: Any,
    filename: str,
    override_path: Optional[str],
) -> Optional[str]:
    if not override_path:
        return None
    return os.path.join(override_path, dir_key_for(item_type), str(tmdb_id), "patches", filename)


# ---------------------------------------------------------------------------
# Patch 读取与合并
# ---------------------------------------------------------------------------

def load_patch(
    item_type: str,
    tmdb_id: Any,
    filename: str,
    override_path: Optional[str],
) -> Optional[Dict[str, Any]]:
    """读取 patches/<filename>；不存在、非 dict 或为空时返回 None。"""
    path = patch_file_path(item_type, tmdb_id, filename, override_path)
    data = read_json(path)
    if isinstance(data, dict) and data:
        return data
    return None


def apply_patch(data: Any, patch: Optional[Dict[str, Any]]) -> bool:
    """把 patch 深合并进 data，返回是否真的合并了内容。"""
    if isinstance(data, dict) and isinstance(patch, dict) and patch:
        deep_merge_dict(data, patch)
        return True
    return False


def apply_patch_for_item(
    item_type: str,
    tmdb_id: Any,
    filename: str,
    data: Any,
    override_path: Optional[str],
) -> bool:
    """按 item_type/tmdb_id/filename 找到 patch 并合并进 data。"""
    return apply_patch(data, load_patch(item_type, tmdb_id, filename, override_path))


def load_metadata(
    item_type: str,
    tmdb_id: Any,
    filename: str,
    override_path: Optional[str],
    primary_path: Optional[str] = None,
    with_patch: bool = True,
) -> Tuple[Optional[Dict[str, Any]], str, bool]:
    """读取 override 主 JSON，并叠加 patch。

    primary_path 参数仅为兼容保留，模拟器不读取主缓存
    （primary cache 属于 StrmAssistant 的刮削缓存，不是本服务的元数据）。

    返回 (data, source, patched)：
      * source: "LOCAL"（override）/ "NONE"
      * patched: 是否合并了 patch
    """
    dir_key = dir_key_for(item_type)
    data: Optional[Dict[str, Any]] = None
    source = "NONE"

    if override_path:
        candidate = os.path.join(override_path, dir_key, str(tmdb_id), filename)
        loaded = read_json(candidate)
        if isinstance(loaded, dict):
            data, source = loaded, "LOCAL"

    patched = False
    if data is not None and with_patch:
        patched = apply_patch_for_item(item_type, tmdb_id, filename, data, override_path)

    return data, source, patched


def load_patch_only(
    item_type: str,
    tmdb_id: Any,
    filename: str,
    override_path: Optional[str],
) -> Optional[Dict[str, Any]]:
    """只有 patch、没有主 JSON 时的兜底（例如「仅锁定名称」的项目）。

    电影/剧集会补一个 id 字段，避免客户端拿到没有主键的稀疏对象。
    """
    patch = load_patch(item_type, tmdb_id, filename, override_path)
    if not patch:
        return None
    data = dict(patch)
    if item_type in ("movie", "tv") and "id" not in data:
        try:
            data["id"] = int(tmdb_id)
        except (TypeError, ValueError):
            pass
    return data


def sync_patch_fields(json_path: str, updated_data: Dict[str, Any]) -> bool:
    """编辑主 JSON 后，同步更新 patch 中已被锁定的字段。

    只更新 patch 中已存在的 key，不会向 patch 新增字段；返回是否发生写入。
    """
    if not json_path or not isinstance(updated_data, dict):
        return False
    patch_path = os.path.join(
        os.path.dirname(json_path), "patches", os.path.basename(json_path)
    )
    patch_data = read_json(patch_path)
    if not isinstance(patch_data, dict) or not patch_data:
        return False

    changed = False
    for key, value in updated_data.items():
        if key in patch_data:
            patch_data[key] = value
            changed = True

    if changed:
        write_json(patch_path, patch_data)
    return changed
