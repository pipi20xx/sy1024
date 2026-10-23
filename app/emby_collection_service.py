# app/emby_collection_service.py

import os
import json
from typing import List, Dict, Tuple, Optional
import asyncio
from datetime import datetime
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from .common import sanitize_filename
from .websocket_manager import manager
from .models import LocalCollection
from .database import get_collections_db
from .logger import log_audit

class EmbyCollectionService:
    """
    A service for handling Emby custom collections, now backed by a SQLite index (collections.db)
    for high performance, while keeping JSON files as the ground truth for content.
    """
    def __init__(self, collections_path: Optional[str], system_service: 'SystemService'):
        self.collections_path = None
        if collections_path and os.path.isdir(collections_path):
            self.collections_path = os.path.normpath(collections_path)
            log_audit("合集", "初始化", f"EmbyCollectionService 初始化成功，目录: {self.collections_path}", level="SUCCESS")
        else:
            log_audit("合集", "初始化", f"初始化警告: 目录 '{collections_path}' 无效或未设置", level="WARN")
        
        self.system_service = system_service
        self._item_to_collection_index = {} # Reverse index: item_id -> list of collection names
        self._collection_to_items_index = {} # Forward index: collection_name -> list of item_ids
        self._collection_name_to_info = {} # Collection name -> {filename, poster_path} for detail display

    async def _initial_sync(self):
        """Perform a full sync from disk to DB on startup."""
        log_audit("合集", "同步", "正在开始初始合集数据库同步", level="START")
        await self.sync_db_from_disk()
        await self._build_reverse_index()
        log_audit("合集", "同步", "初始合集数据库同步完成", level="DONE")

    async def _build_reverse_index(self):
        """Rebuilds the in-memory reverse index (Item ID -> Collection Names) from JSON files."""
        if not self.collections_path:
            log_audit("合集", "索引", "未设置合集路径！无法构建索引", level="ERROR")
            return

        log_audit("合集", "索引", f"正在从路径构建反向索引: {self.collections_path}", level="START")
        if not os.path.exists(self.collections_path):
             log_audit("合集", "索引", f"磁盘上不存在合集路径: {self.collections_path}", level="ERROR")
             return

        new_index = {}
        new_forward_index = {}
        new_name_to_info = {}
        try:
            filenames = await asyncio.to_thread(self._list_files_sync, self.collections_path)
            json_files = [f for f in filenames if f.lower().endswith('.json')]
            log_audit("合集", "索引", f"发现 {len(json_files)} 个 JSON 合集文件")

            for filename in json_files:
                filepath = os.path.join(self.collections_path, filename)
                try:
                    data = await asyncio.to_thread(self._read_json_file_sync, filepath)
                    collection_name = data.get("collection_name")
                    if not collection_name: continue

                    # Build collection info for detail display
                    base_name = sanitize_filename(collection_name)
                    poster_filename = f"{base_name}_poster.jpg"
                    poster_path = f"/api/emby-collections/images/{poster_filename}" if os.path.isfile(os.path.join(self.collections_path, poster_filename)) else None
                    new_name_to_info[collection_name] = {
                        "filename": filename,
                        "collection_name": collection_name,
                        "poster_path": poster_path,
                    }

                    # Process movies and series
                    new_forward_index[collection_name] = []
                    for item in data.get("movies", []) + data.get("series", []):
                        item_id = str(item.get("id"))
                        if item_id:
                            if item_id not in new_index:
                                new_index[item_id] = []
                            new_index[item_id].append(collection_name)
                            new_forward_index[collection_name].append(item_id)
                    # logger.debug(f"Indexed {count} items from {filename}")
                except Exception as e:
                    log_audit("合集", "索引", f"读取 {filename} 构建反向索引时出错: {e}", level="WARN")
            
            self._item_to_collection_index = new_index
            self._collection_to_items_index = new_forward_index
            self._collection_name_to_info = new_name_to_info
            log_audit("合集", "索引", f"反向合集索引已重建，共索引 {len(new_index)} 个项目", level="SUCCESS")
        except Exception as e:
            log_audit("合集", "索引", f"构建反向合集索引时出错: {e}", level="ERROR")

    async def _update_reverse_index_for_collection(self, collection_name: str, items: List[Dict], old_collection_name: Optional[str] = None):
        """Incrementally updates the reverse index for a single collection."""
        # 1. Remove old entries using forward index if available
        name_to_remove = old_collection_name or collection_name
        if name_to_remove in self._collection_to_items_index:
            for item_id in self._collection_to_items_index[name_to_remove]:
                if item_id in self._item_to_collection_index:
                    if name_to_remove in self._item_to_collection_index[item_id]:
                        self._item_to_collection_index[item_id].remove(name_to_remove)
                    if not self._item_to_collection_index[item_id]:
                        del self._item_to_collection_index[item_id]
            del self._collection_to_items_index[name_to_remove]

        # 2. Remove old info entry if renamed
        if old_collection_name and old_collection_name in self._collection_name_to_info:
            del self._collection_name_to_info[old_collection_name]

        # 3. Add new entries
        if collection_name:
            self._collection_to_items_index[collection_name] = []
            # Update collection info cache
            base_name = sanitize_filename(collection_name)
            poster_filename = f"{base_name}_poster.jpg"
            poster_path = f"/api/emby-collections/images/{poster_filename}" if os.path.isfile(os.path.join(self.collections_path, poster_filename)) else None if self.collections_path else None
            self._collection_name_to_info[collection_name] = {
                "filename": f"{base_name}.json",
                "collection_name": collection_name,
                "poster_path": poster_path,
            }
            for item in items:
                item_id = str(item.get("id"))
                if item_id:
                    if item_id not in self._item_to_collection_index:
                        self._item_to_collection_index[item_id] = []
                    if collection_name not in self._item_to_collection_index[item_id]:
                        self._item_to_collection_index[item_id].append(collection_name)
                    self._collection_to_items_index[collection_name].append(item_id)

    # --- Helper methods for Async I/O ---
    def _read_json_file_sync(self, filepath: str) -> Dict:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_json_file_sync(self, filepath: str, data: Dict):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _delete_file_sync(self, filepath: str):
        if os.path.isfile(filepath):
            os.remove(filepath)

    def _write_binary_file_sync(self, filepath: str, content: bytes):
        with open(filepath, 'wb') as f:
            f.write(content)

    def _list_files_sync(self, path: str) -> List[str]:
        return os.listdir(path)

    # --- Core DB Sync Logic ---
    async def sync_db_from_disk(self):
        """
        Scans all JSON files in collections_path and updates the SQLite index.
        Removes DB entries for files that no longer exist.
        """
        if not self.collections_path:
            return

        try:
            # 1. Scan disk
            filenames = await asyncio.to_thread(self._list_files_sync, self.collections_path)
            json_files = [f for f in filenames if f.lower().endswith('.json')]
            
            disk_collections = {}
            for filename in json_files:
                filepath = os.path.join(self.collections_path, filename)
                try:
                    data = await asyncio.to_thread(self._read_json_file_sync, filepath)
                    collection_name = data.get("collection_name", os.path.splitext(filename)[0])
                    
                    # Check for poster
                    base_name = sanitize_filename(collection_name)
                    poster_filename = f"{base_name}_poster.jpg"
                    poster_path = f"/api/emby-collections/images/{poster_filename}" if os.path.isfile(os.path.join(self.collections_path, poster_filename)) else None
                    
                    disk_collections[filename] = {
                        "filename": filename,
                        "collection_name": collection_name,
                        "tmdb_collection_id": data.get("tmdb_collection_id"),
                        "movie_count": len(data.get("movies", [])),
                        "series_count": len(data.get("series", [])),
                        "poster_path": poster_path,
                        "created_at": datetime.now().isoformat(), # Rough approx if new
                        "updated_at": datetime.now().isoformat()
                    }
                except Exception as e:
                    log_audit("合集", "同步", f"同步期间解析 {filename} 时出错: {e}", level="ERROR")

            # 2. Update DB
            async for session in get_collections_db():
                # TRUNCATE / DELETE ALL first for a 100% clean state
                await session.execute(delete(LocalCollection))
                
                # Bulk Insert
                new_entries = []
                for filename, data in disk_collections.items():
                    new_entries.append(LocalCollection(**data))
                
                if new_entries:
                    session.add_all(new_entries)
                
                await session.commit()
                log_audit("合集", "同步", f"数据库同步完成，重置了 {len(new_entries)} 个条目", level="SUCCESS")
                
        except Exception as e:
            log_audit("合集", "同步", f"数据库同步期间发生严重错误: {e}", level="ERROR")

    # --- Public API ---

    async def get_all_collections(self) -> List[Dict]:
        """
        Returns collection metadata from SQLite index. Fast and efficient.
        """
        if not self.collections_path:
            return []

        async for session in get_collections_db():
            result = await session.execute(select(LocalCollection).order_by(LocalCollection.collection_name))
            collections = result.scalars().all()
            return [c.to_dict() for c in collections]
        return []

    async def get_collection_details(self, filename: str) -> Optional[Dict]:
        """
        Reads the full JSON content for details (movies list, etc).
        """
        if not self.collections_path or not filename:
            return None

        filepath = os.path.join(self.collections_path, filename)
        if not os.path.isfile(filepath):
            return None
        
        try:
            return await asyncio.to_thread(self._read_json_file_sync, filepath)
        except Exception as e:
            log_audit("合集", "读取", f"读取 {filename} 详情时出错: {e}", level="ERROR")
            return None

    def get_collections_by_item(self, item_id: str) -> List[Dict]:
        """
        Returns a list of collection info dicts that the given item (TMDB ID) belongs to.
        Each dict contains: collection_name, filename, poster_path
        """
        collection_names = self._item_to_collection_index.get(str(item_id), [])
        result = []
        for name in collection_names:
            info = self._collection_name_to_info.get(name, {})
            result.append({
                "collection_name": name,
                "filename": info.get("filename", f"{sanitize_filename(name)}.json"),
                "poster_path": info.get("poster_path"),
            })
        return result

    async def save_collection(self, collection_data: Dict, original_filename: Optional[str] = None, overwrite: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        Saves collection to JSON and updates SQLite index immediately.
        """
        if not self.collections_path:
            return False, "未设置合集路径。", None

        collection_name = collection_data.get("collection_name", "").strip()
        if not collection_name:
            return False, "合集名称不能为空。", None

        new_base = sanitize_filename(collection_name)
        new_filename = f"{new_base}.json"
        new_filepath = os.path.join(self.collections_path, new_filename)

        # Conflict check
        if not overwrite:
            if original_filename and original_filename.lower() != new_filename.lower() and os.path.exists(new_filepath):
                return False, f"文件名 '{new_filename}' 已存在。", None
            if not original_filename and os.path.exists(new_filepath):
                return False, f"合集 '{collection_name}' 已存在。", None

        try:
            # 1. Write JSON
            await asyncio.to_thread(self._write_json_file_sync, new_filepath, collection_data)
            
            # 2. Handle Rename (Delete old file)
            if original_filename and original_filename.lower() != new_filename.lower():
                old_filepath = os.path.join(self.collections_path, original_filename)
                if os.path.isfile(old_filepath):
                    await asyncio.to_thread(self._delete_file_sync, old_filepath)

            # 3. Update DB
            async for session in get_collections_db():
                # If renamed, delete old entry first
                if original_filename and original_filename.lower() != new_filename.lower():
                    await session.execute(delete(LocalCollection).where(LocalCollection.filename == original_filename))
                
                # Check for image
                poster_filename = f"{new_base}_poster.jpg"
                poster_path = f"/api/emby-collections/images/{poster_filename}" if os.path.isfile(os.path.join(self.collections_path, poster_filename)) else None

                # Upsert new entry
                result = await session.execute(select(LocalCollection).where(LocalCollection.filename == new_filename))
                existing = result.scalar_one_or_none()

                if existing:
                    existing.collection_name = collection_name
                    existing.tmdb_collection_id = collection_data.get("tmdb_collection_id")
                    existing.movie_count = len(collection_data.get("movies", []))
                    existing.series_count = len(collection_data.get("series", []))
                    existing.poster_path = poster_path
                    existing.updated_at = datetime.now().isoformat()
                else:
                    new_entry = LocalCollection(
                        filename=new_filename,
                        collection_name=collection_name,
                        tmdb_collection_id=collection_data.get("tmdb_collection_id"),
                        movie_count=len(collection_data.get("movies", [])),
                        series_count=len(collection_data.get("series", [])),
                        poster_path=poster_path,
                        created_at=datetime.now().isoformat(),
                        updated_at=datetime.now().isoformat()
                    )
                    session.add(new_entry)
                
                await session.commit()

            # Update reverse index incrementally
            old_name = None
            if original_filename and original_filename.lower() != new_filename.lower():
                old_name = os.path.splitext(original_filename)[0] # Best guess if we don't have old data
            
            all_items = collection_data.get("movies", []) + collection_data.get("series", [])
            await self._update_reverse_index_for_collection(collection_name, all_items, old_name)

            return True, "合集已保存。", new_filename

        except Exception as e:
            log_audit("合集", "保存", f"保存合集 {new_filename} 时出错: {e}", level="ERROR")
            return False, str(e), None

    async def delete_collection(self, filename: str) -> Tuple[bool, str]:
        if not self.collections_path or not filename:
            return False, "路径或文件名无效。"

        filepath = os.path.join(self.collections_path, filename)
        
        try:
            # 1. Delete JSON
            if os.path.isfile(filepath):
                await asyncio.to_thread(self._delete_file_sync, filepath)
            
            # 2. Delete associated images
            base_name = os.path.splitext(filename)[0]
            suffixes = ["_poster.jpg", "_fanart.jpg", "_logo.png"]
            for suffix in suffixes:
                image_path = os.path.join(self.collections_path, f"{base_name}{suffix}")
                if os.path.isfile(image_path):
                    try:
                        await asyncio.to_thread(self._delete_file_sync, image_path)
                        log_audit("合集", "删除", f"已删除关联图片: {image_path}", level="CLEAN")
                    except Exception as e:
                        log_audit("合集", "删除", f"删除图片 {image_path} 失败: {e}", level="WARN")

            # 3. Delete from DB
            async for session in get_collections_db():
                await session.execute(delete(LocalCollection).where(LocalCollection.filename == filename))
                await session.commit()
            
            # Update reverse index incrementally (remove this collection)
            collection_name = base_name # Fallback
            await self._update_reverse_index_for_collection("", [], old_collection_name=collection_name)
            
            return True, "合集已删除。"
        except Exception as e:
            log_audit("合集", "删除", f"删除 {filename} 时出错: {e}", level="ERROR")
            return False, str(e)

    async def save_collection_image(self, collection_filename: str, image_type: str, file_content: bytes) -> Tuple[bool, str]:
        if not self.collections_path: return False, "无路径。"
        
        base_name = os.path.splitext(collection_filename)[0]
        suffix_map = {"poster": "_poster.jpg", "backdrop": "_fanart.jpg", "logo": "_logo.png"}
        suffix = suffix_map.get(image_type.lower())
        
        if not suffix: return False, "无效的图片类型。"
        
        image_filename = f"{base_name}{suffix}"
        image_path = os.path.join(self.collections_path, image_filename)
        
        try:
            await asyncio.to_thread(self._write_binary_file_sync, image_path, file_content)
            
            # Update DB if it's a poster
            if image_type.lower() == "poster":
                async for session in get_collections_db():
                    result = await session.execute(select(LocalCollection).where(LocalCollection.filename == collection_filename))
                    entry = result.scalar_one_or_none()
                    if entry:
                        entry.poster_path = f"/api/emby-collections/images/{image_filename}"
                        entry.updated_at = datetime.now().isoformat()
                        await session.commit()
            
            return True, "图片已保存。"
        except Exception as e:
            log_audit("合集", "保存", f"保存图片时出错: {e}", level="ERROR")
            return False, str(e)

    # --- Emby Integration Methods (Apply / Import) ---
    
    async def import_all_collections_from_emby(self, overwrite_json: bool, overwrite_images: bool):
        # ... (Reuse existing logic but ensure save_collection is called to update DB)
        # Note: save_collection already updates DB, so we just need to use it.
        # For bulk import, we might want to optimize DB writes, but reusing save_collection is safer for consistency.
        
        if not self.system_service or not self.system_service.emby_client:
            await manager.broadcast_progress("import_collection", "error", 0, 0, "Emby 客户端未就绪。")
            return

        emby_client = self.system_service.emby_client
        try:
            all_emby_collections = await emby_client.get_all_collections()
        except Exception as e:
            await manager.broadcast_progress("import_collection", "error", 0, 0, str(e))
            return

        total = len(all_emby_collections)
        await manager.broadcast_progress("import_collection", "running", 0, total, f"发现 {total} 个合集。")

        for i, collection in enumerate(all_emby_collections):
            name = collection.get("Name")
            cid = collection.get("Id")
            if not name or not cid: continue
            
            try:
                await manager.broadcast_progress("import_collection", "running", i+1, total, f"正在导入: {name}")
                
                # Fetch items
                items = await emby_client.get_collection_items(cid)
                movies = [{"id": str(x.get("ProviderIds", {}).get("Tmdb")), "name": x.get("Name","")} for x in items if x.get("Type")=="Movie" and x.get("ProviderIds", {}).get("Tmdb")]
                series = [{"id": str(x.get("ProviderIds", {}).get("Tmdb")), "name": x.get("Name","")} for x in items if x.get("Type")=="Series" and x.get("ProviderIds", {}).get("Tmdb")]
                
                data = {
                    "collection_name": name,
                    "tmdb_collection_id": collection.get("ProviderIds", {}).get("TmdbCollection", ""),
                    "movies": movies,
                    "series": series
                }
                
                # Save (handles JSON + DB)
                # Logic: If overwrite_json is True, OR file doesn't exist.
                # Since save_collection checks existence internally if overwrite=False, we can just set overwrite based on logic
                # But save_collection's overwrite param is strict.
                # Let's check existence first.
                base_name = sanitize_filename(name)
                fname = f"{base_name}.json"
                fpath = os.path.join(self.collections_path, fname)
                
                if overwrite_json or not os.path.exists(fpath):
                    await self.save_collection(data, overwrite=True)
                
                # Images
                if overwrite_images or not os.path.exists(os.path.join(self.collections_path, f"{base_name}_poster.jpg")):
                    # We need to trigger DB update if poster changes, but download_image_for_item doesn't go through save_collection_image
                    # So we should call save_collection_image wrapper or manually update DB?
                    # Better: download content then call save_collection_image
                    # Or: just let _sync_db_from_disk handle it on restart? No, better to be consistent.
                    # Since emby_client.download_image_for_item saves directly to disk, we need to update DB manually or wrap it.
                    # Let's use helper to update DB after download.
                    
                    types = {"Primary": "poster", "Backdrop": "backdrop", "Logo": "logo"}
                    for etype, ltype in types.items():
                        # We use a temp method or just call DB update directly? 
                        # To keep it simple, we'll let the user manually refresh or trigger a quick sync for this item.
                        # OR: just update DB here.
                         await emby_client.download_image_for_item(cid, etype, os.path.join(self.collections_path, f"{base_name}{self._get_suffix(ltype)}"))
                         if ltype == 'poster':
                             # Update DB
                             async for session in get_collections_db():
                                 res = await session.execute(select(LocalCollection).where(LocalCollection.filename == fname))
                                 entry = res.scalar_one_or_none()
                                 if entry:
                                     entry.poster_path = f"/api/emby-collections/images/{base_name}_poster.jpg"
                                     await session.commit()
            
            except Exception as e:
                log_audit("合集", "导入", f"导入错误 {name}: {e}", level="ERROR")

        await manager.broadcast_progress("import_collection", "completed", total, total, "导入完成。")

    def _get_suffix(self, ltype):
        return {"poster": "_poster.jpg", "backdrop": "_fanart.jpg", "logo": "_logo.png"}.get(ltype, "")

    async def import_collection_from_emby(self, collection_name: str, overwrite_json: bool, overwrite_images: bool) -> Tuple[bool, str, Optional[Dict]]:
        # Reuse logic similarly
        if not self.system_service.emby_client: return False, "无客户端", None
        emby_client = self.system_service.emby_client
        
        col = await emby_client.find_collection_by_name(collection_name)
        if not col: return False, "未找到", None
        
        cid = col.get("Id")
        items = await emby_client.get_collection_items(cid)
        movies = [{"id": str(x.get("ProviderIds", {}).get("Tmdb")), "name": x.get("Name","")} for x in items if x.get("Type")=="Movie"]
        series = [{"id": str(x.get("ProviderIds", {}).get("Tmdb")), "name": x.get("Name","")} for x in items if x.get("Type")=="Series"]
        
        data = {
            "collection_name": collection_name,
            "tmdb_collection_id": col.get("ProviderIds", {}).get("TmdbCollection", ""),
            "movies": movies, "series": series
        }
        
        base_name = sanitize_filename(collection_name)
        fname = f"{base_name}.json"
        
        # Save JSON/DB
        if overwrite_json or not os.path.exists(os.path.join(self.collections_path, fname)):
            await self.save_collection(data, overwrite=True)
            
        # Images
        types = {"Primary": "poster", "Backdrop": "backdrop", "Logo": "logo"}
        for etype, ltype in types.items():
            fpath = os.path.join(self.collections_path, f"{base_name}{self._get_suffix(ltype)}")
            if overwrite_images or not os.path.exists(fpath):
                await emby_client.download_image_for_item(cid, etype, fpath)
                if ltype == 'poster':
                    async for session in get_collections_db():
                        res = await session.execute(select(LocalCollection).where(LocalCollection.filename == fname))
                        entry = res.scalar_one_or_none()
                        if entry:
                            entry.poster_path = f"/api/emby-collections/images/{base_name}_poster.jpg"
                            await session.commit()
                            
        # Return details
        return True, "已导入", await self.get_collection_details(fname) or data

    async def sync_single_collection_from_emby_by_name(self, collection_name: str) -> Tuple[bool, str]:
        # Called by Webhook
        success, message, _ = await self.import_collection_from_emby(collection_name, overwrite_json=True, overwrite_images=False)
        return success, message

    # --- Re-implement apply_all / apply_single (Generators) ---
    # These interact with Emby Server, logic is mostly unchanged but ensure we read from disk (which is synced).
    # Since they read using _read_json_file_sync, they are fine.
    
    async def apply_all_collections_to_emby(self):
        # ... (Same logic as before, just yielding status)
        # I'll paste the previous logic but keep it clean.
        if not self.system_service.emby_client:
            yield {"status": "error", "message": "无 Emby 客户端"}
            return
        
        # ... (Scanning disk is fine here as we want to apply what is physically on disk)
        # ... (Copy-paste the fixed logic from previous turn)
        # Since I'm replacing the whole file, I need to include the full implementation.
        
        emby_client = self.system_service.emby_client
        files = await asyncio.to_thread(self._list_files_sync, self.collections_path)
        json_files = [f for f in files if f.endswith('.json')]
        total = len(json_files)
        yield {"status": "progress", "message": f"发现 {total} 个合集", "current": 0, "total": total}
        
        for i, fname in enumerate(json_files):
            try:
                data = await asyncio.to_thread(self._read_json_file_sync, os.path.join(self.collections_path, fname))
                cname = data.get("collection_name")
                if not cname: continue
                
                yield {"status": "progress", "message": f"正在处理 {cname}...", "current": i, "total": total}
                
                # IDs
                movies = data.get('movies', [])
                series = data.get('series', [])
                mids = [str(x.get('id')) for x in movies if x.get('id')]
                sids = [str(x.get('id')) for x in series if x.get('id')]
                movie_titles = {str(x.get('id')): [x.get('name')] for x in movies if x.get('id') and x.get('name')}
                series_titles = {str(x.get('id')): [x.get('name')] for x in series if x.get('id') and x.get('name')}
                
                emids = await emby_client.get_emby_item_ids_from_tmdb_ids(mids, "Movie", movie_titles)
                esids = await emby_client.get_emby_item_ids_from_tmdb_ids(sids, "Series", series_titles)
                target_ids = list(set(emids.values()) | set(esids.values()))
                
                if not target_ids:
                    yield {"status": "progress", "message": f"跳过 {cname} (未找到项目)", "current": i, "total": total}
                    continue
                    
                cid, msg = await emby_client.find_or_create_collection(cname, target_ids)
                yield {"status": "progress", "message": msg, "current": i, "total": total}
                
                if not cid: continue
                
                # Provider ID
                if data.get("tmdb_collection_id"):
                    await emby_client.set_collection_provider_id(cid, data.get("tmdb_collection_id"))
                
                # Sync items
                curr = await emby_client.get_collection_items(cid)
                curr_ids = {x.get("Id") for x in curr}
                t_ids = set(target_ids)
                
                to_add = list(t_ids - curr_ids)
                to_rem = list(curr_ids - t_ids)
                
                if to_add: await emby_client.add_items_to_collection(cid, to_add)
                if to_rem: await emby_client.remove_items_from_collection(cid, to_rem)
                
                # Images
                base = sanitize_filename(cname)
                for itype, suffix in {"Primary": "_poster.jpg", "Backdrop": "_fanart.jpg", "Logo": "_logo.png"}.items():
                    ipath = os.path.join(self.collections_path, f"{base}{suffix}")
                    if os.path.exists(ipath):
                        await emby_client.upload_collection_image(cid, itype, ipath)
                        await asyncio.sleep(0.1)
                        
            except Exception as e:
                yield {"status": "error", "message": f"文件 {fname} 出错: {e}"}
        
        yield {"status": "finished", "message": "完成。"}

    async def apply_all_collections_to_emby_task(self, target_filenames: Optional[List[str]] = None):
        """
        Background task version of apply_all_collections_to_emby using WebSocket for progress.
        If target_filenames is provided, only processes those files.
        """
        if not self.system_service.emby_client:
            await manager.broadcast_progress("import_collection", "error", 0, 0, "无 Emby 客户端")
            return
        
        emby_client = self.system_service.emby_client
        
        if target_filenames:
             json_files = [f for f in target_filenames if f.endswith('.json')]
        else:
            files = await asyncio.to_thread(self._list_files_sync, self.collections_path)
            json_files = [f for f in files if f.endswith('.json')]
            
        total = len(json_files)
        
        await manager.broadcast_progress("import_collection", "running", 0, total, f"发现 {total} 个待应用合集。")
        
        for i, fname in enumerate(json_files):
            try:
                data = await asyncio.to_thread(self._read_json_file_sync, os.path.join(self.collections_path, fname))
                cname = data.get("collection_name")
                if not cname: continue
                
                msg = f"正在应用: {cname}"
                log_audit("合集", "应用", msg)
                await manager.broadcast_progress("import_collection", "running", i+1, total, msg)
                
                # IDs
                movies = data.get('movies', [])
                series = data.get('series', [])
                mids = [str(x.get('id')) for x in movies if x.get('id')]
                sids = [str(x.get('id')) for x in series if x.get('id')]
                movie_titles = {str(x.get('id')): [x.get('name')] for x in movies if x.get('id') and x.get('name')}
                series_titles = {str(x.get('id')): [x.get('name')] for x in series if x.get('id') and x.get('name')}
                
                emids = await emby_client.get_emby_item_ids_from_tmdb_ids(mids, "Movie", movie_titles)
                esids = await emby_client.get_emby_item_ids_from_tmdb_ids(sids, "Series", series_titles)
                target_ids = list(set(emids.values()) | set(esids.values()))
                
                if not target_ids:
                    log_audit("合集", "跳过", f"跳过 {cname}: 未找到对应的 Emby 项目 ID", level="WARN")
                    # await manager.broadcast_progress("import_collection", "running", i+1, total, f"Skipping {cname} (No items)")
                    continue
                    
                cid, msg = await emby_client.find_or_create_collection(cname, target_ids)
                
                if not cid: continue
                
                # Provider ID
                if data.get("tmdb_collection_id"):
                    await emby_client.set_collection_provider_id(cid, data.get("tmdb_collection_id"))
                
                # Sync items
                curr = await emby_client.get_collection_items(cid)
                curr_ids = {x.get("Id") for x in curr}
                t_ids = set(target_ids)
                
                to_add = list(t_ids - curr_ids)
                to_rem = list(curr_ids - t_ids)
                
                if to_add: await emby_client.add_items_to_collection(cid, to_add)
                if to_rem: await emby_client.remove_items_from_collection(cid, to_rem)
                
                # Images
                base = sanitize_filename(cname)
                for itype, suffix in {"Primary": "_poster.jpg", "Backdrop": "_fanart.jpg", "Logo": "_logo.png"}.items():
                    ipath = os.path.join(self.collections_path, f"{base}{suffix}")
                    if os.path.exists(ipath):
                        await emby_client.upload_collection_image(cid, itype, ipath)
                        await asyncio.sleep(0.1)
                        
            except Exception as e:
                log_audit("合集", "应用", f"应用 {fname} 时出错: {e}", level="ERROR")
                # Don't stop, just log
        
        log_audit("合集", "应用", "合集应用任务完成", level="DONE")
        await manager.broadcast_progress("import_collection", "completed", total, total, "合集应用完成。")

    async def apply_single_collection_to_emby(self, filename: str):
         if not self.system_service.emby_client:
            yield {"status": "error", "message": "无 Emby 客户端"}
            return
         
         emby_client = self.system_service.emby_client
            
         fpath = os.path.join(self.collections_path, filename)
         if not os.path.exists(fpath):
            yield {"status": "error", "message": "文件未找到"}
            return
            
         try:
            data = await asyncio.to_thread(self._read_json_file_sync, fpath)
            cname = data.get("collection_name")
            
            log_audit("合集", "应用", f"开始应用单个合集: {cname}", level="START")
            
            movies = data.get('movies', [])
            series = data.get('series', [])
            mids = [str(x.get('id')) for x in movies if x.get('id')]
            sids = [str(x.get('id')) for x in series if x.get('id')]
            movie_titles = {str(x.get('id')): [x.get('name')] for x in movies if x.get('id') and x.get('name')}
            series_titles = {str(x.get('id')): [x.get('name')] for x in series if x.get('id') and x.get('name')}
            total_ids = len(mids) + len(sids)
            
            yield {"status": "progress", "message": f"正在查找 {len(mids)} 部电影 + {len(sids)} 部剧集的 Emby 项目...", "current": 0, "total": total_ids}
            
            # 通过 asyncio.Queue + on_progress 回调实现实时进度
            progress_q: asyncio.Queue = asyncio.Queue()

            async def _movie_cb(label: str, current: int, _total: int):
                await progress_q.put(("电影", label, current, total_ids))

            async def _series_cb(label: str, current: int, _total: int):
                await progress_q.put(("剧集", label, current + len(mids), total_ids))

            # 并行查找电影和剧集，同时通过队列向前端推送进度
            async def _empty():
                return {}

            movie_task = asyncio.create_task(
                emby_client.get_emby_item_ids_from_tmdb_ids(mids, "Movie", movie_titles, on_progress=_movie_cb)
            ) if mids else asyncio.create_task(_empty())
            series_task = asyncio.create_task(
                emby_client.get_emby_item_ids_from_tmdb_ids(sids, "Series", series_titles, on_progress=_series_cb)
            ) if sids else asyncio.create_task(_empty())

            pending = {movie_task, series_task}
            while pending:
                done, pending = await asyncio.wait(pending, timeout=0.05)
                while not progress_q.empty():
                    type_label, label, current, total = await progress_q.get()
                    yield {"status": "progress", "message": f"正在查找{type_label} {label}...", "current": current, "total": total}

            emids = movie_task.result()
            esids = series_task.result()
            target_ids = list(set(emids.values()) | set(esids.values()))
            
            if not target_ids:
                yield {"status": "finished", "message": "未找到任何对应的 Emby 项目。"}
                return
            
            yield {"status": "progress", "message": f"找到 {len(target_ids)} 个 Emby 项目，正在创建/更新合集...", "current": total_ids, "total": total_ids}
            
            cid, msg = await emby_client.find_or_create_collection(cname, target_ids)
            yield {"status": "progress", "message": msg, "current": total_ids, "total": total_ids}
            
            if cid:
                 # Provider ID
                if data.get("tmdb_collection_id"):
                    await emby_client.set_collection_provider_id(cid, data.get("tmdb_collection_id"))
                
                # Sync items
                curr = await emby_client.get_collection_items(cid)
                curr_ids = {x.get("Id") for x in curr}
                t_ids = set(target_ids)
                
                to_add = list(t_ids - curr_ids)
                to_rem = list(curr_ids - t_ids)
                
                if to_add:
                    yield {"status": "progress", "message": f"正在添加 {len(to_add)} 个项目到合集...", "current": total_ids, "total": total_ids}
                    await emby_client.add_items_to_collection(cid, to_add)
                if to_rem:
                    yield {"status": "progress", "message": f"正在移除 {len(to_rem)} 个旧项目...", "current": total_ids, "total": total_ids}
                    await emby_client.remove_items_from_collection(cid, to_rem)
                
                # Images
                base = sanitize_filename(cname)
                for itype, suffix in {"Primary": "_poster.jpg", "Backdrop": "_fanart.jpg", "Logo": "_logo.png"}.items():
                    ipath = os.path.join(self.collections_path, f"{base}{suffix}")
                    if os.path.exists(ipath):
                        yield {"status": "progress", "message": f"正在上传 {itype} 图片...", "current": total_ids, "total": total_ids}
                        await emby_client.upload_collection_image(cid, itype, ipath)
                        await asyncio.sleep(0.1)

            log_audit("合集", "应用", f"合集 {cname} 应用完成", level="SUCCESS")
            yield {"status": "finished", "message": "完成。"}
         except Exception as e:
             log_audit("合集", "应用", f"应用合集 {filename} 失败: {e}", level="ERROR")
             yield {"status": "error", "message": str(e)}
