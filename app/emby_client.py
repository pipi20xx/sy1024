# app/emby_client.py

import os
import httpx
import aiofiles
import asyncio
import random # Add import
import time
from typing import Optional, Dict, List, Tuple
from urllib.parse import urljoin
from collections import OrderedDict

from .common import image_to_base64
from .websocket_manager import manager # Import WS manager
from .logger import log_audit


EMBY_IMAGE_NAMING_RULES = {
    "Movie": { "Primary": "poster", "Backdrop": "fanart", "Banner": "banner", "Logo": "clearlogo", "Art": "clearart", "Thumb": "landscape", "Disc": "disc" },
    "Series": { "Primary": "poster", "Backdrop": "fanart", "Banner": "banner", "Logo": "clearlogo", "Art": "clearart", "Thumb": "landscape", "Disc": "disc" },
    "Season": { "Primary": "season-{season_num}" },
    "Episode": { "Primary": "season-{season_num}-episode-{episode_num}" }
}

def _sanitize_filename_for_emby_download(filename):
    if not filename: return "unknown_item"
    import re
    sanitized = re.sub(r'[\\/*?:\"<>|]', "_", filename)
    sanitized = sanitized.strip(". ")
    if not sanitized: return "sanitized_empty_item"
    return sanitized

class EmbyClient:
    def __init__(self, server_url: str, api_key: str, user_id: str = ""):
        if not server_url or not api_key:
            raise ValueError("Emby server URL and API Key are required.")
        
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.user_id = user_id
        
        # httpx AsyncClient configuration
        # Explicitly set connection limits
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        
        self.client = httpx.AsyncClient(
            verify=False,  # Disable SSL verification if needed
            timeout=httpx.Timeout(60.0, connect=30.0),
            headers={'X-Emby-Token': self.api_key},
            follow_redirects=True,
            limits=limits,
            trust_env=False  # 关键：禁用读取系统代理环境变量，防止内网地址被代理拦截
        )
        
        # Concurrency control for downloads
        # Increased to 16 to maximize throughput
        self.download_semaphore = asyncio.Semaphore(16)

        # /System/Info 返回的 ServerId 缓存（服务端基本不变）
        self._cached_server_id: Optional[str] = None

        self.item_details_cache = {}

        # 全库扫描结果内存缓存（按 emby_type 区分），3 分钟有效期
        # 结构: { cache_key: (items_list, fetched_timestamp) }
        self._all_items_cache: Dict[str, tuple[list, float]] = {}
        # 按类型区分的锁，避免同一类型并发重复全库扫描
        self._all_items_locks: Dict[str, asyncio.Lock] = {}
        # 上次清理缓存的时间戳，每 5 分钟清理一次过期条目
        self._last_cache_cleanup: float = time.time()

        # Fetch user ID asynchronously after initialization if not provided
        # Since __init__ cannot be async, we'll schedule this or rely on methods checking for it.
        # For simplicity in this async transition, if user_id is missing, it will be fetched on first request if possible,
        # or better, providing a start-up async method.
        # However, to keep API consistent, we will let _fetch_user_id handle it lazily or explicit call.

    async def close(self):
        await self.client.aclose()

    async def _fetch_user_id(self):
        log_audit("Emby", "初始化", "正在自动获取 Emby 用户 ID")
        response, error = await self._make_request("GET", "/Users")
        if error: raise ConnectionError(f"Failed to fetch user ID: {error}")
        
        if response and isinstance(response, list) and len(response) > 0:
            admin_user = next((u for u in response if u.get('Policy', {}).get('IsAdministrator')), response[0])
            self.user_id = admin_user.get('Id')
            log_audit("Emby", "初始化", f"已自动获取用户 ID: {self.user_id}", level="SUCCESS")
        else:
            raise ValueError("Could not find any users on the Emby server.")

    async def _ensure_user_id(self):
        if not self.user_id:
            try:
                await self._fetch_user_id()
            except Exception as e:
                log_audit("Emby", "初始化", f"自动获取用户 ID 失败: {e}，将以无用户身份继续运行", level="WARN")

    async def _make_request(self, method, endpoint, params=None, json_payload=None, stream=False, timeout=20.0, data=None, headers_override=None, exclude_user_id=False):
        # 预处理 endpoint，防止用户输入的 server_url 已经包含了 /emby
        clean_endpoint = endpoint.lstrip('/')
        if self.server_url.lower().endswith('/emby'):
            # 如果服务器地址已包含 /emby，去掉 endpoint 开头的 emby/
            if clean_endpoint.lower().startswith('emby/'):
                clean_endpoint = clean_endpoint[5:]
        
        endpoints_to_try = [f"/{clean_endpoint}"]
        # 如果服务器地址没包含 /emby，尝试带和不带 /emby 两种情况
        if not self.server_url.lower().endswith('/emby'):
            if not clean_endpoint.lower().startswith('emby/'):
                endpoints_to_try.append(f"/emby/{clean_endpoint}")
        
        endpoints_to_try = list(OrderedDict.fromkeys(endpoints_to_try))
        
        diagnostic_logs = []
        max_retries = 2 # 稍微减少重试次数，加快报错反馈

        for ep in endpoints_to_try:
            url = urljoin(self.server_url + '/', ep.lstrip('/'))
            
            for attempt in range(max_retries + 1):
                try:
                    final_params = params.copy() if params else {}
                    final_params['api_key'] = self.api_key
                    if self.user_id and not exclude_user_id: 
                        final_params.setdefault('UserId', self.user_id)
                    
                    final_headers = headers_override.copy() if headers_override else {}
                    
                    if stream:
                        request = self.client.build_request(
                            method, url, params=final_params, json=json_payload,
                            content=data, headers=final_headers, timeout=timeout
                        )
                        response = await self.client.send(request, stream=True)
                    else:
                        response = await self.client.request(
                            method, url, params=final_params, json=json_payload, 
                            content=data, headers=final_headers, timeout=timeout
                        )
                    
                    response.raise_for_status()

                    if stream: return response, None
                    if response.status_code == 204: return {"success": True}, None
                    return response.json() if response.content else {}, None

                except httpx.HTTPStatusError as e:
                    await e.response.aclose()
                    status_code = e.response.status_code
                    diagnostic_logs.append(f"HTTP {status_code} at {url}")
                    
                    if status_code == 404:
                        break # 404 就不重试了，换下一个 endpoint 尝试
                    
                    if status_code >= 500 and attempt < max_retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break 
                    
                except (httpx.RequestError, httpx.TimeoutException) as e:
                    err_msg = f"{type(e).__name__}: {str(e)} at {url}"
                    diagnostic_logs.append(err_msg)
                    if attempt < max_retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    break
        
        error_report = " | ".join(diagnostic_logs)
        return None, f"Emby 连接失败。详细诊断: {error_report}"

    async def search_by_title(self, title: str, emby_type: str) -> tuple[list, str | None]:
        """通过标题搜索 Emby 库，返回匹配的媒体项列表。"""
        await self._ensure_user_id()
        params = {
            'SearchTerm': title,
            'IncludeItemTypes': emby_type,
            'Recursive': 'true',
            'Fields': 'Id,Name,Path,ProviderIds'
        }
        data, error = await self._make_request("GET", "/Items", params=params)
        if error:
            return [], error
        if not data or not data.get("Items"):
            return [], None
        return data["Items"], None

    def _cleanup_expired_caches(self):
        """定期清理过期的全库缓存条目和不再使用的锁，防止内存缓慢增长"""
        now = time.time()
        # 每 5 分钟才执行一次清理
        if now - self._last_cache_cleanup < 300:
            return
        self._last_cache_cleanup = now

        CACHE_TTL = 180
        # 清理过期缓存
        expired_keys = [
            k for k, (_, ts) in self._all_items_cache.items()
            if now - ts > CACHE_TTL
        ]
        for k in expired_keys:
            self._all_items_cache.pop(k, None)
            self._all_items_locks.pop(k, None)

    async def _fetch_all_items_parallel(
        self,
        item_types: str = "Movie,Series",
        has_tmdb_id: bool = False,
        fields: str = "ProviderIds,Name,Id,Type,ProductionYear,Genres,Tags,LockedFields,GenreItems,TagItems",
        max_workers: int = 8,
        exclude_user_id: bool = False,
    ) -> list:
        """
        统一入口：多线程分页并行拉取 Emby 全库项目。
        先探测总数，再分成 max_workers 页并行拉取，最后合并。
        带 3 分钟内存缓存（按 cache_key 区分），避免短时间内重复全库扫描。
        """
        CACHE_TTL = 180  # 3 分钟
        cache_key = f"{item_types}|tmdb={has_tmdb_id}|{fields}"

        # 定期清理过期缓存，防止内存缓慢增长
        self._cleanup_expired_caches()

        # 第一次检查缓存（无锁快速路径）
        cache_entry = self._all_items_cache.get(cache_key)
        if cache_entry:
            cached_items, fetched_at = cache_entry
            age = time.time() - fetched_at
            if age < CACHE_TTL:
                log_audit("Emby", "缓存", f"全库扫描命中内存缓存: [{cache_key}] 共 {len(cached_items)} 条（缓存剩余 {int(CACHE_TTL - age)} 秒）")
                return cached_items

        # 加锁，避免同一 cache_key 的并发重复全库扫描
        lock = self._all_items_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # 持锁后双重检查：可能其他协程刚刚已完成扫描并填充缓存
            cache_entry = self._all_items_cache.get(cache_key)
            if cache_entry:
                cached_items, fetched_at = cache_entry
                age = time.time() - fetched_at
                if age < CACHE_TTL:
                    log_audit("Emby", "缓存", f"全库扫描命中内存缓存（持锁后二次检查）: [{cache_key}] 共 {len(cached_items)} 条")
                    return cached_items

            base_params = {
                'IncludeItemTypes': item_types,
                'Recursive': 'true',
                'Fields': fields,
            }
            if has_tmdb_id:
                base_params['HasTmdbId'] = 'true'

            # 探测总数
            probe_params = {**base_params, 'Limit': 1}
            probe_data, _ = await self._make_request("GET", "/Items", params=probe_params, exclude_user_id=exclude_user_id)
            total = probe_data.get('TotalRecordCount', 0) if probe_data else 0
            if total == 0:
                # 空结果也缓存，避免短时间内频繁探测空库
                self._all_items_cache[cache_key] = ([], time.time())
                return []

            # 小库直接单次拉取
            if total <= 200:
                data, _ = await self._make_request("GET", "/Items", params=base_params, exclude_user_id=exclude_user_id)
                items = data.get("Items", []) if data else []
                self._all_items_cache[cache_key] = (items, time.time())
                log_audit("Emby", "扫描", f"全库扫描完成（小库单次拉取）: [{cache_key}] 共 {len(items)} 条，已写入缓存", level="SUCCESS")
                return items

            # 大库分页并行拉取
            page_size = max((total + max_workers - 1) // max_workers, 1)
            actual_workers = min(max_workers, (total + page_size - 1) // page_size)

            async def _fetch_page(start: int):
                params = {**base_params, 'Limit': page_size, 'StartIndex': start}
                data, _ = await self._make_request("GET", "/Items", params=params, exclude_user_id=exclude_user_id)
                return data.get("Items", []) if data else []

            log_audit("Emby", "扫描", f"全库扫描: [{cache_key}] {total} 条项目，{actual_workers} 线程并行拉取（每页 {page_size} 条）", level="START")
            results = await asyncio.gather(*[_fetch_page(i * page_size) for i in range(actual_workers)])
            all_items = []
            for items in results:
                all_items.extend(items)
            self._all_items_cache[cache_key] = (all_items, time.time())
            log_audit("Emby", "扫描", f"全库扫描完成: [{cache_key}] 共拉取 {len(all_items)} 条，已写入缓存", level="SUCCESS")
            return all_items

    async def _fetch_all_items_with_tmdbid(self, emby_type: str, max_workers: int = 8) -> list:
        """
        薄封装：拉取带 TMDB ID 的全库项目（兼容旧调用方）。
        实际逻辑委托给 _fetch_all_items_parallel。
        """
        return await self._fetch_all_items_parallel(
            item_types=emby_type,
            has_tmdb_id=True,
            fields="Id,Name,Path,ProviderIds",
            max_workers=max_workers,
            exclude_user_id=False,
        )

    async def find_items_by_tmdb_id(self, tmdb_id: str, item_type: str, titles: list[str] | None = None, title_only: bool = False) -> tuple[list, str | None]:
        """
        通过 TMDB ID 搜索 Emby 库（核心搜索方法）。
        - 策略1：如果提供了 titles，优先用标题搜索 Emby → 再验证 TMDB ID 匹配。
        - 策略2：HasTmdbId 全库遍历（Emby API 不支持按 TMDB ID 值直接过滤，只能全量拉取后 Python 过滤）。
        - title_only=True 时仅做策略1，不触发全库扫描（供批量方法分阶段调用）。
        """
        await self._ensure_user_id()
        emby_type = "Series" if item_type == "tmdb-tv" else "Movie"
        all_found_items, processed_ids = [], set()
        log_audit("Emby", "查找", f"正在查找 TMDB ID {tmdb_id} (类型: {emby_type}) 的所有项目")

        # 策略1：用标题搜索 Emby，然后验证 TMDB ID 匹配
        if titles:
            for title in titles:
                if not title:
                    continue
                search_items, search_err = await self.search_by_title(title, emby_type)
                if search_err or not search_items:
                    continue
                for item in search_items:
                    if str(item.get("ProviderIds", {}).get("Tmdb")) == tmdb_id and item.get("Id") not in processed_ids and item.get("Type") == emby_type:
                        all_found_items.append(item); processed_ids.add(item.get("Id"))
                if all_found_items:
                    log_audit("Emby", "匹配", f"标题搜索命中: tmdb_id={tmdb_id} 标题='{title}' 匹配 {len(all_found_items)} 项", level="SUCCESS")
                    break  # 找到就不再尝试其他标题

        # 策略2：HasTmdbId 全库遍历（title_only 模式跳过，由批量方法统一处理）
        if not all_found_items and not title_only:
            all_items = await self._fetch_all_items_with_tmdbid(emby_type)
            for item in all_items:
                if str(item.get("ProviderIds", {}).get("Tmdb")) == tmdb_id and item.get("Id") not in processed_ids and item.get("Type") == emby_type:
                    all_found_items.append(item); processed_ids.add(item.get("Id"))

        if not all_found_items: return [], f"未找到 TMDB ID 为 {tmdb_id} 的项目。"
        return all_found_items, None
    
    async def get_item_details(self, emby_item_id: str, fields: str = "ProviderIds,Name,OriginalTitle,ProductionYear,ImageTags,Type,IndexNumber,ParentIndexNumber,Path,SeriesId,BackdropCount") -> tuple[dict | None, str | None]:
        await self._ensure_user_id()
        params = {'Fields': fields}
        endpoints_to_try = [f"/Users/{self.user_id}/Items/{emby_item_id}", f"/Items/{emby_item_id}"]
        for endpoint in endpoints_to_try:
            data, error = await self._make_request("GET", endpoint, params=params)
            if data and not error:
                return data, None
        return None, f"Failed to get details for item {emby_item_id} from all endpoints."

    async def get_item_playback_info(self, emby_item_id: str) -> tuple[dict | None, str | None]:
        # ServerId 基本不变，缓存后免去每次调用都先请求一遍 /System/Info
        if not self._cached_server_id:
            system_info, err = await self._make_request("GET", "/System/Info")
            if err or not system_info or not system_info.get("Id"):
                return None, f"无法从Emby获取System/Info来确定服务器ID: {err or '无有效响应'}"
            self._cached_server_id = system_info.get("Id")

        server_id = self._cached_server_id
        item_details, err = await self.get_item_details(emby_item_id, fields="Id,Name,Type")
        if err or not item_details:
             return None, f"获取项目详情失败: {err}"

        return { "EmbyItemId": emby_item_id, "ServerId": server_id, "Name": item_details.get("Name") }, None

    async def find_or_create_collection(self, collection_name: str, initial_ids: List[str] = None) -> Tuple[Optional[str], str]:
        log_audit("合集", "查找", f"查找或创建合集: {collection_name}")
        existing_collection = await self.find_collection_by_name(collection_name)
        if existing_collection:
            coll_id = existing_collection.get("Id")
            return coll_id, f"找到现有合集 '{collection_name}' (ID: {coll_id})。"

        params = {"Name": collection_name, "IsLocked": "false"}
        if initial_ids:
            params["Ids"] = ",".join(initial_ids)

        response, error = await self._make_request("POST", "/Collections", params=params)
        if error or not response or not response.get("Id"):
            return None, f"创建新合集 '{collection_name}' 失败: {error or '无效响应'}"
        
        return response.get("Id"), f"成功创建新合集 '{collection_name}' (ID: {response.get('Id')})。"

    async def add_items_to_collection(self, collection_id: str, emby_item_ids: List[str]) -> Tuple[bool, str]:
        if not emby_item_ids:
            return True, "没有需要添加到合集的项目。"
        log_audit("合集", "添加", f"向合集 {collection_id} 添加 {len(emby_item_ids)} 个项目")
        params = {"Ids": ",".join(emby_item_ids)}
        _, error = await self._make_request("POST", f"/Collections/{collection_id}/Items", params=params)
        if error:
            return False, f"添加项目到合集 {collection_id} 失败: {error}"
        return True, f"已成功发送请求，将 {len(emby_item_ids)} 个项目添加到合集 {collection_id}。"

    async def get_collection_items(self, collection_id: str) -> List[Dict]:
        data_parent, _ = await self._make_request("GET", "/Items", params={"ParentId": collection_id, "Fields": "Id,ProviderIds,Name,Type"})
        if data_parent and data_parent.get("Items"):
            return data_parent["Items"]
        
        data_collections, _ = await self._make_request("GET", f"/Collections/{collection_id}/Items", params={"Fields": "Id,ProviderIds,Name,Type"})
        if data_collections and data_collections.get("Items"):
            return data_collections["Items"]
        
        return []

    async def remove_items_from_collection(self, collection_id: str, emby_item_ids: List[str]) -> Tuple[bool, str]:
        if not emby_item_ids:
            return True, "没有需要从合集中移除的项目。"
        log_audit("合集", "移除", f"从合集 {collection_id} 移除 {len(emby_item_ids)} 个项目")
        params = {"Ids": ",".join(emby_item_ids)}
        _, error = await self._make_request("DELETE", f"/Collections/{collection_id}/Items", params=params)
        if error:
            return False, f"移除 {len(emby_item_ids)} 个项目失败: {error}"
        return True, f"成功发送请求，移除 {len(emby_item_ids)} 个项目。"
        
    async def set_collection_provider_id(self, collection_id: str, tmdb_collection_id: str) -> Tuple[bool, str]:
        if not tmdb_collection_id:
            return True, "未提供TMDB Collection ID，跳过设置。"
        
        log_audit("合集", "更新", f"设置合集 {collection_id} 的 Provider ID: {tmdb_collection_id}")
        item_details, error = await self.get_item_details(collection_id, fields="ProviderIds,Name")
        if error or not item_details:
            return False, f"设置Provider ID失败：无法获取合集 {collection_id} 的当前信息: {error}"

        item_details.setdefault("ProviderIds", {})["TmdbCollection"] = str(tmdb_collection_id)
        _, error = await self._make_request("POST", f"/Items/{collection_id}", json_payload=item_details)
        if error:
            return False, f"更新合集 {collection_id} 的Provider ID失败: {error}"
        return True, f"成功为合集 {collection_id} 设置TMDB Collection ID。"

    async def get_emby_item_ids_from_tmdb_ids(
        self,
        tmdb_ids: List[str],
        item_type_str: str,
        titles_map: Dict[str, List[str]] = None,
        on_progress=None,  # async callable: async def(label: str, current: int, total: int) -> None
    ) -> Dict[str, str]:
        """
        统一入口：批量将 TMDB ID 解析为 Emby Item ID。
        两阶段优化：Phase1 标题逐个查（不触发全库扫描），Phase2 一次全库扫描批量匹配所有剩余 ID。
        on_progress 为可选的异步回调，用于实时通知调用方当前查找进度。
        """
        if not tmdb_ids: return {}
        item_type_for_api = "tmdb-movies2" if item_type_str == "Movie" else "tmdb-tv"
        emby_type = "Series" if item_type_for_api == "tmdb-tv" else "Movie"
        id_map = {}
        remaining_ids = set(str(tid) for tid in tmdb_ids)
        total = len(tmdb_ids)

        # Phase 1: 标题优先搜索（逐个查，title_only=True 避免触发全库扫描）
        for idx, tmdb_id in enumerate(tmdb_ids):
            tmdb_id = str(tmdb_id)
            titles = titles_map.get(tmdb_id) if titles_map else None
            if on_progress:
                label = titles[0] if titles else f"TMDB {tmdb_id}"
                await on_progress(label, idx + 1, total)
            if titles:
                found_items, _ = await self.find_items_by_tmdb_id(tmdb_id, item_type_for_api, titles, title_only=True)
                if found_items and found_items[0].get("Id"):
                    id_map[tmdb_id] = str(found_items[0]["Id"])
                    remaining_ids.discard(tmdb_id)

        # Phase 2: 多线程全库扫描，批量匹配所有未命中的 ID
        if remaining_ids:
            log_audit("Emby", "匹配", f"标题搜索未命中 {len(remaining_ids)} 个 ID，执行多线程全库扫描批量匹配")
            if on_progress:
                await on_progress(f"全库扫描匹配剩余 {len(remaining_ids)} 个项目", total, total)
            all_items = await self._fetch_all_items_with_tmdbid(emby_type)
            for item in all_items:
                item_tmdb = str(item.get("ProviderIds", {}).get("Tmdb", ""))
                if item_tmdb in remaining_ids and item.get("Type") == emby_type:
                    id_map[item_tmdb] = str(item.get("Id"))
                    remaining_ids.discard(item_tmdb)
                    if not remaining_ids:
                        break

        return id_map

    async def upload_collection_image(self, collection_id: str, image_type: str, image_path: str) -> Tuple[bool, str]:
        log_audit("合集", "上传", f"上传合集图片: {image_type} -> {collection_id}")
        if not os.path.exists(image_path):
            return False, f"图片文件未找到: {image_path}"
        base64_content = image_to_base64(image_path)
        if not base64_content:
            return False, f"无法对图片进行Base64编码: {image_path}"

        _, ext = os.path.splitext(image_path.lower())
        content_type = {"png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext.strip('.'), "image/jpeg")
        
        headers = {"Content-Type": content_type}
        endpoint = f"/Items/{collection_id}/Images/{image_type}"
        _, error = await self._make_request("POST", endpoint, data=base64_content.encode('utf-8'), headers_override=headers, timeout=180)
        if error:
            return False, f"上传图片 '{os.path.basename(image_path)}' ({image_type}) 失败: {error}"
        return True, f"成功上传图片 '{os.path.basename(image_path)}' ({image_type}) 到合集 {collection_id}。"

    async def download_all_images_for_tmdb_id(self, item_type: str, tmdb_id: str, target_base_dir: str, broadcast: bool = True, titles: list[str] | None = None) -> Tuple[bool, str]:
        """
        为一个 TMDB ID 找到所有匹配的 Emby 项目，并为每一个项目独立下载其所有图片。
        (并发优化版)
        """
        self.item_details_cache.clear()

        emby_items, error = await self.find_items_by_tmdb_id(tmdb_id, item_type, titles=titles)
        if error:
            return False, error
        if not emby_items:
            return False, f"在 Emby 中找不到 TMDB ID 为 {tmdb_id} 的项目。"
            
        total_downloaded_count = 0
        error_messages = []
        
        # 创建并发任务列表
        tasks = []
        for item in emby_items:
            emby_item_id = item.get("Id")
            item_name = item.get("Name", emby_item_id)
            if not emby_item_id:
                continue
            
            log_audit("Emby", "下载", f"调度任务: 为 Emby 项目 '{item_name}' (ID: {emby_item_id}) 下载图片", level="START")
            tasks.append(self._recursive_image_downloader(emby_item_id, target_base_dir))
            
        if not tasks:
            return True, "没有有效的 Emby 项目需要处理。"

        # 并发执行所有顶层项目的下载
        total_tasks_count = len(tasks)
        if total_tasks_count > 0 and broadcast:
             await manager.broadcast_progress("download", "running", 0, total_tasks_count, f"开始下载 {total_tasks_count} 个项目的图片...")

        # 使用 as_completed 或手动包装任务以实现实时进度更新
        # 这里为了保持逻辑简单并能捕获错误，我们使用包装器模式
        
        async def _wrapped_task(index, task, item_name):
            try:
                res = await task
                if broadcast:
                    await manager.broadcast_progress("download", "running", index + 1, total_tasks_count, f"已完成: {item_name}")
                return res
            except Exception as e:
                return e

        # 将原始任务包装起来
        wrapped_tasks = []
        for i, (item_id, item_name) in enumerate([(item.get("Id"), item.get("Name", "Unknown")) for item in emby_items if item.get("Id")]):
             # 注意：_recursive_image_downloader 是在循环中被调用的，这里需要重新创建 coroutine
             # 上面的 tasks 列表已经是 coroutine 对象了，所以我们需要重新组织结构
             # 为了避免重新创建的麻烦，我们直接包装 tasks[i]
             wrapped_tasks.append(_wrapped_task(i, tasks[i], item_name))

        # 并发执行包装后的任务
        results = await asyncio.gather(*wrapped_tasks, return_exceptions=True)
        
        for idx, result in enumerate(results):
            item_name = emby_items[idx].get("Name", "Unknown")
            # 进度已在 _wrapped_task 中更新，这里处理结果汇总
            
            if isinstance(result, Exception):
                error_messages.append(f"处理项目 '{item_name}' 时发生异常: {str(result)}")
            else:
                downloaded, errors = result
                total_downloaded_count += downloaded
                if errors:
                    error_messages.append(f"处理项目 '{item_name}' 时出错: {', '.join(errors)}")

        final_msg = f"下载完成。共下载 {total_downloaded_count} 张图片。"
        if broadcast:
            await manager.broadcast_progress("download", "completed", total_tasks_count, total_tasks_count, final_msg)

        if error_messages:
            return False, f"图片下载完成，但存在错误：\n" + "\n".join(error_messages)
            
        return True, f"操作完成。共为 {len(emby_items)} 个Emby项目下载了 {total_downloaded_count} 张图片。"

    async def _recursive_image_downloader(self, item_id: str, target_dir: str) -> Tuple[int, List[str]]:
        """
        为一个独立的 Emby Item ID 递归下载其自身和所有子项的图片。
        (并发优化版)
        """
        download_count = 0
        errors = []

        details, err = await self.get_item_details(item_id)
        if err or not details:
            errors.append(f"无法获取 {item_id} 的详情: {err}")
            return 0, errors

        # 1. 下载当前项目的图片 (自身并发在 _download_images_for_single_item 内部处理或保持原子性，这里主要优化子项并发)
        # 考虑到单个项目图片通常较少，这里可以await，但在 _download_images_for_single_item 内部可以并发
        # logger.info(f"正在处理 '{details.get('Name', item_id)}' (Type: {details.get('Type')}) 的图片") # Reduced log noise
        current_item_images, image_errors = await self._download_images_for_single_item(details, target_dir)
        download_count += current_item_images
        errors.extend(image_errors)

        child_tasks = []

        # 2. 如果是剧集，获取所有季并创建任务
        if details.get("Type") == "Series":
            seasons, err = await self._make_request("GET", f"/Shows/{item_id}/Seasons", params={"Fields": "Id"})
            if err or not seasons or not seasons.get("Items"):
                if err: errors.append(f"无法获取剧集 {item_id} 的季列表: {err}")
            else:
                for season in seasons["Items"]:
                    if season.get("Id"):
                        child_tasks.append(self._recursive_image_downloader(season["Id"], target_dir))

        # 3. 如果是季，获取所有集并创建任务
        elif details.get("Type") == "Season":
            series_id = details.get("SeriesId")
            if series_id:
                episodes, err = await self._make_request("GET", f"/Shows/{series_id}/Episodes", params={"SeasonId": item_id, "Fields": "Id"})
                if err or not episodes or not episodes.get("Items"):
                    if err: errors.append(f"无法获取季 {item_id} 的集列表: {err}")
                else:
                    for episode in episodes["Items"]:
                        if episode.get("Id"):
                            child_tasks.append(self._recursive_image_downloader(episode["Id"], target_dir))
        
        # 4. 并发执行所有子任务
        if child_tasks:
            results = await asyncio.gather(*child_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    errors.append(f"子项处理异常: {str(res)}")
                else:
                    c_dl, c_err = res
                    download_count += c_dl
                    errors.extend(c_err)
        
        return download_count, errors

    async def _download_images_for_single_item(self, item_details: Dict, target_dir: str) -> Tuple[int, List[str]]:
        """
        下载单个项目的所有类型图片。
        (并发优化版)
        """
        item_id = item_details.get("Id")
        item_type = item_details.get("Type")
        item_name_for_log = item_details.get("Name", f"ID_{item_id}")

        final_tasks = {}

        # 1. 处理 ImageTags
        image_tags = item_details.get("ImageTags", {})
        if image_tags:
            naming_rules_for_type = EMBY_IMAGE_NAMING_RULES.get(item_type, {})

            for image_type_key, tag in image_tags.items():
                if not tag: continue

                base_name = None
                if item_type in ["Movie", "Series"]:
                    base_name = naming_rules_for_type.get(image_type_key)
                
                elif item_type == "Season":
                    template = naming_rules_for_type.get(image_type_key)
                    if template:
                        s_num = item_details.get('IndexNumber', 0)
                        base_name = template.format(season_num=s_num)
                
                elif item_type == "Episode":
                    template = naming_rules_for_type.get(image_type_key)
                    if template:
                        s_num = item_details.get('ParentIndexNumber', 0)
                        e_num = item_details.get('IndexNumber', 0)
                        base_name = template.format(season_num=s_num, episode_num=e_num)

                if not base_name:
                    base_name = image_type_key.lower()
                    log_audit("Emby", "下载", f"未在规则中找到 '{image_type_key}' 的命名映射，使用默认名 '{base_name}'", level="WARN")
                
                final_tasks[base_name] = (image_type_key, tag)

        # 2. 处理 BackdropImageTags
        backdrop_tags = item_details.get("BackdropImageTags", [])
        if backdrop_tags:
            last_backdrop_tag = backdrop_tags[-1]
            log_audit("Emby", "下载", f"'{item_name_for_log}' 在 BackdropImageTags 中找到 {len(backdrop_tags)} 张背景图，将使用最后一张作为唯一的 'fanart'")
            final_tasks["fanart"] = ("Backdrop", last_backdrop_tag)

        if not final_tasks:
            log_audit("Emby", "下载", f"项目 '{item_name_for_log}' (ID: {item_id}) 没有任何可下载的图片信息", level="WARN")
            return 0, []

        # 3. 创建并发下载任务
        download_futures = []
        for base_name, (api_type, tag) in final_tasks.items():
            download_futures.append(
                self._download_single_image_with_semaphore(item_id, api_type, tag, base_name, target_dir)
            )

        results = await asyncio.gather(*download_futures, return_exceptions=True)
        
        count = 0
        errors = []
        for res in results:
            if isinstance(res, Exception):
                errors.append(str(res))
            else:
                success, msg = res
                if success:
                    count += 1
                else:
                    errors.append(msg)
                    
        return count, errors

    async def _download_single_image_with_semaphore(self, item_id: str, api_type: str, tag: str, base_name: str, target_dir: str) -> Tuple[bool, str]:
        """
        受信号量控制的实际下载任务
        """
        async with self.download_semaphore:
            # 增加随机延迟，避免瞬间请求过于密集触发 Emby 或 网络瓶颈
            await asyncio.sleep(random.uniform(0.1, 0.5))
            
            log_audit("Emby", "下载", f"开始下载: 文件名 '{base_name}' (API类型: {api_type})", level="START")
            
            # Send finer-grained progress for single file
            await manager.broadcast_progress("download_file", "running", 0, 1, f"下载中: {base_name}")
            
            response, dl_error = await self._make_request("GET", f"/Items/{item_id}/Images/{api_type}", params={'tag': tag}, stream=True, timeout=60.0) # Increased timeout
            if dl_error or not response:
                log_audit("Emby", "下载", f"下载图片失败: {dl_error}", level="ERROR")
                return False, f"下载图片 {base_name} 失败: {dl_error}"
            
            try:
                content_type = response.headers.get('content-type', 'image/jpeg').lower()
                ext = '.png' if 'png' in content_type else '.webp' if 'webp' in content_type else '.jpg'
                filename = f"{base_name}{ext}"
                save_path = os.path.join(target_dir, "images", filename)

                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                
                async with aiofiles.open(save_path, 'wb') as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        await f.write(chunk)
                
                log_audit("Emby", "下载", f"图片已成功保存到: {save_path}", level="SUCCESS")
                return True, ""
            except Exception as e:
                log_audit("Emby", "下载", f"保存文件时出错: {e}", level="ERROR")
                return False, f"保存图片 {filename} 失败: {e}"
            finally:
                if 'response' in locals() and hasattr(response, 'aclose'):
                    await response.aclose()

    async def download_single_image_for_item(self, item_details: Dict, emby_image_type: str, target_base_dir: str) -> Tuple[bool, str]:
        """
        为一个给定的项目详情，下载一种指定类型的图片。
        """
        item_id = item_details.get("Id")
        item_type = item_details.get("Type")
        item_name_for_log = item_details.get("Name", f"ID_{item_id}")

        if not item_id or not item_type or item_type not in EMBY_IMAGE_NAMING_RULES:
            return False, f"项目详情无效或类型不受支持: {item_type}"

        image_tags = item_details.get("ImageTags", {})
        backdrop_tags = item_details.get("BackdropImageTags", [])
        
        tag_to_use = None
        api_type_for_request = emby_image_type

        if emby_image_type == "Backdrop" and backdrop_tags:
            tag_to_use = backdrop_tags[-1]
        elif emby_image_type in image_tags:
            tag_to_use = image_tags[emby_image_type]
        
        if not tag_to_use:
            return False, f"在项目 '{item_name_for_log}' 中未找到类型为 '{emby_image_type}' 的图片信息 (tag)。"

        naming_rules_for_type = EMBY_IMAGE_NAMING_RULES.get(item_type, {})
        base_name_template = naming_rules_for_type.get(emby_image_type)
        
        if not base_name_template:
             log_audit("Emby", "下载", f"未在规则中找到 '{emby_image_type}' 的命名映射，将使用小写键名作为后备", level="WARN")
             base_name = emby_image_type.lower()
        else:
            base_name = base_name_template
            if item_type == "Season":
                s_num = item_details.get('IndexNumber', 0)
                base_name = base_name.format(season_num=s_num)
            elif item_type == "Episode":
                s_num = item_details.get('ParentIndexNumber', 0)
                e_num = item_details.get('IndexNumber', 0)
                base_name = base_name.format(season_num=s_num, episode_num=e_num)
        
        log_audit("Emby", "下载", f"准备为 '{item_name_for_log}' 精确下载 -> 文件名: '{base_name}', API类型: '{api_type_for_request}'", level="START")
        
        response, dl_error = await self._make_request("GET", f"/Items/{item_id}/Images/{api_type_for_request}", params={'tag': tag_to_use}, stream=True)
        if dl_error or not response:
            return False, f"下载图片 {base_name} 失败: {dl_error}"

        try:
            content_type = response.headers.get('content-type', 'image/jpeg').lower()
            ext = '.png' if 'png' in content_type else '.webp' if 'webp' in content_type else '.jpg'
            filename = f"{base_name}{ext}"
            save_path = os.path.join(target_base_dir, "images", filename)

            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            async with aiofiles.open(save_path, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    await f.write(chunk)
            
            log_audit("Emby", "下载", f"图片已成功保存到: {save_path}", level="SUCCESS")
            return True, f"图片 '{filename}' 下载成功。"
        except Exception as e:
            return False, f"保存图片 {filename} 失败: {e}"
        finally:
            if 'response' in locals() and hasattr(response, 'aclose'):
                await response.aclose()

    async def trigger_refresh(self, emby_item_id: str) -> tuple[bool, str]:
        log_audit("Emby", "刷新", f"发送刷新请求: {emby_item_id}")
        params = {
            'Recursive': 'true', 
            'MetadataRefreshMode': 'FullRefresh', 
            'ImageRefreshMode': 'FullRefresh',
            'ReplaceAllImages': 'true',
            'ReplaceAllMetadata': 'true'
        }
        _, error = await self._make_request("POST", f"/Items/{emby_item_id}/Refresh", params=params)
        return (False, error) if error else (True, "强制刷新请求已发送。")

    async def update_provider_ids(self, emby_item_id: str, new_tmdb_id: str) -> tuple[bool, str | None]:
        log_audit("Emby", "更新", f"更新 Provider ID: {emby_item_id} -> TMDB {new_tmdb_id}")
        item_data, error = await self.get_item_details(emby_item_id)
        if error: return False, f"获取项目详情失败: {error}"
        
        item_data.setdefault("ProviderIds", {})["Tmdb"] = new_tmdb_id
        _, post_error = await self._make_request("POST", f"/Items/{emby_item_id}", json_payload=item_data)
        if post_error:
            return False, f"更新 ProviderIds 失败: {post_error}"
        return True, None
        
    async def find_collection_by_name(self, collection_name: str) -> Optional[Dict]:
        params = { 'Recursive': 'true', 'IncludeItemTypes': 'BoxSet', 'Name': collection_name }
        data, _ = await self._make_request("GET", "/Items", params=params)
        if data and data.get("Items"):
            for collection in data["Items"]:
                if collection.get("Name") == collection_name:
                    return collection
        return None

    async def get_all_collections(self) -> List[Dict]:
        params = { 'Recursive': 'true', 'IncludeItemTypes': 'BoxSet', 'Fields': 'Id,ProviderIds,Name' }
        data, err = await self._make_request("GET", "/Items", params=params)
        if err or not data or not data.get("Items"):
            return []
        return data["Items"]

    async def download_image_for_item(self, emby_item_id: str, image_type: str, save_path: str) -> bool:
        save_dir, base_filename = os.path.dirname(save_path), os.path.splitext(os.path.basename(save_path))[0]
        try:
            os.makedirs(save_dir, exist_ok=True)
            for f in os.listdir(save_dir):
                if f.startswith(base_filename): os.remove(os.path.join(save_dir, f))
        except OSError: pass

        response, err = await self._make_request("GET", f"/Items/{emby_item_id}/Images/{image_type}", stream=True)
        if err or not response: return False
            
        try:
            if 'image' not in response.headers.get('content-type', '').lower(): return False
            
            async with aiofiles.open(save_path, 'wb') as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    await f.write(chunk)
            return True
        except Exception:
            if os.path.exists(save_path): os.remove(save_path)
            return False
        finally:
            if hasattr(response, 'aclose'):
                await response.aclose()

    async def get_all_items(self, item_types: str = "Movie,Series") -> List[Dict]:
        """
        Fetch all items of specific types recursively.
        统一调用 _fetch_all_items_parallel（8线程并行 + 3分钟缓存）。
        """
        all_items = await self._fetch_all_items_parallel(
            item_types=item_types,
            has_tmdb_id=False,
            fields="ProviderIds,Name,Id,Type,ProductionYear,Genres,Tags,LockedFields,GenreItems,TagItems",
            max_workers=8,
            exclude_user_id=True,
        )

        # 后处理：GenreItems / TagItems → Genres / Tags
        for item in all_items:
            if "GenreItems" in item and not item.get("Genres"):
                item["Genres"] = [g["Name"] for g in item.get("GenreItems", []) if "Name" in g]
            if "TagItems" in item and not item.get("Tags"):
                item["Tags"] = [t["Name"] for t in item.get("TagItems", []) if "Name" in t]

        return all_items

    async def update_item_metadata(self, item_id: str, genres: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Update Genres and Tags for an item (Strict Match to Original)."""
        await self._ensure_user_id()
        
        # 1. Fetch current item FULL details via USER view
        params = {"Fields": "Genres,Tags,LockedFields,GenreItems,TagItems"}
        update_payload, err = await self._make_request("GET", f"/Users/{self.user_id}/Items/{item_id}", params=params)
        
        if err or not update_payload:
            log_audit("Emby", "更新", f"更新前重新获取项目 {item_id} 失败: {err}", level="ERROR")
            return False, f"获取项目 {item_id} 详情失败: {err or '无响应'}"
        
        changed = False
        
        # 2. Update Genres and GenreItems
        if genres is not None:
            new_genres = sorted(list(set(genres)))
            current_genre_names = set(g.get('Name') for g in update_payload.get("GenreItems", []))
            if current_genre_names != set(new_genres):
                update_payload["Genres"] = new_genres
                # Fix: Do NOT send 'Id' for GenreItems as passing a name as ID can cause 500 errors in some Emby versions.
                # Emby will look up or create the genre by Name.
                update_payload["GenreItems"] = [{"Name": g} for g in new_genres]
                changed = True

        # 3. Update Tags and TagItems
        if tags is not None:
            new_tags = sorted(list(set(tags)))
            current_tags = set(update_payload.get("Tags", []))
            if current_tags != set(new_tags):
                update_payload["Tags"] = new_tags
                update_payload["TagItems"] = [{"Name": t} for t in new_tags]
                changed = True
        
        if not changed:
            return True, "No Change"

        # 4. Handle Locked Fields
        locked_fields = set(update_payload.get("LockedFields", []))
        if "Genres" in locked_fields and genres is not None:
            locked_fields.remove("Genres")
        if "Tags" in locked_fields and tags is not None:
            locked_fields.remove("Tags")
        update_payload["LockedFields"] = list(locked_fields)

        # 5. Cleanup payload - Aggressively remove read-only or problem-causing fields
        fields_to_remove = [
            "ImageTags", "BackdropImageTags", "ParentId", "PrimaryImageAspectRatio",
            "CanDelete", "CanDownload", "CanEdit", "DisplayPreferencesId",
            "Etag", "DateCreated", "DateLastMediaAdded", "DateLastRefreshed",
            "DateLastSaved", "DateModified", "ServerId", "SortName",
            "PlayAccess", "ProductionLocations", "Path", "OfficialRating"
        ]
        # Also remove ChapterImages, MediaStreams if they cause issues, but usually they are fine.
        # Let's start with the list above.
        
        for field in fields_to_remove:
            update_payload.pop(field, None)
        
        # 6. Post update (Using /Items/{Id})
        # Original uses /emby/Items/{item_id}?api_key=... WITHOUT UserId in params for the POST.
        # Sending UserId in POST might cause Emby to treat it as user-specific data update conflict.
        _, post_err = await self._make_request("POST", f"/Items/{item_id}", json_payload=update_payload, exclude_user_id=True)
        
        if post_err:
            # OPTIMISTIC CHECK: If 500, verify if update actually happened
            if "500" in str(post_err):
                log_audit("Emby", "更新", f"项目 {item_id} 更新返回 500 错误，正在验证数据是否已持久化", level="WARN")
                await asyncio.sleep(0.5)
                # Re-fetch to check
                verify_data, verify_err = await self._make_request("GET", f"/Users/{self.user_id}/Items/{item_id}", params={"Fields": "Genres,Tags,GenreItems,TagItems"})
                if verify_data:
                    # Check Genres
                    current_genres = set(verify_data.get("Genres", []))
                    if genres is not None and sorted(list(current_genres)) != sorted(list(set(genres))):
                         msg = f"Update failed (Verification mismatched): {post_err}"
                         log_audit("Emby", "更新", f"Genres 验证不匹配: {post_err}", level="ERROR")
                         return False, msg
                    
                    # Check Tags
                    current_tags = set(verify_data.get("Tags", []))
                    if tags is not None and sorted(list(current_tags)) != sorted(list(set(tags))):
                         msg = f"Update failed (Verification mismatched): {post_err}"
                         log_audit("Emby", "更新", f"Tags 验证不匹配: {post_err}", level="ERROR")
                         return False, msg
                    
                    log_audit("Emby", "更新", f"虽然返回 500 错误，但项目 {item_id} 的更新验证成功", level="SUCCESS")
                    return True, "Success (Verified)"

            log_audit("Emby", "更新", f"更新项目 {item_id} 失败: {post_err}", level="ERROR")
            return False, str(post_err)
        
        return True, "Success"

    # ======== 季集搜索方案 (参考 cs123 项目) ========

    async def get_seasons(self, series_id: str) -> tuple[list | None, str | None]:
        """获取指定剧集的所有季信息。"""
        await self._ensure_user_id()
        data, error = await self._make_request("GET", f"/Shows/{series_id}/Seasons", params={
            'Fields': 'ProviderIds,IndexNumber',
            'EnableUserData': 'false'
        })
        if error:
            return None, error
        return (data.get('Items', []) if data else []), None

    async def get_episodes(self, series_id: str, season_id: str) -> tuple[list | None, str | None]:
        """获取指定剧集某季的所有集信息。"""
        await self._ensure_user_id()
        data, error = await self._make_request("GET", f"/Shows/{series_id}/Episodes", params={
            'SeasonId': season_id,
            'Fields': 'ProviderIds,IndexNumber,Path,MediaSources',
            'EnableUserData': 'false'
        })
        if error:
            return None, error
        return (data.get('Items', []) if data else []), None

    async def check_episode_exists(self, tmdb_id: str, season_number: int, episode_number: int,
                                   titles: list[str] | None = None) -> bool:
        """检查 Emby 库中是否存在指定 TMDB ID 的剧集的某季某集。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-tv", titles=titles)
        if error or not found_items:
            log_audit("Emby", "查询", f"检查集存在: TMDB ID {tmdb_id} 未找到匹配的剧集")
            return False

        log_audit("Emby", "查询", f"检查集存在: TMDB ID {tmdb_id} 找到 {len(found_items)} 个匹配项，正在检查 S{season_number}E{episode_number}")

        for series_item in found_items:
            series_id = series_item.get('Id')
            series_name = series_item.get('Name', 'Unknown')

            seasons, seasons_err = await self.get_seasons(series_id)
            if seasons_err or not seasons:
                if seasons_err:
                    log_audit("Emby", "查询", f"剧集 '{series_name}' 获取季信息失败: {seasons_err}", level="WARN")
                continue

            target_season = next((s for s in seasons if s.get('IndexNumber') == season_number), None)
            if not target_season:
                log_audit("Emby", "查询", f"剧集 '{series_name}' 没有找到第 {season_number} 季", level="WARN")
                continue

            episodes, eps_err = await self.get_episodes(series_id, target_season['Id'])
            if eps_err or not episodes:
                if eps_err:
                    log_audit("Emby", "查询", f"剧集 '{series_name}' 第 {season_number} 季获取集数失败: {eps_err}", level="WARN")
                continue

            for episode in episodes:
                if episode.get('IndexNumber') == episode_number:
                    log_audit("Emby", "查询", f"在剧集 '{series_name}' 中找到 S{season_number}E{episode_number}", level="SUCCESS")
                    return True

        log_audit("Emby", "查询", f"在所有匹配的 {len(found_items)} 个剧集中都未找到 S{season_number}E{episode_number}", level="WARN")
        return False

    async def get_episode_info(self, tmdb_id: str, season_number: int, episode_number: int,
                               titles: list[str] | None = None) -> dict:
        """获取指定 TMDB ID 剧集的某季某集的详细信息（含文件列表）。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-tv", titles=titles)
        if error or not found_items:
            log_audit("Emby", "查询", f"查询集信息: TMDB ID {tmdb_id} 未找到匹配的剧集")
            return {'exists': False}

        log_audit("Emby", "查询", f"查询集信息: TMDB ID {tmdb_id} 正在查询 S{season_number}E{episode_number}")

        for series_item in found_items:
            series_id = series_item.get('Id')
            series_name = series_item.get('Name', 'Unknown')

            seasons, seasons_err = await self.get_seasons(series_id)
            if seasons_err or not seasons:
                continue

            target_season = next((s for s in seasons if s.get('IndexNumber') == season_number), None)
            if not target_season:
                continue

            episodes, eps_err = await self.get_episodes(series_id, target_season['Id'])
            if eps_err or not episodes:
                continue

            for episode in episodes:
                if episode.get('IndexNumber') == episode_number:
                    media_sources = episode.get('MediaSources', [])
                    files = []
                    for source in media_sources:
                        files.append({
                            'path': source.get('Path', ''),
                            'name': source.get('Name', ''),
                            'size': source.get('Size', 0),
                            'container': source.get('Container', ''),
                        })
                    log_audit("Emby", "查询", f"在剧集 '{series_name}' 中找到 S{season_number}E{episode_number}，共 {len(files)} 个文件", level="SUCCESS")
                    return {
                        'exists': True,
                        'episode_id': episode.get('Id'),
                        'series_name': series_name,
                        'files': files
                    }

        log_audit("Emby", "查询", f"未找到 S{season_number}E{episode_number}", level="WARN")
        return {'exists': False}

    async def get_season_episodes_info(self, tmdb_id: str, season_number: int,
                                       titles: list[str] | None = None) -> dict[int, dict]:
        """获取指定 TMDB ID 剧集某季的所有集信息（含文件列表），返回 {集号: 信息} 字典。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-tv", titles=titles)
        if error or not found_items:
            log_audit("Emby", "查询", f"查询季度集信息: TMDB ID {tmdb_id} 未找到匹配的剧集")
            return {}

        log_audit("Emby", "查询", f"查询季度集信息: TMDB ID {tmdb_id} 找到 {len(found_items)} 个匹配项，正在查询第 {season_number} 季")

        episodes_info: dict[int, dict] = {}

        for series_item in found_items:
            series_id = series_item.get('Id')
            series_name = series_item.get('Name', 'Unknown')

            seasons, seasons_err = await self.get_seasons(series_id)
            if seasons_err or not seasons:
                continue

            target_season = next((s for s in seasons if s.get('IndexNumber') == season_number), None)
            if not target_season:
                continue

            episodes, eps_err = await self.get_episodes(series_id, target_season['Id'])
            if eps_err or not episodes:
                continue

            log_audit("Emby", "查询", f"剧集 '{series_name}' 第 {season_number} 季找到 {len(episodes)} 集", level="SUCCESS")

            for episode in episodes:
                ep_num = episode.get('IndexNumber')
                if ep_num is None:
                    continue

                media_sources = episode.get('MediaSources', [])

                if ep_num not in episodes_info:
                    episodes_info[ep_num] = {
                        'exists': True,
                        'episode_id': episode.get('Id'),
                        'series_name': series_name,
                        'files': []
                    }

                for source in media_sources:
                    file_path = source.get('Path', '')
                    existing_paths = {f.get('path') for f in episodes_info[ep_num]['files']}
                    if file_path and file_path not in existing_paths:
                        episodes_info[ep_num]['files'].append({
                            'path': file_path,
                            'name': source.get('Name', ''),
                            'size': source.get('Size', 0),
                            'container': source.get('Container', ''),
                        })

        total_episodes = len(episodes_info)
        total_files = sum(len(ep['files']) for ep in episodes_info.values())
        log_audit("Emby", "查询", f"查询季度集信息完成，共 {total_episodes} 集，{total_files} 个文件", level="SUCCESS")
        return episodes_info

    async def get_series_library_status(self, tmdb_id: str, titles: list[str] | None = None) -> dict:
        """获取指定 TMDB ID 剧集在 Emby 库中的状态（各季及集数统计）。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-tv", titles=titles)
        if error or not found_items:
            log_audit("Emby", "查询", f"查询剧集状态: TMDB ID {tmdb_id} 未找到匹配的剧集")
            return {'exists': False, 'seasons': {}}

        log_audit("Emby", "查询", f"查询剧集状态: TMDB ID {tmdb_id} 找到 {len(found_items)} 个匹配项")

        seasons_status: dict[int, dict] = {}

        for series_item in found_items:
            series_id = series_item.get('Id')
            series_name = series_item.get('Name', '')

            seasons, seasons_err = await self.get_seasons(series_id)
            if seasons_err or not seasons:
                continue

            for season in seasons:
                season_number = season.get('IndexNumber')
                if season_number is None:
                    continue

                episodes, eps_err = await self.get_episodes(series_id, season['Id'])
                if eps_err or not episodes:
                    continue

                if season_number not in seasons_status:
                    seasons_status[season_number] = {
                        'exists': True,
                        'total_episodes': len(episodes),
                        'series_name': series_name
                    }
                    log_audit("Emby", "查询", f"剧集 '{series_name}' 第 {season_number} 季有 {len(episodes)} 集")

        result = {
            'exists': True,
            'series_name': found_items[0].get('Name', '') if found_items else '',
            'seasons': seasons_status
        }
        log_audit("Emby", "查询", f"查询剧集状态完成，共 {len(seasons_status)} 季", level="SUCCESS")
        return result

    async def check_movie_exists(self, tmdb_id: str, titles: list[str] | None = None) -> bool:
        """检查 Emby 库中是否存在指定 TMDB ID 的电影。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-movies2", titles=titles)
        if found_items:
            log_audit("Emby", "查询", f"检查电影存在: TMDB ID {tmdb_id} 找到 {len(found_items)} 个匹配的电影", level="SUCCESS")
            return True
        log_audit("Emby", "查询", f"检查电影存在: TMDB ID {tmdb_id} 未找到匹配的电影", level="WARN")
        return False

    async def get_movie_info(self, tmdb_id: str, titles: list[str] | None = None) -> dict:
        """获取指定 TMDB ID 电影在 Emby 库中的详细信息（含文件列表）。"""
        found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-movies2", titles=titles)
        if error or not found_items:
            log_audit("Emby", "查询", f"查询电影信息: TMDB ID {tmdb_id} 未找到匹配的电影")
            return {'exists': False}

        movie_item = found_items[0]
        movie_name = movie_item.get('Name', 'Unknown')
        log_audit("Emby", "查询", f"找到电影 '{movie_name}'", level="SUCCESS")

        # 获取详情以拿到 MediaSources
        details, detail_err = await self.get_item_details(movie_item.get('Id'), fields="MediaSources,Path")
        media_sources = []
        if details:
            media_sources = details.get('MediaSources', [])
        elif movie_item.get('MediaSources'):
            media_sources = movie_item['MediaSources']

        files = []
        for source in media_sources:
            files.append({
                'path': source.get('Path', ''),
                'name': source.get('Name', ''),
                'size': source.get('Size', 0),
                'container': source.get('Container', ''),
            })

        log_audit("Emby", "查询", f"电影 '{movie_name}' 共 {len(files)} 个文件")
        return {
            'exists': True,
            'item_id': movie_item.get('Id'),
            'name': movie_name,
            'files': files
        }

    async def check_item_exists(self, tmdb_id: str, media_type: str,
                                season_number: int | None = None, episode_number: int | None = None,
                                titles: list[str] | None = None) -> bool:
        """
        统一检查 Emby 库中是否存在指定项目。
        - media_type: 'movie' 或 'series'
        - 对于 series，可指定 season_number 和 episode_number 检查特定集
        """
        if media_type == 'movie':
            return await self.check_movie_exists(tmdb_id, titles=titles)
        elif media_type == 'series':
            if season_number is not None and episode_number is not None:
                return await self.check_episode_exists(tmdb_id, season_number, episode_number, titles=titles)
            else:
                found_items, error = await self.find_items_by_tmdb_id(tmdb_id, "tmdb-tv", titles=titles)
                return bool(found_items)
        return False

    async def batch_check_items_exist(self, tmdb_ids: List[str], item_type: str) -> Dict[str, bool]:
        """
        批量检查多个 TMDB ID 是否在 Emby 库中存在。
        复用 _fetch_all_items_with_tmdbid 的 3 分钟内存缓存，整批只需一次全库拉取。
        返回 {tmdb_id: True/False} 字典。
        """
        if not tmdb_ids:
            return {}

        emby_type = "Series" if item_type == "tmdb-tv" else "Movie"
        # 复用已有的全库缓存（3分钟有效期），避免重复请求 Emby
        all_items = await self._fetch_all_items_with_tmdbid(emby_type)

        # 构建 Emby 库中所有 TMDB ID 的集合
        emby_tmdb_ids = {
            str(item.get("ProviderIds", {}).get("Tmdb", ""))
            for item in all_items
            if item.get("ProviderIds", {}).get("Tmdb")
        }

        return {str(tid): str(tid) in emby_tmdb_ids for tid in tmdb_ids}
