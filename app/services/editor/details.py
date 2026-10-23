import os
import json
import re
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union
from sqlalchemy import select

from ...database import ItemsSessionLocal
from ...models import Item
from ...common import (
    MAIN_JSON_FILENAMES,
    SOURCE_OVERRIDE,
    SOURCE_PRIMARY,
    TYPE_DISPLAY_NAMES,
    find_image_files_for_item,
    IMAGE_NAMING_RULES,
    deep_merge_dict
)
from ...logger import log_audit


class DetailsMixin:
    """读取项目详情、加载季/集数据、聚合演职员的方法。"""

    async def get_series_aggregated_credits(self, item_id: str) -> Dict[str, Any]:
        """
        聚合整部剧集（严禁读取 Cache，仅限物理路径在 Override 下的数据）的演职员表。
        """
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return {"cast": [], "crew": []}

        log_audit("编辑", "开始", f"开始聚合剧集演职员 (物理路径校验模式): {item_id}")
        details = await self.get_item_full_details("tmdb-tv", item_id)
        if not details:
            return {"cast": [], "crew": []}

        def is_override_file(path):
            if not path or not override_path: return False
            return os.path.abspath(path).startswith(os.path.abspath(override_path))

        all_cast, all_crew, all_guest = [], [], []

        # 1. 主条目
        # 通过数据库中的原始路径判断是否在 Override 目录下
        entry_json_path = self._get_actual_json_path("tmdb-tv", item_id, "series.json")

        if is_override_file(entry_json_path):
            main_meta = details.get("full_metadata", {})
            main_credits = main_meta.get("credits") or main_meta.get("casts") or {}
            all_cast = self._merge_credits_lists(all_cast, main_credits.get("cast", []), "cast", "主条目")
            all_crew = self._merge_credits_lists(all_crew, main_credits.get("crew", []), "crew", "主条目")
            all_guest = self._merge_credits_lists(all_guest, main_credits.get("guest_stars", []), "cast", "主条目")

        # 2. 遍历每一季
        for season in details.get("seasons", []):
            # 获取该季 JSON 的物理路径并校验
            s_num = season.get("season_number")
            season_json_path = self._get_actual_json_path("tmdb-tv", item_id, f"season-{s_num}.json")

            if is_override_file(season_json_path):
                s_meta = season.get("metadata")
                if s_meta:
                    s_credits = s_meta.get("credits") or s_meta.get("casts") or {}
                    all_cast = self._merge_credits_lists(all_cast, s_credits.get("cast", []), "cast", f"第{s_num}季")
                    all_crew = self._merge_credits_lists(all_crew, s_credits.get("crew", []), "crew", f"第{s_num}季")
                    all_guest = self._merge_credits_lists(all_guest, s_credits.get("guest_stars", []), "cast", f"第{s_num}季")

            # 3. 遍历每一集
            for ep in season.get("episodes", []):
                e_num = ep.get("episode_number")
                ep_json_path = self._get_actual_json_path("tmdb-tv", item_id, f"season-{s_num}-episode-{e_num}.json")

                if is_override_file(ep_json_path):
                    e_meta = ep.get("metadata")
                    if e_meta:
                        e_credits = e_meta.get("credits") or e_meta.get("casts") or {}
                        # 只有当集数有实际演职员数据时才进行合并日志打印
                        if e_credits.get("cast") or e_credits.get("guest_stars") or e_credits.get("crew"):
                            all_cast = self._merge_credits_lists(all_cast, e_credits.get("cast", []), "cast", f"S{s_num}E{e_num}")
                            all_crew = self._merge_credits_lists(all_crew, e_credits.get("crew", []), "crew", f"S{s_num}E{e_num}")
                            all_guest = self._merge_credits_lists(all_guest, e_credits.get("guest_stars", []), "cast", f"S{s_num}E{e_num}")

        # --- 打印聚合结果表格 ---
        def print_table(title, items, is_cast=True):
            if not items: return
            log_audit("编辑", "处理", f"\n[聚合结果 - {title}]")
            log_audit("编辑", "处理", f"{'ID':<10} | {'姓名':<20} | {'角色/职位'}")
            log_audit("编辑", "处理", "-" * 60)
            for p in items:
                pid = str(p.get("id", "N/A"))
                name = str(p.get("name", "N/A"))
                role = str(p.get("character") if is_cast else p.get("job", "N/A"))
                # 截断过长的字符串以保持对齐 (可选)
                log_audit("编辑", "处理", f"{pid:<10} | {name:<20} | {role}")
            log_audit("编辑", "处理", "-" * 60)
        print_table("主要演员 (Cast)", all_cast, is_cast=True)
        if all_guest: print_table("客串演员 (Guest Stars)", all_guest, is_cast=True)
        print_table("制作人员 (Crew)", all_crew, is_cast=False)

        log_audit("编辑", "完成", f"剧集演职员聚合完成。")
        return {
            "cast": all_cast,
            "crew": all_crew,
            "guest_stars": all_guest
        }

    async def get_item_full_details(self, item_type: str, item_id: str, view_mode: str = 'standard') -> Optional[Dict[str, Any]]:
        async with ItemsSessionLocal() as session:
            stmt = select(Item).where(Item.item_id == item_id, Item.item_type == item_type)
            result = await session.execute(stmt)
            entry = result.scalar()

        if not entry:
            await self.scanner_service._refresh_item_in_db(item_type, item_id)
            async with ItemsSessionLocal() as session:
                entry = (await session.execute(stmt)).scalar()
            if not entry: return None

        full_metadata = {}
        if entry.json_path and os.path.exists(entry.json_path):
            try:
                def _read_json():
                    with open(entry.json_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                full_metadata = await asyncio.to_thread(_read_json)
            except Exception as e:
                full_metadata = {"name": f"项目 {item_id} (元数据读取失败)", "overview": str(e)}

        # Inject collection info if available
        if self.emby_collection_service:
            collections = self.emby_collection_service.get_collections_by_item(item_id)
            if collections:
                full_metadata['belongs_to_collections'] = collections

        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        override_episodegroup_exists = False
        override_episodeorder_exists = False
        override_externalids_exists = False
        override_patches_exists = False

        if item_type == "tmdb-tv" and override_path:
            epg_path = os.path.join(override_path, item_type, entry.folder_id, "episodegroup.json")
            override_episodegroup_exists = await asyncio.to_thread(os.path.isfile, epg_path)
            epo_path = os.path.join(override_path, item_type, entry.folder_id, "episodeorder.json")
            override_episodeorder_exists = await asyncio.to_thread(os.path.isfile, epo_path)
            eids_path = os.path.join(override_path, item_type, entry.folder_id, "external_ids.json")
            override_externalids_exists = await asyncio.to_thread(os.path.isfile, eids_path)
            patches_dir = os.path.join(override_path, item_type, entry.folder_id, "patches")
            override_patches_exists = await asyncio.to_thread(os.path.isdir, patches_dir)
        elif override_path:
            eids_path = os.path.join(override_path, item_type, entry.folder_id, "external_ids.json")
            override_externalids_exists = await asyncio.to_thread(os.path.isfile, eids_path)
            patches_dir = os.path.join(override_path, item_type, entry.folder_id, "patches")
            override_patches_exists = await asyncio.to_thread(os.path.isdir, patches_dir)

        # --- Patches 合并：将 patches 中主 JSON 的内容合并到 full_metadata ---
        if override_patches_exists and full_metadata:
            main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
            if main_json_filename:
                patch_main_path = os.path.join(override_path, item_type, entry.folder_id, "patches", main_json_filename)
                if await asyncio.to_thread(os.path.isfile, patch_main_path):
                    try:
                        def _read_patch():
                            with open(patch_main_path, 'r', encoding='utf-8') as f:
                                return json.load(f)
                        patch_data = await asyncio.to_thread(_read_patch)
                        if isinstance(patch_data, dict) and patch_data:
                            deep_merge_dict(full_metadata, patch_data)
                    except Exception as e:
                        log_audit("编辑", "失败", f"读取 patches/{main_json_filename} 失败: {e}", level="WARN")

        details_result = {
            "id": item_id, "type": item_type, "source": entry.source,
            "full_metadata": full_metadata, "images": [], "seasons": [],
            "override_cache_exists": bool(override_path and os.path.isdir(os.path.join(override_path, item_type, entry.folder_id))),
            "primary_cache_configured": bool(self.configuration_service.get("primary_cache_path")),
            "override_cache_configured": bool(override_path),
            "override_episodegroup_exists": override_episodegroup_exists,
            "override_episodeorder_exists": override_episodeorder_exists,
            "override_externalids_exists": override_externalids_exists,
            "override_patches_exists": override_patches_exists,
            "tags": [],
        }

        # 查询 BGM 映射状态（只查本地 DB，开销极小）
        from ... import globals
        if globals.relation_service:
            bgm_map = await globals.relation_service.batch_check_bangumi_mapping(item_type, [item_id])
            details_result["has_bgm_mapping"] = bgm_map.get(item_id, False)
        else:
            details_result["has_bgm_mapping"] = False

        if override_path:
            tags_json_path = os.path.join(override_path, item_type, entry.folder_id, "tags.json")
            if await asyncio.to_thread(os.path.isfile, tags_json_path):
                try:
                    def _read_tags():
                        with open(tags_json_path, 'r', encoding='utf-8') as f:
                            return json.load(f)
                    tags_data = await asyncio.to_thread(_read_tags)
                    if isinstance(tags_data, dict) and "tags" in tags_data and isinstance(tags_data["tags"], list):
                        details_result["tags"] = tags_data["tags"]
                except Exception as e:
                    log_audit("编辑", "失败", f"读取 tags.json 失败: {e}", level="WARN")
        if override_path:
            item_folder_override = os.path.join(override_path, item_type, entry.folder_id)
            if await asyncio.to_thread(os.path.isdir, item_folder_override):
                images_found = await asyncio.to_thread(find_image_files_for_item, {"node_type": TYPE_DISPLAY_NAMES.get(item_type)}, item_folder_override)
                for key, path in images_found.items():
                    label = IMAGE_NAMING_RULES.get("series_movie", {}).get(key, {}).get("label", "未知图片")
                    image_filename = os.path.basename(path)
                    details_result["images"].append({"label": label, "url": f"/media-content/{item_type}/{entry.folder_id}/images/{image_filename}", "name": image_filename})

        if item_type == "tmdb-tv":
            series_folder_id = entry.folder_id
            if view_mode == 'episodegroup' and override_episodegroup_exists:
                details_result['seasons'] = await asyncio.to_thread(self._load_seasons_from_episodegroup, series_folder_id, override_path)
            else:
                details_result['seasons'] = await asyncio.to_thread(self._load_seasons_standard, series_folder_id, override_path)

        return details_result

    def _load_seasons_standard(self, series_id: str, override_path: Optional[str]) -> List[Dict[str, Any]]:
        seasons_list = []
        epg_lookup = {}
        if override_path:
            epg_path = os.path.join(override_path, "tmdb-tv", series_id, "episodegroup.json")
            if os.path.isfile(epg_path):
                try:
                    with open(epg_path, "r", encoding="utf-8") as f:
                        epg_data = json.load(f)
                    if epg_data and epg_data.get("groups"):
                        for group in epg_data["groups"]:
                            group_order = group.get("order")
                            for ep_map in group.get("episodes", []):
                                key = (ep_map.get("season_number"), ep_map.get("episode_number"))
                                value = (group_order, ep_map.get("order", 0) + 1)
                                epg_lookup[key] = value
                except Exception as e:
                    log_audit("编辑", "失败", f"加载 or 解析 EPG 文件 {epg_path} 以便附加编号时出错: {e}", level="WARN")
        final_files = {}
        for source_type in [SOURCE_PRIMARY, SOURCE_OVERRIDE]:
            source_path = self._get_cache_path_for_source(source_type)
            if not source_path: continue
            series_folder = os.path.join(source_path, "tmdb-tv", series_id)
            if os.path.isdir(series_folder):
                for filename in os.listdir(series_folder):
                    if filename.endswith('.json') and (filename.startswith('season-') or filename.startswith('episode-')):
                        final_files[filename] = {"path": os.path.join(series_folder, filename), "source": source_type}

        all_seasons_data = {}
        for filename, file_info in final_files.items():
            season_match = re.search(r'season-(\d+)\.json', filename)
            if season_match:
                s_num = int(season_match.group(1))
                all_seasons_data.setdefault(s_num, {'episodes': {}})['file_info'] = file_info
            episode_match = re.search(r'season-(\d+)-episode-(\d+)\.json', filename)
            if episode_match:
                s_num, e_num = int(episode_match.group(1)), int(episode_match.group(2))
                all_seasons_data.setdefault(s_num, {'episodes': {}}).setdefault('episodes', {})[e_num] = file_info

        for s_num in sorted(all_seasons_data.keys()):
            season_data = all_seasons_data[s_num]
            season_file_info = season_data.get('file_info')
            season_metadata, season_source = None, None

            if season_file_info:
                try:
                    with open(season_file_info['path'], 'r', encoding='utf-8') as f:
                        season_metadata = json.load(f)
                    season_source = season_file_info['source']
                except Exception: pass

            episodes_in_season = []
            for e_num, ep_file_info in sorted(season_data.get('episodes', {}).items()):
                try:
                    with open(ep_file_info['path'], 'r', encoding='utf-8') as f:
                        ep_metadata = json.load(f)

                    custom_season_num, custom_episode_num = None, None
                    if (s_num, e_num) in epg_lookup:
                        custom_season_num, custom_episode_num = epg_lookup[(s_num, e_num)]

                    ep_thumb_url = None
                    if override_path:
                        ep_folder = os.path.join(override_path, "tmdb-tv", series_id)
                        ep_images = find_image_files_for_item({"node_type": "集", "season_number": s_num, "episode_number": e_num}, ep_folder)
                        if 'thumb' in ep_images:
                            ep_thumb_url = f"/media-content/tmdb-tv/{series_id}/images/{os.path.basename(ep_images['thumb'])}"

                    episode_data_to_append = {
                        "metadata": ep_metadata,
                        "season_number": s_num,
                        "episode_number": e_num,
                        "thumb_path": ep_thumb_url,
                        "source": ep_file_info['source']
                    }
                    if custom_season_num is not None:
                        episode_data_to_append["custom_season_number"] = custom_season_num
                    if custom_episode_num is not None:
                        episode_data_to_append["custom_episode_number"] = custom_episode_num

                    episodes_in_season.append(episode_data_to_append)
                except Exception: pass

            season_poster_url = None
            if override_path:
                s_folder = os.path.join(override_path, "tmdb-tv", series_id)
                s_images = find_image_files_for_item({"node_type": "季", "season_number": s_num}, s_folder)
                if 'poster' in s_images:
                    season_poster_url = f"/media-content/tmdb-tv/{series_id}/images/{os.path.basename(s_images['poster'])}"

            seasons_list.append({
                "metadata": season_metadata,
                "season_number": s_num,
                "poster_path": season_poster_url,
                "episodes": episodes_in_season,
                "source": season_source,
                "is_episodegroup": False
            })
        return seasons_list

    def _load_seasons_from_episodegroup(self, series_id: str, override_path: Optional[str]) -> List[Dict[str, Any]]:
        seasons_list = []
        epg_path = os.path.join(override_path, "tmdb-tv", series_id, "episodegroup.json")
        try:
            with open(epg_path, "r", encoding="utf-8") as f:
                epg_data = json.load(f)
        except Exception as e:
            log_audit("编辑", "失败", f"无法加载或解析 episodegroup.json: {epg_path}, 错误: {e}", level="ERROR")
            return []

        for group in epg_data.get("groups", []):
            group_order = group.get("order")
            season_metadata = {
                "name": group.get("name", f"第 {group_order} 组"),
                "overview": group.get("overview", ""),
                "season_number": group_order,
                "air_date": group.get("air_date", "")
            }

            episodes_in_season = []

            for episode_map in group.get("episodes", []):
                tmdb_s_num = episode_map.get("season_number")
                tmdb_e_num = episode_map.get("episode_number")
                ep_json_path = self._get_actual_json_path("tmdb-tv", series_id, f"season-{tmdb_s_num}-episode-{tmdb_e_num}.json")

                if ep_json_path:
                    try:
                        with open(ep_json_path, 'r', encoding='utf-8') as f:
                            ep_metadata = json.load(f)

                        ep_source = SOURCE_PRIMARY
                        if override_path and ep_json_path.startswith(override_path):
                            ep_source = SOURCE_OVERRIDE

                        ep_thumb_url = None
                        if override_path:
                            ep_folder = os.path.join(override_path, "tmdb-tv", series_id)
                            custom_season_num = group.get("order")
                            custom_episode_num = episode_map.get("order", 0) + 1
                            ep_images = find_image_files_for_item({"node_type": "集", "season_number": custom_season_num, "episode_number": custom_episode_num}, ep_folder)
                            if not ep_images:
                                ep_images = find_image_files_for_item({"node_type": "集", "season_number": tmdb_s_num, "episode_number": tmdb_e_num}, ep_folder)
                            if 'thumb' in ep_images:
                                ep_thumb_url = f"/media-content/tmdb-tv/{series_id}/images/{os.path.basename(ep_images['thumb'])}"

                        episodes_in_season.append({
                            "metadata": ep_metadata,
                            "custom_episode_number": episode_map.get("order", 0) + 1,
                            "custom_season_number": group_order,
                            "season_number": tmdb_s_num,
                            "episode_number": tmdb_e_num,
                            "thumb_path": ep_thumb_url,
                            "source": ep_source
                        })
                    except Exception as e:
                        log_audit("编辑", "失败", f"加载集文件 {ep_json_path} 失败: {e}", level="WARN")
            season_poster_url = None
            if override_path:
                series_folder_override = os.path.join(override_path, "tmdb-tv", series_id)
                poster_search_data = {
                    "node_type": "季",
                    "season_number": group_order
                }
                season_images = find_image_files_for_item(poster_search_data, series_folder_override)
                if 'poster' in season_images:
                    poster_filename = os.path.basename(season_images['poster'])
                    season_poster_url = f"/media-content/tmdb-tv/{series_id}/images/{poster_filename}"

            seasons_list.append({
                "metadata": season_metadata,
                "season_number": group_order,
                "poster_path": season_poster_url,
                "episodes": sorted(episodes_in_season, key=lambda x: x.get('custom_episode_number', 0)),
                "source": SOURCE_OVERRIDE,
                "is_episodegroup": True
            })
        return sorted(seasons_list, key=lambda x: x.get('season_number', 0))

    async def get_all_override_items_metadata(self) -> Tuple[bool, Union[List[Dict[str, Any]], str]]:
        """
        直接从磁盘扫描 override 目录，获取所有项目的完整元数据。
        为了性能，不读取季和集的信息。

        数据优先级：override 主 JSON > primary cache 主 JSON > 空，最后 patches 最高优先级覆盖合并。
        """
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：未配置覆盖缓存目录。"

        primary_path = self._get_cache_path_for_source(SOURCE_PRIMARY)

        def _scan_disk():
            results = []
            targets = [
                ('tmdb-movies2', 'movie', 'all.json'),
                ('tmdb-tv', 'tv', 'series.json')
            ]

            for folder_key, db_type, json_file in targets:
                override_type_path = os.path.join(override_path, folder_key)
                if not os.path.isdir(override_type_path):
                    continue

                for tmdb_id in os.listdir(override_type_path):
                    item_dir = os.path.join(override_type_path, tmdb_id)
                    if not os.path.isdir(item_dir):
                        continue

                    override_json_path = os.path.join(item_dir, json_file)
                    patches_dir = os.path.join(item_dir, "patches")
                    patch_main_path = os.path.join(patches_dir, json_file)

                    has_override_json = os.path.isfile(override_json_path)
                    has_patch = os.path.isfile(patch_main_path)

                    if not has_override_json and not has_patch:
                        continue

                    try:
                        meta = {}

                        # 1. 优先读取 override 主 JSON
                        if has_override_json:
                            with open(override_json_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                        elif primary_path:
                            # 2. 没有 override 主 JSON 时回退到 primary cache
                            primary_json_path = os.path.join(primary_path, folder_key, tmdb_id, json_file)
                            if os.path.isfile(primary_json_path):
                                with open(primary_json_path, 'r', encoding='utf-8') as f:
                                    meta = json.load(f)

                        # 3. patches 最高优先级，覆盖合并到 meta
                        if has_patch:
                            try:
                                with open(patch_main_path, 'r', encoding='utf-8') as f:
                                    patch_data = json.load(f)
                                if isinstance(patch_data, dict) and patch_data:
                                    deep_merge_dict(meta, patch_data)
                            except Exception as e:
                                log_audit("编辑", "失败", f"读取 patches 失败 {patch_main_path}: {e}", level="WARN")

                        # 提取核心字段，完全摒弃 full_metadata 以减小体积
                        results.append({
                            "tmdb_id": tmdb_id,
                            "type": db_type,
                            "item_type": folder_key,
                            "title": meta.get('title') or meta.get('name'),
                            "original_title": meta.get('original_title') or meta.get('original_name'),
                            "year": (meta.get('release_date') or meta.get('first_air_date') or "")[:4],
                            "release_date": meta.get('release_date') or meta.get('first_air_date'),
                            "poster_path": meta.get('poster_path'),
                            "genres": meta.get('genres', []),
                            "vote_average": meta.get('vote_average'),
                            "overview": meta.get('overview')
                        })
                    except Exception as e:
                        log_audit("编辑", "失败", f"读取文件失败: {e}", level="ERROR")
            return results

        try:
            items = await asyncio.to_thread(_scan_disk)
            return True, items
        except Exception as e:
            return False, str(e)
