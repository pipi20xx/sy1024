import os
import json
import shutil
import asyncio
from typing import Dict, Any, Tuple, Optional, List

from ...common import SOURCE_OVERRIDE, SOURCE_PRIMARY, MAIN_JSON_FILENAMES
from ...logger import log_audit


class DeleteMixin:
    """所有删除操作：删除覆盖文件夹、缓存、图片、Patches、元数据等。"""

    async def delete_override_folder(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除覆盖缓存文件夹: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"
        target_folder = os.path.join(override_path, item_type, item_id)
        if not os.path.isdir(target_folder): return True, "覆盖缓存中文件夹不存在，无需删除。"

        try:
            shutil.rmtree(target_folder)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "项目的覆盖缓存文件夹已成功删除。"
        except Exception as e:
            return False, f"删除文件夹时发生错误: {e}"

    async def delete_cache_folder(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除主缓存文件夹: {item_type}/{item_id}")
        primary_path = self._get_cache_path_for_source(SOURCE_PRIMARY)
        if not primary_path: return False, "错误：未配置主缓存目录。"
        target_folder = os.path.join(primary_path, item_type, item_id)
        if not os.path.isdir(target_folder): return True, "主缓存中文件夹不存在，无需删除。"

        try:
            shutil.rmtree(target_folder)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "项目的主缓存文件夹已成功删除。"
        except Exception as e:
            return False, f"删除文件夹时发生错误: {e}"

    async def delete_item_images(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除覆盖图片: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"
        images_folder = os.path.join(override_path, item_type, item_id, "images")
        if not os.path.isdir(images_folder): return True, "没有找到可供删除的图片文件夹。"

        try:
            shutil.rmtree(images_folder)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "项目在覆盖缓存中的所有图片已成功删除。"
        except Exception as e:
            return False, f"删除图片时发生错误: {e}"

    async def delete_patches_folder(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除 Patches 文件夹: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"
        patches_folder = os.path.join(override_path, item_type, item_id, "patches")
        if not os.path.isdir(patches_folder): return True, "没有找到可供删除的 Patches 文件夹。"

        try:
            shutil.rmtree(patches_folder)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "项目的 Patches 文件夹已成功删除。"
        except Exception as e:
            return False, f"删除 Patches 文件夹时发生错误: {e}"

    async def delete_item_metadata(self, item_type: str, item_id: str, mode: str = 'all') -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除覆盖元数据: {item_type}/{item_id} (模式: {mode})")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        item_folder = os.path.join(override_path, item_type, item_id)
        if not os.path.isdir(item_folder):
            return True, "覆盖缓存中没有找到该项目的文件夹，无需删除元数据。"

        deleted_count = 0
        errors = []

        if mode == 'main_only':
            main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
            if main_json_filename:
                file_path = os.path.join(item_folder, main_json_filename)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        error_msg = f"删除文件 {main_json_filename} 时发生错误: {e}"
                        log_audit("编辑", "处理", error_msg, level="ERROR")
                        errors.append(error_msg)
        else:
            for filename in os.listdir(item_folder):
                if filename.endswith('.json') and filename not in ['episodegroup.json', 'tags.json', 'episodeorder.json', 'external_ids.json']:
                    file_path = os.path.join(item_folder, filename)
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        error_msg = f"删除文件 {filename} 时发生错误: {e}"
                        log_audit("编辑", "处理", error_msg, level="ERROR")
                        errors.append(error_msg)

        if errors:
            return False, f"删除元数据时发生错误:\n" + "\n".join(errors)

        if deleted_count > 0:
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, f"成功删除了 {deleted_count} 个元数据文件。"
        else:
            return True, "在覆盖缓存中没有找到可供删除的元数据文件。"

    async def delete_season_metadata(self, series_id: str, season_number: int, include_episodes: bool) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除季元数据: {series_id} S{season_number} (含子项: {include_episodes})")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        series_folder = os.path.join(override_path, "tmdb-tv", series_id)
        season_json_path = os.path.join(series_folder, f"season-{season_number}.json")
        deleted_count = 0

        if os.path.isfile(season_json_path):
            try:
                os.remove(season_json_path); deleted_count += 1
            except Exception as e:
                return False, f"删除季元数据文件失败: {e}"

        if include_episodes and os.path.isdir(series_folder):
            for filename in os.listdir(series_folder):
                if filename.startswith(f"season-{season_number}-episode-") and filename.endswith(".json"):
                    try:
                        os.remove(os.path.join(series_folder, filename)); deleted_count += 1
                    except Exception as e:
                        log_audit("编辑", "失败", f"删除集文件 {filename} 失败: {e}", level="WARN")
        if deleted_count > 0:
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, f"操作成功，共删除了 {deleted_count} 个覆盖元数据文件。"
        else:
            return False, "当前使用的是主源数据，没有覆盖数据可供删除。"

    async def delete_episode_metadata(self, series_id: str, season_number: int, episode_number: int) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除集元数据: {series_id} S{season_number}E{episode_number}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"
        json_path = os.path.join(override_path, "tmdb-tv", series_id, f"season-{season_number}-episode-{episode_number}.json")
        if not os.path.isfile(json_path): return False, "当前使用的是主源数据，没有覆盖数据可供删除。"

        try:
            os.remove(json_path)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "集的覆盖元数据已删除。"
        except Exception as e:
            return False, f"删除集元数据时发生错误: {e}"
