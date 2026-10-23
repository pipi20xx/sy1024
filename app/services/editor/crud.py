import os
import json
import shutil
import asyncio
from typing import Dict, Any, Tuple, Optional, List
from sqlalchemy import select, delete

from ...database import ItemsSessionLocal
from ...models import Item
from ...common import MAIN_JSON_FILENAMES, SOURCE_OVERRIDE, SOURCE_PRIMARY
from ...logger import log_audit


class MetadataCrudMixin:
    """元数据 CRUD 操作：更新项目/季/集的元数据。"""

    async def update_item_metadata(self, item_type: str, item_id: str, updated_data: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        log_audit("编辑", "开始", f"开始更新项目元数据: {item_type}/{item_id}")
        main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_filename:
            return False, "不支持的项目类型", None

        json_path = self._get_actual_json_path(item_type, item_id, main_json_filename)
        if not json_path:
            return False, "找不到可编辑的元数据文件", None

        if self._is_primary_path(json_path):
            return False, "该文件位于主缓存(Primary)中，不允许直接编辑。请先使用「补充到 Override」复制后再编辑。", None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"读取元数据失败: {e}", None

        original_folder_id = item_id
        new_folder_id = str(updated_data.get("id", original_folder_id)).strip()
        folder_renamed = False
        original_folder_path = None
        new_folder_path = None

        if new_folder_id and new_folder_id != original_folder_id:
            current_folder_path = os.path.dirname(json_path)
            parent_dir = os.path.dirname(current_folder_path)
            new_folder_path = os.path.join(parent_dir, new_folder_id)

            if os.path.exists(new_folder_path):
                return False, f"重命名失败：目标文件夹 '{new_folder_path}' 已存在。", None

            try:
                shutil.move(current_folder_path, new_folder_path)
                original_folder_path = current_folder_path
                json_path = os.path.join(new_folder_path, os.path.basename(json_path))
                folder_renamed = True
            except Exception as e:
                return False, f"重命名文件夹失败: {e}", None

        if "genres" in updated_data and isinstance(updated_data["genres"], str):
            updated_data['genres'] = [{"name": g.strip()} for g in updated_data["genres"].split(',') if g.strip()]

        tags_to_save = updated_data.pop("tags", None)
        metadata.pop("tags", None)
        # Strip injected fields that should not be persisted to disk
        updated_data.pop("belongs_to_collections", None)
        metadata.pop("belongs_to_collections", None)
        metadata.update(updated_data)
        if 'id' in metadata:
            metadata['id'] = int(metadata['id'])

        if tags_to_save is not None:
            override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
            if override_path:
                final_override_folder = os.path.join(override_path, item_type, new_folder_id)
                os.makedirs(final_override_folder, exist_ok=True)

                tags_json_path = os.path.join(final_override_folder, "tags.json")
                try:
                    with open(tags_json_path, "w", encoding="utf-8") as f:
                        json.dump({"tags": tags_to_save}, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    log_audit("编辑", "更新", f"保存 tags.json 到 '{tags_json_path}' 失败: {e}", level="ERROR")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)

            # 同步更新 patches 中已被 patch 的字段，防止编辑被 patches 覆盖
            self._sync_patches_if_exist(json_path, updated_data)

            if folder_renamed:
                async with ItemsSessionLocal() as session:
                    stmt = delete(Item).where(Item.folder_id == original_folder_id, Item.item_type == item_type)
                    await session.execute(stmt)
                    await session.commit()

            await self.scanner_service._refresh_item_in_db(item_type, new_folder_id)
            return True, "元数据已成功更新。", new_folder_id
        except Exception as e:
            if folder_renamed and original_folder_path and new_folder_path:
                shutil.move(new_folder_path, original_folder_path)
            return False, f"写入更新时出错: {e}", original_folder_id

    async def update_season_metadata(self, series_id: str, season_number: int, updated_data: Dict[str, Any], update_episodes: bool) -> Tuple[bool, str]:
        season_json_path = self._get_actual_json_path("tmdb-tv", series_id, f"season-{season_number}.json")
        if not season_json_path:
            return False, f"季元数据文件 season-{season_number}.json 未找到"

        if self._is_primary_path(season_json_path):
            return False, "该文件位于主缓存(Primary)中，不允许直接编辑。请先使用「补充到 Override」复制后再编辑。"

        try:
            with open(season_json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"读取季元数据文件失败: {e}"

        series_folder_path = os.path.dirname(season_json_path)
        original_season_json_path = season_json_path

        new_season_number = int(updated_data.get("season_number", season_number))
        season_renamed = False
        if new_season_number != season_number:
            new_season_json_path = os.path.join(series_folder_path, f"season-{new_season_number}.json")
            if os.path.exists(new_season_json_path):
                return False, f"重命名失败：目标季文件 'season-{new_season_number}.json' 已存在。"
            try:
                shutil.move(season_json_path, new_season_json_path)
                season_json_path = new_season_json_path
                season_renamed = True
                metadata['season_number'] = new_season_number
            except Exception as e:
                return False, f"重命名季文件失败: {e}"

        renamed_episodes_log = []
        if season_renamed and update_episodes:
            try:
                for filename in os.listdir(series_folder_path):
                    if filename.startswith(f"season-{season_number}-episode-") and filename.endswith(".json"):
                        old_ep_path = os.path.join(series_folder_path, filename)
                        new_ep_filename = filename.replace(f"season-{season_number}-", f"season-{new_season_number}-", 1)
                        new_ep_path = os.path.join(series_folder_path, new_ep_filename)

                        shutil.move(old_ep_path, new_ep_path)
                        renamed_episodes_log.append((new_ep_path, old_ep_path))
            except Exception as e:
                for new_p, old_p in renamed_episodes_log:
                    shutil.move(new_p, old_p)
                shutil.move(season_json_path, original_season_json_path)
                return False, f"级联重命名集文件时失败: {e}"

        changes_made = season_renamed

        # 定义待合并的数据，排除掉由重命名逻辑处理的 season_number
        data_to_merge = updated_data.copy()
        data_to_merge.pop("season_number", None)

        # Merge all other fields
        for key, value in data_to_merge.items():
            # 特殊处理：对于 credits 和 casts，只要有值就更新，因为内部可能发生了深度变化
            if key in ["credits", "casts"]:
                metadata[key] = value
                changes_made = True
                continue

            if metadata.get(key) != value:
                metadata[key] = value
                changes_made = True

        if not changes_made:
            return True, "季元数据未发生变化"

        try:
            with open(season_json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)

            # 同步更新 patches 中已被 patch 的字段
            self._sync_patches_if_exist(season_json_path, data_to_merge)

            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "季元数据已成功更新"
        except Exception as e:
            if season_renamed:
                shutil.move(season_json_path, original_season_json_path)
                for new_p, old_p in renamed_episodes_log:
                    shutil.move(new_p, old_p)
            return False, f"写入季元数据文件失败: {e}"

    async def update_episode_metadata(self, series_id: str, season_number: int, episode_number: int, updated_data: Dict[str, Any]) -> Tuple[bool, str]:
        episode_json_path = self._get_actual_json_path("tmdb-tv", series_id, f"season-{season_number}-episode-{episode_number}.json")
        if not episode_json_path:
            return False, f"集元数据文件 season-{season_number}-episode-{episode_number}.json 未找到"

        if self._is_primary_path(episode_json_path):
            return False, "该文件位于主缓存(Primary)中，不允许直接编辑。请先使用「补充到 Override」复制后再编辑。"

        try:
            with open(episode_json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"读取集元数据文件失败: {e}"

        series_folder_path = os.path.dirname(episode_json_path)
        new_season_number = int(updated_data.get("season_number", season_number))
        new_episode_number = int(updated_data.get("episode_number", episode_number))
        original_episode_json_path = episode_json_path

        episode_renamed = False
        if new_season_number != season_number or new_episode_number != episode_number:
            new_episode_json_path = os.path.join(series_folder_path, f"season-{new_season_number}-episode-{new_episode_number}.json")
            if os.path.exists(new_episode_json_path):
                return False, f"重命名失败：目标集文件已存在。"
            try:
                shutil.move(episode_json_path, new_episode_json_path)
                episode_json_path = new_episode_json_path
                episode_renamed = True
                metadata['season_number'] = new_season_number
                metadata['episode_number'] = new_episode_number
            except Exception as e:
                return False, f"重命名集文件失败: {e}"

        changes_made = episode_renamed

        # Remove renaming keys
        data_to_merge = updated_data.copy()
        data_to_merge.pop("season_number", None)
        data_to_merge.pop("episode_number", None)

        # Merge all other fields
        for key, value in data_to_merge.items():
            if key in ["credits", "casts"]:
                metadata[key] = value
                changes_made = True
                continue

            if metadata.get(key) != value:
                metadata[key] = value
                changes_made = True

        if not changes_made:
            return True, "集元数据未发生变化"
        try:
            with open(episode_json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4, ensure_ascii=False)

            # 同步更新 patches 中已被 patch 的字段
            self._sync_patches_if_exist(episode_json_path, data_to_merge)

            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "集元数据已成功更新"
        except Exception as e:
            if episode_renamed:
                shutil.move(episode_json_path, original_episode_json_path)
            return False, f"写入集元数据文件失败: {e}"
