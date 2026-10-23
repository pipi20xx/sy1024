import os
import shutil
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union
from ..common import SOURCE_OVERRIDE
from .configuration import ConfigurationService
from .scanner import ScannerService
from .editor import EditorService
from ..web_image_service import WebImageService
from .emby_integration import EmbyIntegrationService
from ..logger import log_audit


class ImageService:
    def __init__(self, configuration_service: ConfigurationService, scanner_service: ScannerService, editor_service: EditorService, web_image_service: WebImageService, emby_integration_service: EmbyIntegrationService):
        self.configuration_service = configuration_service
        self.scanner_service = scanner_service
        self.editor_service = editor_service
        self.web_image_service = web_image_service
        self.emby_integration_service = emby_integration_service

    def _get_cache_path_for_source(self, source: str) -> Optional[str]:
        return self.configuration_service.get_cache_path_for_source(source)

    def get_web_images(self, item_type: str, item_id: str, image_types: List[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        tvdb_id = None
        if item_type == 'tmdb-tv':
            # Use EditorService to find path, then read json.
            json_path = self.editor_service._get_actual_json_path("tmdb-tv", item_id, "series.json")
            if json_path and os.path.exists(json_path):
                try:
                    import json
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    tvdb_id = str(data.get("external_ids", {}).get("tvdb_id") or "") or None
                except Exception:
                    pass

        return self.web_image_service.get_available_images(item_type, item_id, image_types, tvdb_id, sources)

    async def save_web_images(self, item_type: str, item_id: str, images_to_save: List[Dict], behavior: str = "overwrite") -> Tuple[bool, str]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：覆盖缓存 (override) 目录未在设置中配置。"

        filename_map = {
            "poster": "poster.jpg",
            "fanart": "fanart.jpg",
            "logo": "clearlogo.png",
            "clearart": "clearart.png",
            "thumb": "landscape.jpg",
            "banner": "banner.jpg",
            "disc": "disc.png"
        }
        
        conflict_map = {
            "poster": ["poster.png", "poster.jpeg", "poster.webp", "folder.jpg", "folder.png"],
            "fanart": ["fanart.png", "fanart.jpeg", "fanart.webp", "backdrop.jpg", "backdrop.png"],
            "logo": ["clearlogo.jpg", "clearlogo.jpeg", "logo.png", "logo.jpg"],
            "art": ["clearart.jpg", "clearart.jpeg"],
            "thumb": ["landscape.png", "landscape.jpeg", "thumb.jpg", "thumb.png"],
            "banner": ["banner.png", "banner.jpeg"],
            "disc": ["disc.jpg", "disc.jpeg"]
        }

        target_images_dir = os.path.join(override_path, item_type, item_id, "images")
        os.makedirs(target_images_dir, exist_ok=True)

        log_audit("图片", "开始", f"[保存网络图片] Item: {item_id}, 模式: {behavior}, 数量: {len(images_to_save)}")
        success_count = 0
        error_count = 0
        skipped_count = 0
        messages = []

        for image_info in images_to_save:
            image_type = image_info.get("type") or image_info.get("label")
            image_url = image_info.get("url")
            # Fallback for 'full_url' which is what web_image_service returns
            if not image_url:
                image_url = image_info.get("full_url")

            log_audit("图片", "处理", f"[保存网络图片] 处理图片: Type={image_type}, URL={image_url}")
            if not image_type or not image_url:
                log_audit("图片", "跳过", f"[保存网络图片] 跳过 - 缺少类型或URL: {image_info}", level="WARN")
                continue

            target_filename = filename_map.get(image_type)
            if not target_filename:
                log_audit("图片", "跳过", f"[保存网络图片] 跳过 - 未知类型映射: {image_type}", level="WARN")
                continue

            save_path = os.path.join(target_images_dir, target_filename)
            
            # --- Check logic for Skip behavior ---
            if behavior == 'skip':
                # Check if target exists
                if os.path.exists(save_path):
                    skipped_count += 1
                    msg = f"跳过 {target_filename} (已存在)"
                    messages.append(msg)
                    log_audit("图片", "处理", f"[保存网络图片] {msg} - Item: {item_id}")
                    continue
                
                # Check conflicts
                base_name_no_ext = os.path.splitext(target_filename)[0]
                conflict_found = False
                # Check extensions
                for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    if os.path.exists(os.path.join(target_images_dir, base_name_no_ext + ext)):
                        conflict_found = True
                        break
                # Check synonyms
                if not conflict_found and image_type in conflict_map:
                     for conflict_name in conflict_map[image_type]:
                         if os.path.exists(os.path.join(target_images_dir, conflict_name)):
                             conflict_found = True
                             break
                
                if conflict_found:
                    skipped_count += 1
                    msg = f"跳过 {target_filename} (存在同类图片)"
                    messages.append(msg)
                    log_audit("图片", "处理", f"[保存网络图片] {msg} - Item: {item_id}")
                    continue

            temp_path = save_path + ".tmp"
            
            # WebImageService uses requests (sync), so run in thread
            success, msg = await asyncio.to_thread(self.web_image_service.download_image, image_url, temp_path)
            
            if success:
                try:
                    is_overwrite = False
                    if behavior == 'overwrite':
                        base_name_no_ext = os.path.splitext(target_filename)[0]
                        def _clean_files():
                            nonlocal is_overwrite
                            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                possible_conflict = os.path.join(target_images_dir, base_name_no_ext + ext)
                                if os.path.isfile(possible_conflict):
                                    try: 
                                        os.remove(possible_conflict)
                                        is_overwrite = True
                                    except OSError: pass

                            if image_type in conflict_map:
                                for conflict_name in conflict_map[image_type]:
                                    conflict_path = os.path.join(target_images_dir, conflict_name)
                                    if os.path.isfile(conflict_path):
                                        try: 
                                            os.remove(conflict_path)
                                            is_overwrite = True
                                        except OSError: pass
                        
                        await asyncio.to_thread(_clean_files)
                    
                    await asyncio.to_thread(shutil.move, temp_path, save_path)
                    success_count += 1
                    
                    action_str = "覆盖" if is_overwrite else "保存"
                    log_audit("图片", "完成", f"[保存网络图片] 成功{action_str}: {target_filename} - Item: {item_id}")
                except Exception as e:
                    error_count += 1
                    messages.append(f"文件操作失败 {target_filename}: {e}")
                    log_audit("图片", "失败", f"[保存网络图片] 文件移动失败 {target_filename}: {e}", level="ERROR")
                    if os.path.exists(temp_path):
                        await asyncio.to_thread(os.remove, temp_path)
            else:
                error_count += 1
                messages.append(f"下载失败 {target_filename}: {msg}")
                log_audit("图片", "失败", f"[保存网络图片] 下载失败 {target_filename}: {msg}", level="ERROR")
        await self.scanner_service._refresh_item_in_db(item_type, item_id)
        
        final_message = f"操作完成。成功: {success_count}, 跳过: {skipped_count}, 失败: {error_count}。"
        if error_count > 0:
            final_message += "\n" + "\n".join(messages)
        elif skipped_count > 0 and success_count == 0:
             final_message += " (所有项目已跳过)"
        
        return True, final_message

    def get_season_web_images(self, series_id: str, season_number: int, image_types: List[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        """获取指定季度的网络图片。"""
        return self.web_image_service.get_available_season_images(series_id, season_number, image_types, sources)

    def get_episode_web_images(self, series_id: str, season_number: int, episode_number: int, image_types: List[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        """获取指定集的网络图片。"""
        return self.web_image_service.get_available_episode_images(series_id, season_number, episode_number, image_types, sources)

    async def save_season_web_images(self, series_id: str, season_number: int, images_to_save: List[Dict], behavior: str = "overwrite") -> Tuple[bool, str]:
        """保存季度网络图片到 Override 目录。文件名: season-{s_num}.jpg"""
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：覆盖缓存 (override) 目录未在设置中配置。"

        target_images_dir = os.path.join(override_path, "tmdb-tv", series_id, "images")
        os.makedirs(target_images_dir, exist_ok=True)

        # 季度图片的文件名映射
        filename_map = {
            "poster": f"season-{season_number}.jpg",
            "fanart": f"season-{season_number}-fanart.jpg",
            "logo": f"season-{season_number}-clearlogo.png",
        }

        log_audit("图片", "开始", f"[保存季度网络图片] Series: {series_id} S{season_number}, 模式: {behavior}, 数量: {len(images_to_save)}")
        success_count = 0
        error_count = 0
        skipped_count = 0
        messages = []

        for image_info in images_to_save:
            image_type = image_info.get("type") or image_info.get("label")
            image_url = image_info.get("url") or image_info.get("full_url")

            if not image_type or not image_url:
                continue

            target_filename = filename_map.get(image_type)
            if not target_filename:
                continue

            save_path = os.path.join(target_images_dir, target_filename)

            if behavior == 'skip':
                base_name_no_ext = os.path.splitext(target_filename)[0]
                conflict_found = False
                for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    if os.path.exists(os.path.join(target_images_dir, base_name_no_ext + ext)):
                        conflict_found = True
                        break
                if conflict_found:
                    skipped_count += 1
                    continue

            temp_path = save_path + ".tmp"
            success, msg = await asyncio.to_thread(self.web_image_service.download_image, image_url, temp_path)

            if success:
                try:
                    if behavior == 'overwrite':
                        base_name_no_ext = os.path.splitext(target_filename)[0]
                        def _clean_season_files():
                            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                possible = os.path.join(target_images_dir, base_name_no_ext + ext)
                                if os.path.isfile(possible):
                                    try: os.remove(possible)
                                    except OSError: pass
                        await asyncio.to_thread(_clean_season_files)

                    await asyncio.to_thread(shutil.move, temp_path, save_path)
                    success_count += 1
                    log_audit("图片", "完成", f"[保存季度网络图片] 成功: {target_filename} - Series: {series_id} S{season_number}")
                except Exception as e:
                    error_count += 1
                    messages.append(f"文件操作失败 {target_filename}: {e}")
                    if os.path.exists(temp_path):
                        await asyncio.to_thread(os.remove, temp_path)
            else:
                error_count += 1
                messages.append(f"下载失败 {target_filename}: {msg}")

        await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)

        final_message = f"操作完成。成功: {success_count}, 跳过: {skipped_count}, 失败: {error_count}。"
        if error_count > 0:
            final_message += "\n" + "\n".join(messages)
        return True, final_message

    async def save_episode_web_images(self, series_id: str, season_number: int, episode_number: int, images_to_save: List[Dict], behavior: str = "overwrite") -> Tuple[bool, str]:
        """保存集网络图片到 Override 目录。文件名: season-{s_num}-episode-{e_num}.jpg"""
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：覆盖缓存 (override) 目录未在设置中配置。"

        target_images_dir = os.path.join(override_path, "tmdb-tv", series_id, "images")
        os.makedirs(target_images_dir, exist_ok=True)

        # 集图片的文件名映射
        filename_map = {
            "thumb": f"season-{season_number}-episode-{episode_number}.jpg",
        }

        log_audit("图片", "开始", f"[保存集网络图片] Series: {series_id} S{season_number}E{episode_number}, 模式: {behavior}, 数量: {len(images_to_save)}")
        success_count = 0
        error_count = 0
        skipped_count = 0
        messages = []

        for image_info in images_to_save:
            image_type = image_info.get("type") or image_info.get("label")
            image_url = image_info.get("url") or image_info.get("full_url")

            if not image_type or not image_url:
                continue

            target_filename = filename_map.get(image_type)
            if not target_filename:
                continue

            save_path = os.path.join(target_images_dir, target_filename)

            if behavior == 'skip':
                base_name_no_ext = os.path.splitext(target_filename)[0]
                conflict_found = False
                for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                    if os.path.exists(os.path.join(target_images_dir, base_name_no_ext + ext)):
                        conflict_found = True
                        break
                if conflict_found:
                    skipped_count += 1
                    continue

            temp_path = save_path + ".tmp"
            success, msg = await asyncio.to_thread(self.web_image_service.download_image, image_url, temp_path)

            if success:
                try:
                    if behavior == 'overwrite':
                        base_name_no_ext = os.path.splitext(target_filename)[0]
                        def _clean_episode_files():
                            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                possible = os.path.join(target_images_dir, base_name_no_ext + ext)
                                if os.path.isfile(possible):
                                    try: os.remove(possible)
                                    except OSError: pass
                        await asyncio.to_thread(_clean_episode_files)

                    await asyncio.to_thread(shutil.move, temp_path, save_path)
                    success_count += 1
                    log_audit("图片", "完成", f"[保存集网络图片] 成功: {target_filename} - Series: {series_id} S{season_number}E{episode_number}")
                except Exception as e:
                    error_count += 1
                    messages.append(f"文件操作失败 {target_filename}: {e}")
                    if os.path.exists(temp_path):
                        await asyncio.to_thread(os.remove, temp_path)
            else:
                error_count += 1
                messages.append(f"下载失败 {target_filename}: {msg}")

        await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)

        final_message = f"操作完成。成功: {success_count}, 跳过: {skipped_count}, 失败: {error_count}。"
        if error_count > 0:
            final_message += "\n" + "\n".join(messages)
        return True, final_message

    async def download_images_from_emby(self, item_type: str, item_id: str, broadcast: bool = True) -> Tuple[bool, str]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "覆盖缓存路径未配置。"
        
        target_base_dir = os.path.join(override_path, item_type, item_id)
        
        success, message = await self.emby_integration_service.download_images_core(item_type, item_id, target_base_dir, broadcast=broadcast)
        
        if success:
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            log_audit("图片", "完成", f"Emby 图片下载任务全部完成: {item_type}/{item_id}")
        return success, message