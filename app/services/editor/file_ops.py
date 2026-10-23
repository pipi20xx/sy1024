import os
import json
import shutil
import asyncio
from typing import Dict, Any, Tuple, Optional, List

from ...common import SOURCE_OVERRIDE, SOURCE_PRIMARY, MAIN_JSON_FILENAMES
from ...logger import log_audit
from .. import patches as patch_store


class FileOpsMixin:
    """文件操作：复制项目到 Override、锁定名称（Patches）。"""

    async def copy_item_to_override(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "开始", f"开始将项目 {item_type}/{item_id} 复制到覆盖缓存...")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        primary_path = self._get_cache_path_for_source(SOURCE_PRIMARY)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"
        if not primary_path: return False, "错误：未配置主缓存目录。"

        source_folder = os.path.join(primary_path, item_type, item_id)
        if not os.path.isdir(source_folder): return False, f"错误：源文件夹不存在: {source_folder}"

        target_folder = os.path.join(override_path, item_type, item_id)
        os.makedirs(target_folder, exist_ok=True)

        def _copy_files():
            source_images_dir = os.path.join(source_folder, "images")
            target_images_dir = os.path.join(target_folder, "images")

            c_count, s_count = 0, 0

            for item_name in os.listdir(source_folder):
                source_item_path = os.path.join(source_folder, item_name)
                target_item_path = os.path.join(target_folder, item_name)
                if os.path.isfile(source_item_path) and item_name.endswith('.json'):
                    if not os.path.exists(target_item_path):
                        shutil.copy2(source_item_path, target_item_path); c_count += 1
                    else: s_count += 1

            if os.path.isdir(source_images_dir):
                os.makedirs(target_images_dir, exist_ok=True)
                for image_name in os.listdir(source_images_dir):
                    source_image_path = os.path.join(source_images_dir, image_name)
                    target_image_path = os.path.join(target_images_dir, image_name)
                    if os.path.isfile(source_image_path):
                        if not os.path.exists(target_image_path):
                            shutil.copy2(source_image_path, target_image_path); c_count += 1
                        else: s_count += 1
            return c_count, s_count

        copied_files_count, skipped_files_count = await asyncio.to_thread(_copy_files)

        await self.scanner_service._refresh_item_in_db(item_type, item_id)

        return True, f"操作完成。补充复制了 {copied_files_count} 个文件，跳过了 {skipped_files_count} 个已存在项。"

    async def lock_item_name(self, item_type: str, item_id: str, mode: str = None) -> Tuple[bool, str]:
        """
        锁定项目名称：读取当前名称（优先 override，其次 cache），写入 patches 文件。
        不再复制整个 JSON，而是只创建包含名称字段的 patches/series.json 或 patches/all.json。
        mode 参数保留用于向后兼容，但不再影响行为。
        """
        log_audit("编辑", "开始", f"开始锁定项目名称 (Patches): {item_type}/{item_id}")
        if not self.is_override_cache_configured():
            return False, "错误：未配置覆盖缓存目录。"

        main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_filename:
            return False, "不支持的项目类型。"

        override_dir = os.path.join(self.configuration_service.get("override_cache_path"), item_type, item_id)
        override_file_path = os.path.join(override_dir, main_json_filename)
        primary_file_path = os.path.join(self.configuration_service.get("primary_cache_path"), item_type, item_id, main_json_filename) if self.configuration_service.get("primary_cache_path") else None

        name_key = "title" if item_type == "tmdb-movies2" else "name"

        # 确定名称来源：优先 override，其次 cache
        source_file = None
        source_label = ""
        if os.path.isfile(override_file_path):
            source_file = override_file_path
            source_label = "Override"
        elif primary_file_path and os.path.isfile(primary_file_path):
            source_file = primary_file_path
            source_label = "Cache"
        else:
            return False, f"找不到项目 {item_id} 的 {main_json_filename} 文件（Override 和 Cache 均不存在）。"

        try:
            def _process_lock():
                # 1. 读取源 JSON 中的名称
                with open(source_file, 'r', encoding='utf-8') as f:
                    source_data = json.load(f)
                name_value = source_data.get(name_key)
                if not name_value:
                    return None, f"源文件 {source_label} 中未找到 {name_key} 字段。"

                # 2. 创建 patches 目录
                patches_dir = os.path.join(override_dir, "patches")
                os.makedirs(patches_dir, exist_ok=True)

                # 3. 读取现有 patches 文件（如果有），合并名称字段
                patch_file_path = os.path.join(patches_dir, main_json_filename)
                patch_data = {}
                if os.path.isfile(patch_file_path):
                    try:
                        with open(patch_file_path, 'r', encoding='utf-8') as f:
                            patch_data = json.load(f)
                    except Exception:
                        patch_data = {}

                # 4. 写入名称到 patches 文件（原子写入并让模拟器的读取缓存失效）
                patch_data[name_key] = name_value
                patch_store.write_json(patch_file_path, patch_data)

                return name_value, f"已将名称 '{name_value}' 锁定到 patches/{main_json_filename}（来源: {source_label}）。"

            name_value, message = await asyncio.to_thread(_process_lock)

            if name_value is None:
                return False, message

            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, message
        except Exception as e:
            log_audit("编辑", "失败", f"锁定名称操作失败 for {item_type}/{item_id}: {e}", level="ERROR")
            return False, f"锁定名称操作失败: {e}"

    async def update_patch_name(self, item_type: str, item_id: str, new_name: str) -> Tuple[bool, str]:
        """直接更新 patches 文件中的名称字段，不需要 Override 有主 JSON。"""
        log_audit("编辑", "开始", f"开始更新 Patches 名称: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：未配置覆盖缓存目录。"

        main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_filename:
            return False, "不支持的项目类型。"

        name_key = "title" if item_type == "tmdb-movies2" else "name"

        override_dir = os.path.join(override_path, item_type, item_id)
        patches_dir = os.path.join(override_dir, "patches")
        patch_file_path = os.path.join(patches_dir, main_json_filename)

        if not os.path.isfile(patch_file_path):
            return False, "Patches 文件不存在，请先使用「锁定名称」。"

        try:
            def _update():
                with open(patch_file_path, "r", encoding="utf-8") as f:
                    patch_data = json.load(f)
                patch_data[name_key] = new_name
                patch_store.write_json(patch_file_path, patch_data)

            await asyncio.to_thread(_update)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, f"已将名称更新为 '{new_name}'。"
        except Exception as e:
            log_audit("编辑", "失败", f"更新 Patches 名称失败 for {item_type}/{item_id}: {e}", level="ERROR")
            return False, f"更新 Patches 名称失败: {e}"
