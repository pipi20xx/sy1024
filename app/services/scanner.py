import os
import json
import asyncio
import httpx
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List, Union
from sqlalchemy import select, delete, or_, func
from ..database import ItemsSessionLocal
from ..models import Item
from ..query_parser import QueryParser
from ..common import (
    MAIN_JSON_FILENAMES, TYPE_DISPLAY_NAMES, SOURCE_PRIMARY, SOURCE_OVERRIDE,
    STATIC_GENRES, format_date_to_year, find_image_files_for_item
)
from ..websocket_manager import manager
from ..logger import log_audit
from .configuration import ConfigurationService


class ScannerService:
    def __init__(self, configuration_service: ConfigurationService, emby_integration_service=None):
        self.configuration_service = configuration_service
        self.emby_integration_service = emby_integration_service
        self.scan_progress: Dict[str, Any] = {"status": "idle", "total": 0, "current": 0, "message": "未开始扫描"}

    def get_scan_progress(self) -> Dict[str, Any]:
        return self.scan_progress

    def _get_cache_path_for_source(self, source: str) -> Optional[str]:
        return self.configuration_service.get_cache_path_for_source(source)

    def _load_json_metadata(self, folder_path: str, main_json_filename: str) -> Tuple[Dict[str, Any], bool]:
        metadata, is_missing = {}, True
        file_path = os.path.join(folder_path, main_json_filename)
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    temp_metadata = json.load(f)
                if isinstance(temp_metadata, dict):
                    metadata, is_missing = temp_metadata, False
                    metadata['_source_json_filename'] = main_json_filename
            except Exception as e:
                log_audit("扫描", "失败", f"文件处理失败 '{file_path}': {e}", level="WARN")
        return metadata, is_missing

    def _extract_basic_info_from_meta(self, metadata: Dict[str, Any], data_type_key: str, folder_id_display: str) -> Dict[str, Any]:
        item_id = metadata.get("id", folder_id_display)
        name_key = "title" if data_type_key == "tmdb-movies2" else "name"
        name = metadata.get(name_key, f"未知名称 ({item_id})")
        date_key = "release_date" if data_type_key == "tmdb-movies2" else "first_air_date"
        year_str = format_date_to_year(metadata.get(date_key, ""))
        year = int(year_str) if year_str.isdigit() else None
        full_date = metadata.get(date_key, "")
        return {"name": name, "id": item_id, "year": year, "full_date": full_date}

    async def _scan_and_insert_item(self, session, data_type_key: str, folder_id: str, scan_time: str):
        active_source = None
        active_folder = None
        main_json_file = MAIN_JSON_FILENAMES.get(data_type_key)

        o_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        override_folder = os.path.join(o_path, data_type_key, folder_id) if o_path else None
        
        if override_folder and os.path.isfile(os.path.join(override_folder, main_json_file)):
            active_source = SOURCE_OVERRIDE
            active_folder = override_folder
        else:
            p_path = self._get_cache_path_for_source(SOURCE_PRIMARY)
            primary_folder = os.path.join(p_path, data_type_key, folder_id) if p_path else None
            if primary_folder and os.path.isfile(os.path.join(primary_folder, main_json_file)):
                active_source = SOURCE_PRIMARY
                active_folder = primary_folder
            else:
                return

        metadata, is_missing = await asyncio.to_thread(self._load_json_metadata, active_folder, main_json_file)
        if is_missing: return

        summary = self._extract_basic_info_from_meta(metadata, data_type_key, folder_id)
        genres_list = [g.get("name") for g in metadata.get("genres", []) if g.get("name")]
        
        poster_path_val = None
        if o_path:
            item_folder_override = os.path.join(o_path, data_type_key, folder_id)
            if os.path.isdir(item_folder_override):
                found_images = await asyncio.to_thread(find_image_files_for_item, {"node_type": TYPE_DISPLAY_NAMES.get(data_type_key)}, item_folder_override)
                if "poster" in found_images:
                    poster_path_val = f"/media-content/{data_type_key}/{folder_id}/images/{os.path.basename(found_images['poster'])}"

        has_episode_group = False
        if data_type_key == "tmdb-tv" and o_path:
            epg_path = os.path.join(o_path, data_type_key, folder_id, "episodegroup.json")
            has_episode_group = os.path.isfile(epg_path)

        has_external_ids = False
        if o_path:
            eids_path = os.path.join(o_path, data_type_key, folder_id, "external_ids.json")
            has_external_ids = os.path.isfile(eids_path)

        item = Item(
            item_id=str(summary['id']),
            item_type=data_type_key,
            source=active_source,
            name=summary['name'],
            year=summary['year'],
            full_date=summary['full_date'],
            poster_path=poster_path_val,
            genres=json.dumps(genres_list, ensure_ascii=False),
            folder_id=folder_id,
            json_path=os.path.join(active_folder, metadata.get('_source_json_filename', main_json_file)),
            last_scanned=scan_time,
            has_episode_group=has_episode_group,
            has_external_ids=has_external_ids
        )
        await session.merge(item)

    async def scan_all_data(self):
        if self.scan_progress["status"] == "scanning":
            log_audit("扫描", "跳过", "扫描已在进行中", level="WARN")
            return

        self.scan_progress = {"status": "scanning", "total": 0, "current": 0, "message": "正在初始化扫描..."}
        await manager.broadcast_progress("scan", "scanning", 0, 0, "正在初始化扫描...") # WS Push
        
        log_audit("扫描", "开始", "执行完整磁盘扫描", level="START")
        scan_time = datetime.now().isoformat()
        
        def _scan_dirs():
            items = []
            u_items = set()
            for source_type in [SOURCE_PRIMARY, SOURCE_OVERRIDE]:
                base_path = self._get_cache_path_for_source(source_type)
                if not (base_path and os.path.isdir(base_path)):
                    continue
                for data_type_key in TYPE_DISPLAY_NAMES.keys():
                    if data_type_key == "tmdb-collections": continue
                    type_path = os.path.join(base_path, data_type_key)
                    if not os.path.isdir(type_path): continue
                    for folder_name in os.listdir(type_path):
                        if os.path.isdir(os.path.join(type_path, folder_name)):
                            item_key = (data_type_key, folder_name)
                            if item_key not in u_items:
                                items.append({'data_type_key': data_type_key, 'folder_id': folder_name})
                                u_items.add(item_key)
            return items

        items_to_scan = await asyncio.to_thread(_scan_dirs)
        
        total_items_to_process = len(items_to_scan)
        self.scan_progress["total"] = total_items_to_process
        await manager.broadcast_progress("scan", "scanning", 0, total_items_to_process, f"发现 {total_items_to_process} 个项目。") # WS Push
        log_audit("扫描", "发现项目", f"共 {total_items_to_process} 个项目")

        try:
            async with ItemsSessionLocal() as session:
                log_audit("扫描", "开始", "正在清空旧的数据库缓存...")
                async with session.begin():
                    await session.execute(delete(Item))
                
                batch_size = 50
                for idx, item_data in enumerate(items_to_scan):
                    self.scan_progress["current"] = idx + 1
                    folder_id = item_data['folder_id']
                    data_type_key = item_data['data_type_key']
                    self.scan_progress["message"] = f"正在处理 '{data_type_key}/{folder_id}'"
                    
                    if idx % 5 == 0 or idx == total_items_to_process - 1:
                         await manager.broadcast_progress("scan", "scanning", idx + 1, total_items_to_process, self.scan_progress["message"])

                    try:
                        await self._scan_and_insert_item(session, data_type_key, folder_id, scan_time)
                        if (idx + 1) % batch_size == 0: await session.commit()
                    except Exception as e:
                        log_audit("扫描", "处理", f"处理项目 '{data_type_key}/{folder_id}' 时发生错误: {e}", level="ERROR")
                await session.commit()
            
            self.scan_progress = {"status": "completed", "total": total_items_to_process, "current": total_items_to_process, "message": f"扫描完成。"}
            await manager.broadcast_progress("scan", "completed", total_items_to_process, total_items_to_process, "扫描完成。") # WS Push
        except Exception as e:
            self.scan_progress["status"] = "error"
            self.scan_progress["message"] = f"扫描失败: {e}"
            await manager.broadcast_progress("scan", "error", 0, 0, f"扫描失败: {e}") # WS Push
            log_audit("扫描", "失败", str(e), level="ERROR")
        
        log_audit("扫描", "处理", self.scan_progress["message"])
    def get_available_genres(self, item_type: str) -> List[str]:
        return STATIC_GENRES

    async def get_available_years(self, item_type: str) -> List[str]:
        async with ItemsSessionLocal() as session:
            stmt = select(Item.year).where(Item.item_type == item_type).where(Item.year != None).distinct().order_by(Item.year.desc())
            result = await session.execute(stmt)
            return [str(year) for year in result.scalars().all()]
    
    async def get_items(self, item_type: str, search_term: Optional[str] = None, source: Optional[str] = None, 
                  poster_status: Optional[str] = None, genres: Optional[List[str]] = None, 
                  year: Optional[int] = None, month: Optional[int] = None, 
                  sort_by: Optional[str] = None,
                  page: int = 1, limit: int = 50) -> Dict[str, Any]:
        try:
            async with ItemsSessionLocal() as session:
                query = select(Item).where(Item.item_type == item_type)
                parser = QueryParser(search_term)
                base_search = parser.get_base_search_term().lower()
                
                if base_search:
                    pattern = f"%{base_search}%"
                    query = query.where(or_(Item.name.like(pattern), Item.item_id.like(pattern)))
                if source: query = query.where(Item.source == source)
                if poster_status == "yes": query = query.where(Item.poster_path != None)
                elif poster_status == "no": query = query.where(Item.poster_path == None)
                if genres:
                    for genre in genres: query = query.where(Item.genres.like(f'%"{genre}"%'))
                
                if year:
                    query = query.where(Item.year == year)
                    if month:
                        month_str = str(month).zfill(2)
                        query = query.where(Item.full_date.like(f"{year}-{month_str}-%"))

                count_q = select(func.count()).select_from(query.alias())
                total_items = (await session.execute(count_q)).scalar() or 0

                if total_items == 0:
                    return {"items": [], "total_items": 0, "total_pages": 0, "current_page": 1, "has_more": False}

                if sort_by == "name_asc": query = query.order_by(Item.name.asc())
                elif sort_by == "name_desc": query = query.order_by(Item.name.desc())
                elif sort_by == "date_asc": query = query.order_by(Item.full_date.asc())
                else: query = query.order_by(Item.full_date.desc())
                
                query = query.limit(limit).offset((page - 1) * limit)
                items = (await session.execute(query)).scalars().all()
                
                items_data = [item.to_dict() for item in items]

                # 异步查询 Emby 入库状态（受配置开关控制）
                # 开关关闭时不查询，不注入 in_library 字段，前端自然不显示角标
                # 开关开启时启动后台任务异步查询，通过 WebSocket 推送结果，不阻塞列表返回
                show_library_status = self.configuration_service.get("show_library_status", False)
                if show_library_status and self.emby_integration_service and items_data:
                    tmdb_ids = [item_data["id"] for item_data in items_data]
                    asyncio.create_task(self._async_query_library_status(item_type, tmdb_ids))

                # 同步查询 BGM 映射状态（受配置开关控制）
                # 只查本地 SQLite DB，开销极小，直接同步注入，不走 WebSocket
                show_bgm_status = self.configuration_service.get("show_bgm_mapping_status", False)
                if show_bgm_status and items_data:
                    from .. import globals
                    if globals.relation_service:
                        tmdb_ids = [item_data["id"] for item_data in items_data]
                        bgm_map = await globals.relation_service.batch_check_bangumi_mapping(item_type, tmdb_ids)
                        for item_data in items_data:
                            item_data["has_bgm_mapping"] = bgm_map.get(item_data["id"], False)

                return {
                    "items": items_data,
                    "total_items": total_items,
                    "total_pages": (total_items + limit - 1) // limit,
                    "current_page": page,
                    "has_more": page < ((total_items + limit - 1) // limit)
                }
        except Exception as e:
            log_audit("扫描", "失败", f"查询项目列表失败: {e}", level="ERROR")
            return {"items": [], "total_items": 0, "total_pages": 0, "current_page": 1, "has_more": False}

    async def get_all_item_ids_by_filter(self, item_type: str, search_term: Optional[str] = None, 
                                     source: Optional[str] = None, poster_status: Optional[str] = None, 
                                     genres: Optional[List[str]] = None, year: Optional[int] = None, 
                                     month: Optional[int] = None) -> List[str]:
        async with ItemsSessionLocal() as session:
            query = select(Item.item_id).where(Item.item_type == item_type)
            parser = QueryParser(search_term)
            base_search = parser.get_base_search_term().lower()
            if base_search:
                pattern = f"%{base_search}%"
                query = query.where(or_(Item.name.like(pattern), Item.item_id.like(pattern)))
            if source: query = query.where(Item.source == source)
            if poster_status == "yes": query = query.where(Item.poster_path != None)
            elif poster_status == "no": query = query.where(Item.poster_path == None)
            if genres:
                for genre in genres: query = query.where(Item.genres.like(f'%"{genre}"%'))
            if year:
                query = query.where(Item.year == year)
                if month:
                    month_str = str(month).zfill(2)
                    query = query.where(Item.full_date.like(f"{year}-{month_str}-%"))
            
            result = await session.execute(query)
            return result.scalars().all()

    async def _async_query_library_status(self, item_type: str, tmdb_ids: List[str]):
        """
        后台异步批量查询 Emby 入库状态，通过 WebSocket 推送给前端。
        不阻塞列表 API 返回，前端收到后自动更新卡片角标。
        """
        try:
            in_library_map = await self.emby_integration_service.batch_check_in_library(item_type, tmdb_ids)
            await manager.broadcast({
                "type": "library_status",
                "data": {
                    "item_type": item_type,
                    "statuses": in_library_map
                }
            })
        except Exception as e:
            log_audit("扫描", "警告", f"异步查询 Emby 入库状态失败: {e}", level="WARN")

    async def _refresh_item_in_db(self, item_type: str, folder_id: str):
        """编辑操作后刷新数据库中的项目记录。若项目不存在则即时扫描插入。"""
        async with ItemsSessionLocal() as session:
            exists = (await session.execute(
                select(Item.item_id).where(Item.item_type == item_type, Item.item_id == str(folder_id))
            )).scalar() is not None

        if not exists:
            log_audit("扫描", "处理", f"数据库中未找到 {item_type}/{folder_id}，尝试即时扫描", level="WARN")
        else:
            log_audit("扫描", "处理", f"刷新数据库记录: {item_type}/{folder_id}")

        try:
            async with ItemsSessionLocal() as session:
                async with session.begin():
                    await self._scan_and_insert_item(session, item_type, folder_id, datetime.now().isoformat())
            if not exists:
                log_audit("扫描", "即时完成", f"{folder_id} 已新增到数据库", level="SUCCESS")
            else:
                log_audit("扫描", "即时完成", f"{folder_id} 已更新到数据库", level="SUCCESS")
        except Exception as e:
            log_audit("扫描", "失败", f"刷新 {folder_id} 失败: {e}", level="ERROR")
    async def refresh_item_cache(self, item_type: str, folder_id: str) -> Tuple[bool, str]:
        log_audit("扫描", "处理", f"请求刷新缓存: {item_type}/{folder_id}")
        await self._refresh_item_in_db(item_type, folder_id)
        return True, "缓存刷新成功。"

    async def get_items_by_ids(self, movie_ids: List[str] = [], series_ids: List[str] = []) -> List[Dict[str, Any]]:
        log_audit("扫描", "查询", f"批量查询详情: {len(movie_ids)} 电影, {len(series_ids)} 剧集")
        movie_ids = list(set(filter(None, movie_ids)))
        series_ids = list(set(filter(None, series_ids)))
        if not movie_ids and not series_ids: return []

        found_items = []
        BATCH_SIZE = 500

        async with ItemsSessionLocal() as session:
            if movie_ids:
                for i in range(0, len(movie_ids), BATCH_SIZE):
                    batch = movie_ids[i:i + BATCH_SIZE]
                    stmt = select(Item.item_id, Item.item_type, Item.name, Item.year, Item.poster_path, Item.source).where(Item.item_type == 'tmdb-movies2', Item.item_id.in_(batch))
                    found_items.extend([{'id': r.item_id, 'type': r.item_type, 'name': r.name, 'year': r.year, 'poster_path': r.poster_path, 'source': r.source} for r in (await session.execute(stmt)).all()])
            if series_ids:
                for i in range(0, len(series_ids), BATCH_SIZE):
                    batch = series_ids[i:i + BATCH_SIZE]
                    stmt = select(Item.item_id, Item.item_type, Item.name, Item.year, Item.poster_path, Item.source).where(Item.item_type == 'tmdb-tv', Item.item_id.in_(batch))
                    found_items.extend([{'id': r.item_id, 'type': r.item_type, 'name': r.name, 'year': r.year, 'poster_path': r.poster_path, 'source': r.source} for r in (await session.execute(stmt)).all()])

            # Check missing and rescan
            found_ids = {str(item['id']) for item in found_items}
            missing_m = [mid for mid in movie_ids if mid not in found_ids]
            missing_s = [sid for sid in series_ids if sid not in found_ids]

            if missing_m or missing_s:
                log_audit("扫描", "补全", f"发现 {len(missing_m) + len(missing_s)} 个缺失项目，正在补全")
                scan_time = datetime.now().isoformat()
                
                # Batch insert/update within a single transaction
                try:
                    async with session.begin():
                        for mid in missing_m: 
                            try:
                                await self._scan_and_insert_item(session, 'tmdb-movies2', mid, scan_time)
                            except Exception as e:
                                log_audit("扫描", "失败", f"补全影片 {mid} 失败: {e}", level="WARN")
                        for sid in missing_s:
                            try:
                                await self._scan_and_insert_item(session, 'tmdb-tv', sid, scan_time)
                            except Exception as e:
                                log_audit("扫描", "失败", f"补全剧集 {sid} 失败: {e}", level="WARN")
                except Exception as e:
                    log_audit("扫描", "补全失败", str(e), level="ERROR")

                # Re-query
                to_check = missing_m + missing_s
                if to_check:
                    stmt = select(Item.item_id, Item.item_type, Item.name, Item.year, Item.poster_path, Item.source).where(Item.item_id.in_(to_check))
                    found_items.extend([{'id': r.item_id, 'type': r.item_type, 'name': r.name, 'year': r.year, 'poster_path': r.poster_path, 'source': r.source} for r in (await session.execute(stmt)).all()])

        # Check API for truly missing
        final_found_ids = {str(item['id']) for item in found_items}
        truly_missing_m = [mid for mid in movie_ids if mid not in final_found_ids]
        truly_missing_s = [sid for sid in series_ids if sid not in final_found_ids]
        
        if truly_missing_m: found_items.extend(await self._fetch_basic_info_from_tmdb_api(truly_missing_m, 'movie'))
        if truly_missing_s: found_items.extend(await self._fetch_basic_info_from_tmdb_api(truly_missing_s, 'tv'))

        # Sort results
        id_map = {f"{item['id']}_{item['type']}": item for item in found_items}
        sorted_res = []
        for mid in movie_ids:
            if f"{mid}_tmdb-movies2" in id_map: sorted_res.append(id_map[f"{mid}_tmdb-movies2"])
        for sid in series_ids:
            if f"{sid}_tmdb-tv" in id_map: sorted_res.append(id_map[f"{sid}_tmdb-tv"])

        return sorted_res

    async def _fetch_basic_info_from_tmdb_api(self, tmdb_ids: List[str], media_type: str) -> List[Dict[str, Any]]:
        tmdb_key = self.configuration_service.get("tmdb_api_key")
        if not tmdb_key: return []
        items = []
        async with httpx.AsyncClient() as client:
            for tmdb_id in tmdb_ids:
                try:
                    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={tmdb_key}&language=zh-CN"
                    res = await client.get(url, timeout=5.0)
                    if res.status_code == 200:
                        data = res.json()
                        name = data.get('title') if media_type == 'movie' else data.get('name')
                        date = data.get('release_date') if media_type == 'movie' else data.get('first_air_date')
                        items.append({
                            'id': str(data['id']),
                            'type': 'tmdb-movies2' if media_type == 'movie' else 'tmdb-tv',
                            'name': name or '未知',
                            'year': date.split('-')[0] if date else 'N/A',
                            'poster_path': f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get('poster_path') else None,
                            'source': 'tmdb_api'
                        })
                except Exception: pass
        return items
