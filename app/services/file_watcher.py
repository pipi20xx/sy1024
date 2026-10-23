"""
实时文件监控服务。
使用 watchdog 的 PollingObserver（兼容 Docker bind mount）监控
Primary 和 Override 缓存目录的 JSON 文件变化，
自动触发单个项目的重新扫描并广播 WebSocket 通知。
"""

import os
import json
import time
import asyncio
import threading
from typing import Dict, Any, Set, Optional, List, Tuple
from datetime import datetime

from ..common import SOURCE_PRIMARY, SOURCE_OVERRIDE, TYPE_DISPLAY_NAMES, MAIN_JSON_FILENAMES
from ..logger import log_audit
from ..websocket_manager import manager

# 优雅导入 watchdog —— 未安装时服务降级（不崩溃）
try:
    from watchdog.observers.polling import PollingObserver
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    PollingObserver = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore  # 降级为 plain object


class _CacheFileEventHandler(FileSystemEventHandler):  # type: ignore[misc]
    """watchdog 事件处理器：仅关注 .json 文件的变化。"""

    def __init__(self, watcher: "FileWatcherService"):
        self._watcher = watcher

    # ---- watchdog 通过 dispatch 分发事件 ----
    def on_created(self, event):  # type: ignore[override]
        if not event.is_directory and event.src_path.endswith('.json'):
            self._watcher._on_file_changed(event.src_path, "created")

    def on_modified(self, event):  # type: ignore[override]
        if not event.is_directory and event.src_path.endswith('.json'):
            self._watcher._on_file_changed(event.src_path, "modified")

    def on_deleted(self, event):  # type: ignore[override]
        if not event.is_directory and event.src_path.endswith('.json'):
            self._watcher._on_file_changed(event.src_path, "deleted")

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        dest = getattr(event, 'dest_path', '')
        if dest.endswith('.json'):
            self._watcher._on_file_changed(dest, "moved")
        if event.src_path.endswith('.json'):
            self._watcher._on_file_changed(event.src_path, "moved")


# 需要忽略的临时文件前缀/后缀
_IGNORE_PREFIXES = ('.~', '~$', '.#', '#')
_IGNORE_SUFFIXES = ('.tmp', '.bak', '.swp', '.temp')


def _should_ignore(path: str) -> bool:
    """检查文件是否为临时/编辑器中间文件，这些文件不应触发重扫。"""
    basename = os.path.basename(path)
    if not basename.endswith('.json'):
        return True
    return (any(basename.startswith(p) for p in _IGNORE_PREFIXES) or
            any(basename.endswith(s) for s in _IGNORE_SUFFIXES))


class FileWatcherService:
    """
    实时文件监控服务。

    特性：
    - 使用 PollingObserver（默认 5s 间隔，可配置）兼容 Docker bind mount 场景
    - 防抖 3 秒：短时间内多次变更合并为一次重扫
    - 扫描进行中自动跳过，避免全量扫描期间产生大量重扫
    - 变更后通过 WebSocket 广播通知前端
    - 事件去重：同一文件的连续 modified 事件在防抖窗口内只处理一次
    """

    DEBOUNCE_SECONDS = 3.0  # 防抖延迟
    DEFAULT_POLL_INTERVAL = 5  # 默认轮询间隔（秒）

    def __init__(self, configuration_service, scanner_service):
        self.configuration_service = configuration_service
        self.scanner_service = scanner_service
        self._observer: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_lock = threading.Lock()
        self._pending_changes: Set[Tuple[str, str]] = set()
        self._recent_paths: Dict[str, float] = {}  # 路径 -> 最近处理时间戳（去重用）
        self._is_running = False
        self._watched_paths: List[str] = []

    # ---- 状态查询 ----

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def watched_paths(self) -> List[str]:
        return list(self._watched_paths)

    def get_status(self) -> Dict[str, Any]:
        """返回当前监控状态。"""
        return {
            "enabled": self._is_running,
            "watched_paths": list(self._watched_paths),
        }

    # ---- 生命周期 ----

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        """设置主事件循环引用，用于从 watchdog 线程调度协程。"""
        self._loop = loop

    def start(self):
        """启动文件监控。"""
        if self._is_running:
            return

        if not _WATCHDOG_AVAILABLE:
            log_audit("文件监控", "失败", "watchdog 库未安装，请执行 pip install watchdog", level="ERROR")
            return

        if not self._loop:
            log_audit("文件监控", "跳过", "事件循环未设置，无法启动监控", level="WARN")
            return

        primary_path = self.configuration_service.get_cache_path_for_source(SOURCE_PRIMARY)
        override_path = self.configuration_service.get_cache_path_for_source(SOURCE_OVERRIDE)

        paths_to_watch: List[str] = []
        if primary_path and os.path.isdir(primary_path):
            paths_to_watch.append(primary_path)
        if override_path and os.path.isdir(override_path):
            paths_to_watch.append(override_path)

        if not paths_to_watch:
            log_audit("文件监控", "跳过", "缓存路径未配置或目录不存在，跳过启动", level="WARN")
            return

        self._watched_paths = paths_to_watch
        poll_interval = self.configuration_service.get(
            "file_watcher_poll_interval", self.DEFAULT_POLL_INTERVAL
        )
        self._observer = PollingObserver(timeout=poll_interval)
        handler = _CacheFileEventHandler(self)

        for path in paths_to_watch:
            self._observer.schedule(handler, path, recursive=True)

        self._observer.start()  # daemon thread
        self._is_running = True
        log_audit(
            "文件监控", "启动",
            f"已开始监控 {len(paths_to_watch)} 个目录: {', '.join(paths_to_watch)}"
        )

    def stop(self):
        """停止文件监控。"""
        if not self._is_running:
            return

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()
                self._debounce_timer = None
            self._pending_changes.clear()
            self._recent_paths.clear()

        self._is_running = False
        self._watched_paths = []
        log_audit("文件监控", "停止", "文件监控已停止")

    # ---- 事件处理（由 watchdog 线程调用）----

    def _on_file_changed(self, file_path: str, event_type: str):
        """当检测到文件变化时（由 watchdog 线程调用）。"""
        # 全量扫描进行中时跳过，避免海量重扫
        if self.scanner_service.scan_progress.get("status") == "scanning":
            return

        # 过滤临时文件
        if _should_ignore(file_path):
            return

        result = self._parse_path(file_path)
        if not result:
            return

        data_type_key, folder_id = result
        now = time.time()
        with self._debounce_lock:
            # 事件去重：同一路径在防抖窗口内的连续事件只处理一次
            last_seen = self._recent_paths.get(file_path, 0)
            if now - last_seen < self.DEBOUNCE_SECONDS:
                return
            self._recent_paths[file_path] = now

            self._pending_changes.add((data_type_key, folder_id))
            # 重置防抖定时器
            if self._debounce_timer:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(
                self.DEBOUNCE_SECONDS, self._process_pending_changes
            )
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _process_pending_changes(self):
        """防抖延迟到期后，批量处理所有待处理的变更。"""
        with self._debounce_lock:
            if not self._pending_changes:
                return
            changes = list(self._pending_changes)
            self._pending_changes.clear()
            self._debounce_timer = None

            # 清理过期的去重记录，防止 _recent_paths 无限增长
            now = time.time()
            expired = [p for p, t in self._recent_paths.items()
                       if now - t > self.DEBOUNCE_SECONDS * 3]
            for p in expired:
                del self._recent_paths[p]

        # 再次检查扫描状态
        if self.scanner_service.scan_progress.get("status") == "scanning":
            log_audit("文件监控", "跳过", "全量扫描进行中，跳过文件变更处理", level="DEBUG")
            return

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._rescan_items(changes), self._loop
            )

    async def _rescan_items(self, changes: List[Tuple[str, str]]):
        """重新扫描变更的项目并广播 WebSocket 通知（在主事件循环中执行）。"""
        from ..database import ItemsSessionLocal
        from sqlalchemy import delete as sql_delete
        from ..models import Item

        scan_time = datetime.now().isoformat()
        rescanned: List[Dict[str, str]] = []

        for data_type_key, folder_id in changes:
            try:
                if self._item_exists_on_disk(data_type_key, folder_id):
                    async with ItemsSessionLocal() as session:
                        async with session.begin():
                            await self.scanner_service._scan_and_insert_item(
                                session, data_type_key, folder_id, scan_time
                            )
                    rescanned.append({
                        "item_type": data_type_key,
                        "folder_id": folder_id,
                    })
                    log_audit("文件监控", "更新", f"已重新扫描 {data_type_key}/{folder_id}")

                    # 自动锁定名称（仅对未锁定的项目）
                    if self.configuration_service.get("file_watcher_auto_lock_name", False):
                        if not self._is_name_locked(data_type_key, folder_id):
                            try:
                                from .. import globals
                                if globals.service and hasattr(globals.service, 'editor_service'):
                                    await globals.service.editor_service.lock_item_name(
                                        data_type_key, folder_id
                                    )
                                    log_audit("文件监控", "锁定", f"已自动锁定名称 {data_type_key}/{folder_id}")
                            except Exception as e:
                                log_audit("文件监控", "锁定失败", f"自动锁定 {data_type_key}/{folder_id} 失败: {e}", level="WARN")
                else:
                    # 项目已从磁盘删除，从数据库中移除
                    async with ItemsSessionLocal() as session:
                        async with session.begin():
                            await session.execute(
                                sql_delete(Item).where(
                                    Item.item_type == data_type_key,
                                    Item.folder_id == folder_id
                                )
                            )
                    rescanned.append({
                        "item_type": data_type_key,
                        "folder_id": folder_id,
                    })
                    log_audit("文件监控", "删除", f"已从数据库删除 {data_type_key}/{folder_id}")
            except Exception as e:
                log_audit(
                    "文件监控", "失败",
                    f"处理 {data_type_key}/{folder_id} 失败: {e}",
                    level="ERROR"
                )

        if rescanned:
            await manager.broadcast({
                "type": "file_watcher",
                "data": {
                    "action": "rescanned",
                    "items": rescanned,
                    "message": f"实时监控已更新 {len(rescanned)} 个项目",
                }
            })

    def _item_exists_on_disk(self, data_type_key: str, folder_id: str) -> bool:
        """检查项目的主 JSON 文件是否仍然存在于磁盘上。"""
        main_json_file = MAIN_JSON_FILENAMES.get(data_type_key)
        if not main_json_file:
            return False

        for source in (SOURCE_OVERRIDE, SOURCE_PRIMARY):
            cache_path = self.configuration_service.get_cache_path_for_source(source)
            if cache_path and os.path.isfile(
                os.path.join(cache_path, data_type_key, folder_id, main_json_file)
            ):
                return True
        return False

    def _is_name_locked(self, data_type_key: str, folder_id: str) -> bool:
        """检查项目名称是否已锁定（patches 文件中是否已有名称字段）。"""
        override_path = self.configuration_service.get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False

        main_json_file = MAIN_JSON_FILENAMES.get(data_type_key)
        if not main_json_file:
            return False

        name_key = "title" if data_type_key == "tmdb-movies2" else "name"
        patch_file_path = os.path.join(override_path, data_type_key, folder_id, "patches", main_json_file)

        if not os.path.isfile(patch_file_path):
            return False

        try:
            with open(patch_file_path, "r", encoding="utf-8") as f:
                patch_data = json.load(f)
            return name_key in patch_data
        except Exception:
            return False

    # ---- 路径解析 ----

    def _parse_path(self, file_path: str) -> Optional[Tuple[str, str]]:
        """
        从文件路径中解析出 (data_type_key, folder_id)。

        期望的路径结构:
          {cache_path}/{data_type_key}/{folder_id}/.../*.json
        例如:
          /data/primary/tmdb-tv/12345/series.json
          /data/override/tmdb-movies2/67890/patches/all.json
        """
        normalized = os.path.normpath(file_path)

        for cache_path in self._watched_paths:
            cache_normalized = os.path.normpath(cache_path)
            if normalized.startswith(cache_normalized + os.sep):
                rel_path = os.path.relpath(normalized, cache_normalized)
                parts = rel_path.split(os.sep)
                if len(parts) >= 2 and parts[0] in TYPE_DISPLAY_NAMES and parts[0] != "tmdb-collections":
                    return (parts[0], parts[1])
                break

        return None
