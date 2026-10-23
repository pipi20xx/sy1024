import os
import json
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union

from ...common import SOURCE_OVERRIDE, SOURCE_PRIMARY, MAIN_JSON_FILENAMES
from ...logger import log_audit


class SpecialFilesMixin:
    """特殊文件操作：剧集组 (episodegroup.json)、剧集排序 (episodeorder.json)、外部 ID (external_ids.json)。"""

    # ==================== Episode Group ====================

    def get_episode_group_content(self, series_id: str) -> Tuple[bool, Union[Dict, str]]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        epg_path = os.path.join(override_path, "tmdb-tv", series_id, "episodegroup.json")

        if os.path.isfile(epg_path):
            try:
                with open(epg_path, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            except Exception as e:
                return False, f"读取 episodegroup.json 文件失败: {e}"
        else:
            default_data = {"description": "", "groups": [], "id": series_id}
            return True, default_data

    async def update_episode_group_content(self, series_id: str, new_content: Dict[str, Any]) -> Tuple[bool, str]:
        log_audit("编辑", "开始", f"开始更新剧集组内容: {series_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        target_folder = os.path.join(override_path, "tmdb-tv", series_id)
        os.makedirs(target_folder, exist_ok=True)
        target_file_path = os.path.join(target_folder, "episodegroup.json")

        processed_groups = {}
        if "groups" in new_content and isinstance(new_content["groups"], list):
            for group in new_content["groups"]:
                group_order = group.get("order")
                if group_order is not None:
                    if group_order not in processed_groups:
                        processed_groups[group_order] = {
                            "name": group.get("name", f"第 {group_order} 季"),
                        }
                        if "overview" in group:
                            processed_groups[group_order]["overview"] = group["overview"]
                        if "air_date" in group:
                            processed_groups[group_order]["air_date"] = group["air_date"]
                        processed_groups[group_order]["order"] = group_order
                        processed_groups[group_order]["episodes"] = []
                    else:
                        processed_groups[group_order]["name"] = group.get("name", f"第 {group_order} 季")
                        if "overview" in group:
                            processed_groups[group_order]["overview"] = group["overview"]
                        else:
                            processed_groups[group_order].pop("overview", None)
                        if "air_date" in group:
                            processed_groups[group_order]["air_date"] = group["air_date"]
                        else:
                            processed_groups[group_order].pop("air_date", None)

                    existing_episodes = {
                        (ep.get("season_number"), ep.get("episode_number"), ep.get("order"))
                        for ep in processed_groups[group_order]["episodes"]
                    }
                    for new_episode in group.get("episodes", []):
                        ep_key = (new_episode.get("season_number"), new_episode.get("episode_number"), new_episode.get("order"))
                        if ep_key not in existing_episodes:
                            processed_groups[group_order]["episodes"].append(new_episode)
                            existing_episodes.add(ep_key)

            for group_order in processed_groups:
                processed_groups[group_order]["episodes"].sort(key=lambda x: x.get("order", 0))

            new_content["groups"] = sorted(list(processed_groups.values()), key=lambda x: x.get("order", 0))

        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(new_content, f, indent=2, ensure_ascii=False)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "episodegroup.json 文件已成功更新。"
        except IOError as e:
            return False, f"写入文件时发生错误: {e}"

    async def create_episode_group_file(self, series_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "开始", f"开始创建剧集组文件: {series_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        target_folder = os.path.join(override_path, "tmdb-tv", series_id)
        os.makedirs(target_folder, exist_ok=True)
        target_file_path = os.path.join(target_folder, "episodegroup.json")
        if os.path.exists(target_file_path): return False, "文件已存在，无法创建。"

        default_data = {"description": "自定义剧集分组", "groups": [], "id": series_id}

        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "episodegroup.json 文件已成功创建。"
        except IOError as e:
            return False, f"创建文件时发生错误: {e}"

    async def delete_episode_group_file(self, series_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除剧集组文件: {series_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        target_file_path = os.path.join(override_path, "tmdb-tv", series_id, "episodegroup.json")
        if not os.path.isfile(target_file_path): return True, "文件不存在，无需删除。"

        try:
            os.remove(target_file_path)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "episodegroup.json 文件已成功删除。"
        except OSError as e:
            return False, f"删除文件时发生错误: {e}"

    # ==================== Episode Order ====================

    def get_episode_order_content(self, series_id: str) -> Tuple[bool, Union[Dict, str]]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        ep_order_path = os.path.join(override_path, "tmdb-tv", series_id, "episodeorder.json")

        if os.path.isfile(ep_order_path):
            try:
                with open(ep_order_path, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            except Exception as e:
                return False, f"读取 episodeorder.json 文件失败: {e}"
        else:
            default_data = {"description": "", "seasons": []}
            return True, default_data

    async def update_episode_order_content(self, series_id: str, new_content: Dict[str, Any]) -> Tuple[bool, str]:
        log_audit("编辑", "开始", f"开始更新剧集排序内容: {series_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        target_folder = os.path.join(override_path, "tmdb-tv", series_id)
        os.makedirs(target_folder, exist_ok=True)
        target_file_path = os.path.join(target_folder, "episodeorder.json")

        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(new_content, f, indent=2, ensure_ascii=False)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "episodeorder.json 文件已成功更新。"
        except IOError as e:
            return False, f"写入文件时发生错误: {e}"

    async def delete_episode_order_file(self, series_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除剧集排序文件: {series_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        target_file_path = os.path.join(override_path, "tmdb-tv", series_id, "episodeorder.json")
        if not os.path.isfile(target_file_path): return True, "文件不存在，无需删除。"

        try:
            os.remove(target_file_path)
            await self.scanner_service._refresh_item_in_db("tmdb-tv", series_id)
            return True, "episodeorder.json 文件已成功删除。"
        except OSError as e:
            return False, str(f"删除文件时发生错误: {e}")

    # ==================== External IDs ====================

    def get_external_ids_content(self, item_type: str, item_id: str) -> Tuple[bool, Union[Dict, str]]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        if item_type == "tmdb-tv":
            target_folder = os.path.join(override_path, "tmdb-tv", item_id)
        else:
            target_folder = os.path.join(override_path, "tmdb-movies2", item_id)

        external_ids_path = os.path.join(target_folder, "external_ids.json")

        if os.path.isfile(external_ids_path):
            try:
                with open(external_ids_path, "r", encoding="utf-8") as f:
                    return True, json.load(f)
            except Exception as e:
                return False, f"读取 external_ids.json 文件失败: {e}"
        else:
            default_data = {"external_ids": {}}
            return True, default_data

    async def update_external_ids_content(self, item_type: str, item_id: str, new_content: Dict[str, Any]) -> Tuple[bool, str]:
        log_audit("编辑", "开始", f"开始更新外部ID内容: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        if item_type == "tmdb-tv":
            target_folder = os.path.join(override_path, "tmdb-tv", item_id)
        else:
            target_folder = os.path.join(override_path, "tmdb-movies2", item_id)

        os.makedirs(target_folder, exist_ok=True)
        target_file_path = os.path.join(target_folder, "external_ids.json")

        processed_seasons = {}
        if "seasons" in new_content and isinstance(new_content["seasons"], list):
            for season in new_content["seasons"]:
                season_number = season.get("season_number")
                if season_number is not None:
                    if season_number not in processed_seasons:
                        processed_seasons[season_number] = {}

                    season_external_ids = season.get("external_ids", {})
                    for key, value in season_external_ids.items():
                        if value is not None and value != "":
                            processed_seasons[season_number][key] = value
                        elif key in processed_seasons[season_number]:
                            del processed_seasons[season_number][key]

            if processed_seasons:
                new_content["seasons"] = [
                    {"season_number": sn, "external_ids": ids}
                    for sn, ids in sorted(processed_seasons.items())
                ]
            else:
                del new_content["seasons"]

        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(new_content, f, indent=2, ensure_ascii=False)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "external_ids.json 文件已成功更新。"
        except IOError as e:
            return False, f"写入文件时发生错误: {e}"

    async def delete_external_ids_file(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        log_audit("编辑", "清理", f"开始删除外部ID文件: {item_type}/{item_id}")
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path: return False, "错误：未配置覆盖缓存目录。"

        if item_type == "tmdb-tv":
            target_file_path = os.path.join(override_path, "tmdb-tv", item_id, "external_ids.json")
        else:
            target_file_path = os.path.join(override_path, "tmdb-movies2", item_id, "external_ids.json")

        if not os.path.isfile(target_file_path): return True, "文件不存在，无需删除。"

        try:
            os.remove(target_file_path)
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "external_ids.json 文件已成功删除。"
        except OSError as e:
            return False, f"删除文件时发生错误: {e}"
