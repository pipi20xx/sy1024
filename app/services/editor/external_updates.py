import os
import json
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union

from ...common import SOURCE_OVERRIDE, SOURCE_PRIMARY
from ...logger import log_audit
from ..bangumi_provider import BangumiProvider
from ..metadata_mapper import MetadataMapper


class ExternalUpdatesMixin:
    """从外部数据源（Bangumi、Emby）更新元数据的方法。"""

    async def update_metadata_from_bangumi(
        self,
        item_type: str,
        item_id: str,
        bangumi_id: Optional[int] = None,
        fields: Optional[List[str]] = None,
        force_refresh: bool = False,
        use_whitelist: bool = False,
        mode: str = 'merge',
        auto_match: bool = False
    ) -> Tuple[bool, str]:
        """
        Updates local item metadata using data fetched from Bangumi.
        If bangumi_id is not provided, tries to resolve it via RelationService.
        """
        log_audit("编辑", "开始", f"开始从 Bangumi 更新元数据: {item_type}/{item_id} (Bangumi ID: {bangumi_id or 'Auto'})")
        from ... import globals

        # Map item_type to tmdb_type
        tmdb_type = 'movie' if item_type == 'tmdb-movies2' else 'tv'
        target_type = "Movie" if item_type == "tmdb-movies2" else "Series"

        # 1. Resolve Bangumi ID
        if not bangumi_id:
            if not globals.relation_service:
                return False, "关联服务未初始化"

            relations = await globals.relation_service.get_relation(item_id, tmdb_type)
            if relations:
                bangumi_id = relations[0]['bangumi_id']
            elif auto_match:
                # Try to auto-match if allowed
                log_audit("编辑", "查询", f"项目 {item_id} ({item_type}) 无关联，尝试自动匹配...")
                rec = await globals.relation_service.get_single_recommendation(item_id, tmdb_type)
                if rec and rec.get('found') and rec.get('bangumi_id'):
                    bangumi_id = rec['bangumi_id']
                    rec_score = rec.get('score', 0)
                    log_audit("编辑", "完成", f"自动匹配成功: TMDB {item_id} -> BGM {bangumi_id} (Score: {rec_score})")
                    # Save the new relation
                    await globals.relation_service.save_relation(item_id, tmdb_type, bangumi_id)
                else:
                    return False, f"自动匹配失败: 未找到适合项目 {item_id} 的 Bangumi 条目。"
            else:
                return False, f"找不到项目 {item_id} ({item_type}) 的 Bangumi 关联。请先进行关联。"
        else:
            # If ID provided, save/update relation!
            if globals.relation_service:
                await globals.relation_service.save_relation(item_id, tmdb_type, bangumi_id)

        # 2. Fetch Data
        provider = BangumiProvider()
        # Force refresh to ensure latest data if requested
        subject_result = await provider.get_subject(bangumi_id, force_refresh=force_refresh)
        subject_data = subject_result.get("data")

        if not subject_data:
            return False, f"无法获取 Bangumi ID {bangumi_id} 的数据。"

        # New: Also fetch characters for cast mapping
        characters_result = await provider.get_characters(bangumi_id)
        characters_data = characters_result.get("data", [])

        # 3. Map Data
        mapper = MetadataMapper()
        mapped_data = mapper.map_subject(subject_data, target_type=target_type, characters_data=characters_data)

        if not mapped_data:
            return False, "映射 Bangumi 数据失败 (结果为空)。"

        # 4. Filter Fields
        if fields:
            # Normalize fields to internal keys
            # Front-end might send friendly names or keys.
            # Internal keys: title, original_title, overview, tags, vote_average, credits, networks...
            # We assume frontend sends valid internal keys.

            # FIX: Map generic frontend keys to specific schema keys for Series
            target_fields = set(fields)
            if target_type == 'Series':
                mapping = {
                    'title': 'name',
                    'original_title': 'original_name',
                    'release_date': 'first_air_date'
                }
                for generic, specific in mapping.items():
                    if generic in target_fields:
                        target_fields.add(specific)

            filtered_data = {k: v for k, v in mapped_data.items() if k in target_fields}

            # Special handling: 'credits' vs 'casts' (mapper output depends on type)
            # If user selected 'cast' or 'crew', we should include the relevant key
            if 'cast' in fields or 'crew' in fields or 'credits' in fields:
                if 'credits' in mapped_data: filtered_data['credits'] = mapped_data['credits']
                if 'casts' in mapped_data: filtered_data['casts'] = mapped_data['casts']

            if 'studios' in fields:
                if 'networks' in mapped_data: filtered_data['networks'] = mapped_data['networks']
                if 'production_companies' in mapped_data: filtered_data['production_companies'] = mapped_data['production_companies']

            mapped_data = filtered_data

        if not mapped_data:
            return False, "未选择任何字段或所选字段无数据。"

        # --- Whitelist Logic ---
        if use_whitelist and 'tags' in mapped_data:
            allowed_tags = provider.get_allowed_tags()
            # If whitelist exists, filter. If empty, behavior depends.
            # Usually empty whitelist in this context means "allow nothing" if user EXPLICITLY requested it?
            # Or "allow all"?
            # In tag writer service: if allowed_tags_filter: filter. else: allow all.
            # Let's mimic that: if whitelist is configured (non-empty), use it.
            if allowed_tags:
                allowed_set = set(t.lower() for t in allowed_tags)
                mapped_data['tags'] = [t for t in mapped_data['tags'] if t.lower() in allowed_set]
            # If whitelist is empty but user checked "Use Whitelist", maybe we should clear tags?
            # User request: "Use this whitelist". If whitelist is empty, logic says "Use empty list" -> Result empty.
            # But strictly following provider logic: provider returns [] if file read fails or empty.
            # Let's assume if user checked "Use Whitelist", they expect filtering.
            elif use_whitelist:
                # Whitelist is empty/missing, but user wants to use it.
                # If we follow strict "Allow List", then nothing is allowed.
                mapped_data['tags'] = []

        # --- Merge Logic ---
        if mode == 'merge':
            current_details = await self.get_item_full_details(item_type, item_id)
            if current_details:
                existing_metadata = current_details.get('full_metadata', {})

                # 1. Scalar Fields: Skip if exists (Fill Missing only)
                # We iterate over a copy of keys to safely delete
                for key in list(mapped_data.keys()):
                    if key in ['tags', 'genres', 'credits', 'casts', 'networks', 'production_companies']:
                        continue

                    existing_val = existing_metadata.get(key)

                    # Logic: If existing value is "truthy", we skip updating.
                    # Special case for numbers (like vote_average): 0 should often be treated as empty/missing.
                    should_skip = False
                    if isinstance(existing_val, (int, float)):
                        if existing_val > 0: should_skip = True
                    elif existing_val:  # Strings, etc.
                        should_skip = True

                    if should_skip:
                        del mapped_data[key]
                        log_audit("编辑", "处理", f"合并模式: 字段 '{key}' 本地已存在 ({existing_val})，跳过更新。")
                # 2. List Fields: Merge (Union)
                # Merge Tags
                if 'tags' in mapped_data:
                    existing_tags = current_details.get('tags', [])
                    new_tags = mapped_data['tags']
                    # Combine unique
                    mapped_data['tags'] = sorted(list(set(existing_tags + new_tags)))

                # Merge Genres (List of dicts)
                if 'genres' in mapped_data:
                    existing_genres = existing_metadata.get('genres', [])
                    new_genres = mapped_data['genres']  # [{'name': 'X'}, ...]

                    existing_names = set(g.get('name') for g in existing_genres if g.get('name'))

                    merged_genres = list(existing_genres)
                    for g in new_genres:
                        if g.get('name') not in existing_names:
                            merged_genres.append(g)
                            existing_names.add(g.get('name'))
                    mapped_data['genres'] = merged_genres

                # Merge Credits/Casts
                new_credits = mapped_data.get('credits') or mapped_data.get('casts')
                if new_credits:
                    # 获取现有的 credits
                    existing_credits = existing_metadata.get('credits') or existing_metadata.get('casts') or {}

                    merged_credits = {
                        "cast": self._merge_credits_lists(existing_credits.get("cast", []), new_credits.get("cast", []), "cast"),
                        "crew": self._merge_credits_lists(existing_credits.get("crew", []), new_credits.get("crew", []), "crew")
                    }
                    # 如果是集或季，可能还有 guest_stars
                    if "guest_stars" in new_credits or "guest_stars" in existing_credits:
                        merged_credits["guest_stars"] = self._merge_credits_lists(
                            existing_credits.get("guest_stars", []),
                            new_credits.get("guest_stars", []),
                            "cast"
                        )

                    # 保持键名一致性
                    target_key = 'credits' if 'credits' in mapped_data or 'credits' in existing_metadata else 'casts'
                    mapped_data[target_key] = merged_credits

        # Remove poster_path if not explicitly requested (or maybe never update it via this?)
        # For now, if filtered, we trust it. If not filtered, we might want to be careful.
        # But 'Update Metadata' usually implies text.
        if 'poster_path' in mapped_data:
            # Unless we implement image download, saving a URL string here might be useless
            # or handled by frontend?
            # Existing logic: update_item_metadata saves to JSON.
            pass

        # 5. Save
        # 特殊处理：如果只有 tags 字段，直接写入 tags.json，不需要编辑主元数据文件
        # tags.json 是独立存在于 Override 目录的，不受 Primary 缓存限制
        if list(mapped_data.keys()) == ['tags']:
            override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
            if override_path:
                final_override_folder = os.path.join(override_path, item_type, item_id)
                os.makedirs(final_override_folder, exist_ok=True)
                tags_json_path = os.path.join(final_override_folder, "tags.json")
                try:
                    with open(tags_json_path, "w", encoding="utf-8") as f:
                        json.dump({"tags": mapped_data['tags']}, f, indent=2, ensure_ascii=False)
                    await self.scanner_service._refresh_item_in_db(item_type, item_id)
                    log_audit("编辑", "完成", f"成功从 Bangumi (ID: {bangumi_id}) 更新标签: {mapped_data['tags']}")
                    return True, f"成功从 Bangumi (ID: {bangumi_id}) 更新标签。"
                except Exception as e:
                    return False, f"写入 tags.json 失败: {e}"
            else:
                return False, "未配置覆盖缓存目录。"

        success, msg, new_id = await self.update_item_metadata(item_type, item_id, mapped_data)

        if success:
            return True, f"成功从 Bangumi (ID: {bangumi_id}) 更新元数据。"
        else:
            return False, f"更新失败: {msg}"

    async def update_metadata_from_emby(self, item_type: str, emby_item_id: str, folder_tmdb_id: str, original_emby_item_type: str, fields_to_update: List[str], update_children: bool) -> Tuple[bool, str]:
        # Logic to determine local path
        if item_type == "tmdb-tv":
            json_filename = "series.json"
        elif item_type == "tmdb-movies2":
            json_filename = "all.json"
        else:
            return False, f"不支持的内部项目类型 '{item_type}'"

        json_path = self._get_actual_json_path(item_type, folder_tmdb_id, json_filename)
        local_item_path = None

        if not json_path:
            override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
            if override_path:
                local_item_path = os.path.join(override_path, item_type, folder_tmdb_id)
                os.makedirs(local_item_path, exist_ok=True)
            else:
                return False, f"找不到 {item_type}/{folder_tmdb_id} 的 {json_filename} 文件。"
        else:
            local_item_path = os.path.dirname(json_path)

        success, msg = await self.emby_integration_service.run_metadata_updater_core(
            item_type, emby_item_id, folder_tmdb_id, original_emby_item_type,
            fields_to_update, update_children, local_item_path
        )

        if success:
            await self.scanner_service._refresh_item_in_db(item_type, folder_tmdb_id)

        return success, msg
