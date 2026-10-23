import os
import shutil
import random
import asyncio
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from app import globals
from app.services.styles.circle_focus import generate_style_circle_focus
from app.services.styles.fan import generate_style_fan
from app.services.styles.single import generate_style_single
from app.services.styles.streaming_hero import generate_style_streaming_hero
from app.services.styles.torn_paper import generate_style_torn_paper
from app.services.styles.ink_brush import generate_style_ink_brush
from app.services.styles.style_3d_float import generate_style_3d_float
from app.services.styles.cyber_glitch import generate_style_cyber_glitch
from app.logger import log_audit


class CollectionPosterService:
    def __init__(self):
        self.fonts_dir = Path("app/static/fonts")
        self.temp_dir = Path("app/static/temp_collection_posters")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
    def get_font_path(self, font_name: str) -> str:
        # Default fallback
        default_font = self.fonts_dir / "josefinsans.woff2" 
        
        if not font_name: 
            return str(default_font) if default_font.exists() else ""
            
        if os.path.exists(font_name): 
            return font_name
            
        font_path = self.fonts_dir / font_name
        if font_path.exists(): 
            return str(font_path)
            
        # Try finding with suffix or case insensitive
        for file in self.fonts_dir.iterdir():
            if file.name.lower() == font_name.lower(): 
                return str(file)
                
        log_audit("合集海报", "处理", f"未找到字体: {font_name}，将使用默认字体。", level="WARN")
        return str(default_font) if default_font.exists() else ""

    async def download_collection_images(self, collection_id: Optional[str] = None, item_ids: Optional[List[str]] = None, count: int = 20, seed: Optional[int] = None, titles_map: Optional[Dict[str, List[str]]] = None, movie_ids: Optional[List[str]] = None, series_ids: Optional[List[str]] = None) -> Tuple[List[str], Path]:
        if not globals.service or not globals.service.emby_client:
            raise RuntimeError("Emby Client not connected")
        
        items = []
        
        # 优先使用分开的 movie_ids / series_ids（避免试错搜索）
        if movie_ids or series_ids:
            resolved_emby_items = []
            
            # 并行搜索电影和剧集，各搜各的类型
            movie_task = globals.service.emby_client.get_emby_item_ids_from_tmdb_ids(movie_ids or [], "Movie", titles_map) if movie_ids else None
            series_task = globals.service.emby_client.get_emby_item_ids_from_tmdb_ids(series_ids or [], "Series", titles_map) if series_ids else None
            
            results = await asyncio.gather(
                movie_task or asyncio.sleep(0, result={}),
                series_task or asyncio.sleep(0, result={})
            )
            map_movies, map_series = results[0], results[1]
            
            for tid, eid in {**map_movies, **map_series}.items():
                resolved_emby_items.append({"Id": eid, "ImageTags": {"Primary": "ForceCheck"}})
            
            log_audit("合集海报", "处理", f"从 {len(movie_ids or [])} 电影 + {len(series_ids or [])} 剧集中解析出 {len(resolved_emby_items)} 个 Emby 项目。")
            items = resolved_emby_items
            
        elif item_ids:
            # 兼容旧接口：混在一起试错（先 Movie 再 Series）
            tmdb_ids = [i for i in item_ids if i.isdigit()]
            emby_ids = [i for i in item_ids if not i.isdigit()]
            
            resolved_emby_items = []
            
            # 1. Use existing Emby IDs directly
            if emby_ids:
                resolved_emby_items.extend([{"Id": i, "ImageTags": {"Primary": "ForceCheck"}} for i in emby_ids])
                
            # 2. Resolve TMDB IDs (通过统一入口，传入 titles_map 启用标题优先搜索)
            if tmdb_ids:
                # Batch find movies
                map_movies = await globals.service.emby_client.get_emby_item_ids_from_tmdb_ids(tmdb_ids, "Movie", titles_map)
                
                # Identify missing
                found_tmdb_ids = set(map_movies.keys())
                missing_tmdb_ids = [tid for tid in tmdb_ids if tid not in found_tmdb_ids]
                
                # Batch find series for missing
                map_series = {}
                if missing_tmdb_ids:
                     map_series = await globals.service.emby_client.get_emby_item_ids_from_tmdb_ids(missing_tmdb_ids, "Series", titles_map)
                
                # Combine
                for tid, eid in map_movies.items():
                    resolved_emby_items.append({"Id": eid, "ImageTags": {"Primary": "ForceCheck"}})
                    
                for tid, eid in map_series.items():
                    resolved_emby_items.append({"Id": eid, "ImageTags": {"Primary": "ForceCheck"}})
                    
                log_audit("合集海报", "处理", f"从 {len(tmdb_ids)} 个 TMDB ID 中解析出 {len(resolved_emby_items)} 个 Emby 项目。")
            items = resolved_emby_items
            
        elif collection_id:
            # Get items in collection
            items = await globals.service.emby_client.get_collection_items(collection_id)
            
            # If no items found, try fetching children directly
            if not items:
                data, err = await globals.service.emby_client._make_request(
                    "GET", "/Items", 
                    params={"ParentId": collection_id, "Limit": 100, "ImageTypes": "Primary", "Recursive": "true", "IncludeItemTypes": "Movie,Series"}
                )
                if data and data.get("Items"):
                    items = data["Items"]
        
        if not items:
            log_audit("合集海报", "处理", f"合集 {collection_id} 未找到任何项目。", level="WARN")
            return [], None

        # Filter items that have Primary image
        valid_items = items
        if not item_ids:
             valid_items = [i for i in items if i.get("ImageTags", {}).get("Primary")]
        
        if not valid_items:
             log_audit("合集海报", "处理", f"合集 {collection_id} 中没有带封面的项目。", level="WARN")
             return [], None

        # Shuffle and pick with optional seed
        if seed is not None:
            log_audit("合集海报", "开始", f"正在随机打乱 {len(valid_items)} 个项目，种子: {seed}")
            random.Random(seed).shuffle(valid_items)
        else:
            random.shuffle(valid_items)
            
        selected = valid_items[:count]
        log_audit("合集海报", "处理", f"已选中用于海报生成的项目 ID: {[i.get('Id') for i in selected]}")
        task_id = str(uuid.uuid4())
        task_dir = self.temp_dir / task_id
        task_dir.mkdir(exist_ok=True)
        
        log_audit("合集海报", "开始", f"开始为合集海报下载 {len(selected)} 张图片...")
        async def dl(item):
            item_id = item["Id"]
            path = task_dir / f"{item_id}.jpg"
            # Download Primary
            success = await globals.service.emby_client.download_image_for_item(item_id, "Primary", str(path))
            if success:
                return str(path)
            return None

        results = await asyncio.gather(*[dl(i) for i in selected])
        downloaded_paths = [r for r in results if r]
        
        log_audit("合集海报", "完成", f"图片下载完成，成功获取 {len(downloaded_paths)} 张。")
        return downloaded_paths, task_dir

    async def generate_poster(self, 
                              collection_id: Optional[str], 
                              style_type: str,
                              title_zh: str,
                              title_en: str,
                              font_zh: str,
                              font_en: str,
                              zh_font_size_ratio: float = 1.0,
                              en_font_size_ratio: float = 1.0,
                              offset_x: int = 0,
                              offset_y: int = 0,
                              resolution_scale: float = 1.0,
                              return_layers: bool = False,
                              item_ids: Optional[List[str]] = None,
                              seed: Optional[int] = None,
                              titles_map: Optional[Dict[str, List[str]]] = None,
                              movie_ids: Optional[List[str]] = None,
                              series_ids: Optional[List[str]] = None) -> Any:
        
        task_dir = None
        try:
            image_paths, task_dir = await self.download_collection_images(collection_id, item_ids, seed=seed, titles_map=titles_map, movie_ids=movie_ids, series_ids=series_ids)
            
            if not image_paths:
                log_audit("合集海报", "下载", f"无法下载合集 {collection_id} 的图片。", level="ERROR")
                return None

            zh_font_path = self.get_font_path(font_zh)
            en_font_path = self.get_font_path(font_en)
            
            loop = asyncio.get_running_loop()
            
            style_map = {
                "circle_focus": generate_style_circle_focus,
                "fan": generate_style_fan,
                "single": generate_style_single,
                "streaming_hero": generate_style_streaming_hero,
                "torn_paper": generate_style_torn_paper,
                "ink_brush": generate_style_ink_brush,
                "3d_float": generate_style_3d_float,
                "cyber_glitch": generate_style_cyber_glitch
            }
            
            style_func = style_map.get(style_type)
            if not style_func:
                log_audit("合集海报", "处理", f"未知样式类型: {style_type}", level="ERROR")
                raise ValueError(f"未知样式: {style_type}")

            log_audit("合集海报", "开始", f"开始执行海报生成算法 (样式: {style_type})...")
            result = await loop.run_in_executor(
                None, 
                style_func,
                image_paths,
                title_zh,
                title_en,
                (zh_font_path, en_font_path), 
                zh_font_size_ratio,
                en_font_size_ratio,
                offset_x,
                offset_y,
                resolution_scale,
                return_layers,
                seed
            )
            
            if result:
                log_audit("合集海报", "完成", "海报生成成功。")
            return result

        except Exception as e:
            log_audit("合集海报", "失败", f"生成海报时出错: {e}", level="ERROR")
            return None
        finally:
            if task_dir and task_dir.exists():
                try:
                    shutil.rmtree(task_dir)
                except Exception as e:
                    log_audit("合集海报", "清理", f"无法清理临时目录 {task_dir}: {e}", level="WARN")
    async def batch_generate_posters_task(self, collection_filenames: List[str], params: Dict[str, Any]):
        """
        Background task to generate posters for multiple collections.
        params: style_type, show_zh, show_en, font_zh, font_en, etc.
        """
        from app.websocket_manager import manager
        from app.common import sanitize_filename
        
        total = len(collection_filenames)
        await manager.broadcast_progress("batch_poster", "running", 0, total, f"开始处理 {total} 个合集...")
        
        success_count = 0
        fail_count = 0
        
        for i, filename in enumerate(collection_filenames):
            try:
                # 1. Load collection details to get items and title
                details = await globals.collection_service.get_collection_details(filename)
                if not details:
                    fail_count += 1
                    continue
                
                collection_name = details.get("collection_name", "Unknown")
                
                await manager.broadcast_progress("batch_poster", "running", i+1, total, f"正在生成: {collection_name}")
                
                # 2. Extract items
                movies = details.get("movies", [])
                series = details.get("series", [])
                movie_ids = [str(m.get("id")) for m in movies if m.get("id")]
                series_ids = [str(s.get("id")) for s in series if s.get("id")]
                
                # 构建 titles_map 供统一入口启用标题优先搜索
                titles_map = {}
                for m in movies:
                    if m.get("id") and m.get("name"):
                        titles_map[str(m.get("id"))] = [m.get("name")]
                for s in series:
                    if s.get("id") and s.get("name"):
                        titles_map[str(s.get("id"))] = [s.get("name")]
                
                if not (movie_ids or series_ids):
                    log_audit("合集海报", "跳过", f"合集 {collection_name} 为空，跳过海报生成。", level="WARN")
                    fail_count += 1
                    continue
                
                # 3. Prepare titles
                title_zh = collection_name if params.get("show_zh") else ""
                title_en = collection_name if params.get("show_en") else "" # Or try to find English name? For now use same name if show_en is True
                # Ideally, we should allow user to specify if they want to try translation or just use collection name.
                # The single generator uses collection name for both by default.
                
                # 4. Generate Poster (get Base64 string)
                # Ensure seed is random for each if not specified, or consistent?
                # Usually we want random for each collection to look different unless user forced a seed.
                # But batch usually implies unique look. Let's use random seed per collection.
                seed = params.get("seed") if params.get("seed") is not None else random.randint(0, 1000000)
                
                base64_image = await self.generate_poster(
                    collection_id=None,
                    movie_ids=movie_ids,
                    series_ids=series_ids,
                    titles_map=titles_map if titles_map else None,
                    style_type=params.get("style_type", "circle_focus"),
                    title_zh=title_zh,
                    title_en=title_en,
                    font_zh=params.get("font_zh"),
                    font_en=params.get("font_en"),
                    zh_font_size_ratio=params.get("zh_font_size_ratio", 1.0),
                    en_font_size_ratio=params.get("en_font_size_ratio", 1.0),
                    offset_x=params.get("offset_x", 0),
                    offset_y=params.get("offset_y", 0),
                    resolution_scale=params.get("resolution_scale", 1.0),
                    return_layers=False,
                    seed=seed
                )
                
                if base64_image:
                    # 5. Save image to disk
                    # Convert Base64 to bytes
                    import base64
                    image_data = base64.b64decode(base64_image)
                    
                    success, msg = await globals.collection_service.save_collection_image(filename, "poster", image_data)
                    if success:
                        success_count += 1
                    else:
                        log_audit("合集海报", "失败", f"保存 {collection_name} 的图片失败: {msg}", level="ERROR")
                        fail_count += 1
                else:
                    fail_count += 1
                    
            except Exception as e:
                log_audit("合集海报", "失败", f"处理 {filename} 时出错: {e}", level="ERROR")
                fail_count += 1
                
        await manager.broadcast_progress("batch_poster", "completed", total, total, f"批量生成完成: {success_count} 成功, {fail_count} 失败")

collection_poster_service = CollectionPosterService()