import json
from typing import AsyncGenerator, Dict, Any, List, Set
from sqlalchemy import select
from .. import globals
from .bangumi_provider import BangumiProvider
from .metadata_mapper import MetadataMapper
from ..database import MediaRelationsSessionLocal, TmdbBgmMappingSessionLocal
from ..models import TmdbBangumiMap, TmdbBgmMapping
from ..logger import log_audit


class EmbyTagWriterService:
    def __init__(self):
        pass

    async def _format_sse(self, type: str, message: Any) -> str:
        return f"data: {json.dumps({'type': type, 'message': message}, ensure_ascii=False)}\n\n"

    async def _get_bangumi_ids_from_tmdb(self, tmdb_id: str, tmdb_type: str) -> tuple[List[int], str]:
        # Map Emby 'Series'/'Movie' to DB 'tv'/'movie'
        db_type = 'tv' if tmdb_type == 'Series' else 'movie'
        try:
            # 优先使用新表 TmdbBgmMapping（手动映射表）
            async with TmdbBgmMappingSessionLocal() as session:
                stmt = select(TmdbBgmMapping).where(
                    TmdbBgmMapping.tmdb_id == int(tmdb_id),
                    TmdbBgmMapping.tmdb_type == db_type
                )
                result = await session.execute(stmt)
                mapping = result.scalar_one_or_none()
                if mapping:
                    season_mappings = json.loads(mapping.season_mappings) if mapping.season_mappings else {}
                    # 合并所有季度的 bangumi_id
                    all_bangumi_ids = []
                    for season_bgm_ids in season_mappings.values():
                        all_bangumi_ids.extend(season_bgm_ids)
                    return all_bangumi_ids, "手动映射表"
            
            # 如果新表没找到，使用旧表 TmdbBangumiMap（自动化表）
            async with MediaRelationsSessionLocal() as session:
                stmt = select(TmdbBangumiMap.bangumi_id).where(
                    TmdbBangumiMap.tmdb_id == tmdb_id,
                    TmdbBangumiMap.tmdb_type == db_type
                )
                result = await session.execute(stmt)
                bangumi_ids = [row[0] for row in result.fetchall()]
                if bangumi_ids:
                    return bangumi_ids, "自动化表"
                return [], "未找到"
        except Exception as e:
            log_audit("Emby标签", "失败", f"查询关联数据库出错: {e}", level="ERROR")
            return [], "查询错误"

    def _generate_detailed_log(self, field_name: str, existing_items: List[str], new_items: List[str], final_items: List[str], is_merge_mode: bool) -> str:
        log_lines = []
        log_lines.append(f"  - 处理字段: [{field_name}]")
        
        # Always show current state for transparency
        log_lines.append(f"    - Emby 中已有: {existing_items or '无'}")
        log_lines.append(f"    - Bangumi 数据: {new_items or '无'}")
        
        if is_merge_mode:
            added_items = sorted(list(set(new_items) - set(existing_items)))
            log_lines.append(f"    - 本次新增: {added_items or '无'}")
        
        log_lines.append(f"    - {'合并后' if is_merge_mode else '覆盖为'}: {final_items or '无'}")
        return "\n".join(log_lines)

    async def sync_to_emby(self, options: Dict[str, Any]) -> AsyncGenerator[str, None]:
        try:
            # Access client via system service facade
            emby_client = None
            if globals.service and globals.service.emby_integration_service:
                emby_client = globals.service.emby_integration_service.emby_client
            
            # Initialize New Provider and Mapper
            provider = BangumiProvider()
            mapper = MetadataMapper()

            if not emby_client:
                yield await self._format_sse("error", "Emby 客户端未初始化")
                return

            item_types_to_scan = options.get("item_types", "Movie,Series")
            
            # Load Allowed Tags: 优先使用前端传来的白名单，回退到配置文件
            allowed_tags_list = options.get("allowed_tags_filter") or provider.get_allowed_tags()
            allowed_tags_filter = set(t.lower() for t in allowed_tags_list) if allowed_tags_list else set()
            yield await self._format_sse("log", f"标签白名单: {len(allowed_tags_filter)} 个标签" + ("（未配置，不过滤）" if not allowed_tags_filter else ""))

            is_preview = options.get("is_preview", True)
            write_to_genres = options.get("write_to_genres", False)
            write_to_tags = options.get("write_to_tags", False)
            is_merge_mode = options.get("is_merge_mode", True)

            yield await self._format_sse("log", f"模式: {'[预览]' if is_preview else '[写入]'} | 写入类型: {write_to_genres} | 写入标签: {write_to_tags} | 合并模式: {is_merge_mode}")
            
            yield await self._format_sse("log", "正在获取 Emby 媒体库列表...")
            all_emby_items = await emby_client.get_all_items(item_types=item_types_to_scan)
            total_items = len(all_emby_items)
            yield await self._format_sse("log", f"获取完成，共 {total_items} 个项目。")

            # 1. Map Emby Items to BGM IDs
            all_bgm_ids_to_fetch_tags: Set[int] = set()
            emby_to_bgm_map: Dict[str, tuple[List[int], str]] = {}
            
            for item in all_emby_items:
                tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                item_type = item.get("Type") # Movie or Series
                if tmdb_id and item_type:
                    bgm_ids, source_table = await self._get_bangumi_ids_from_tmdb(str(tmdb_id), item_type)
                    if bgm_ids:
                        emby_to_bgm_map[item['Id']] = (bgm_ids, source_table)
                        all_bgm_ids_to_fetch_tags.update(bgm_ids)
            
            yield await self._format_sse("log", f"关联到 {len(all_bgm_ids_to_fetch_tags)} 个 Bangumi 条目。")
            yield await self._format_sse("log", "准备开始处理...")

            # 3. Process Items
            processed_count = 0
            for i, item in enumerate(all_emby_items):
                item_id = item.get("Id")
                bgm_data = emby_to_bgm_map.get(item_id)
                
                # Report progress periodically
                if i % 5 == 0:
                    yield await self._format_sse("progress", int(((i + 1) / total_items) * 100))
                
                if bgm_data is not None:
                    bgm_ids, source_table = bgm_data
                    item_name = item.get("Name", f"Item {item_id}")
                    
                    combined_tags: Set[str] = set()
                    logs_for_item = []

                    for bgm_id in bgm_ids:
                        # Fetch data from Provider (Cache or API)
                        bgm_result = await provider.get_subject(bgm_id)
                        subject_data = bgm_result.get("data")
                        source_code = bgm_result.get("source", "miss")
                        source_str = provider.get_source_label(source_code)

                        logs_for_item.append(f"  - Bangumi ID: {bgm_id} | 数据来源: {source_str}")

                        tags_for_id = []
                        if subject_data:
                            mapped = mapper.map_subject(subject_data)
                            tags_for_id = mapped.get('tags', [])
                        
                        if tags_for_id:
                            combined_tags.update(tags_for_id)
                    
                    # Apply Tag Filter
                    final_tags = []
                    if allowed_tags_filter:
                        final_tags = [t for t in combined_tags if t.lower() in allowed_tags_filter]
                    else:
                        final_tags = list(combined_tags)
                    
                    if final_tags:
                        detailed_logs = []
                        genres_to_set, tags_to_set = None, None
                        has_changes = False
                        
                        if write_to_genres:
                            existing = item.get("Genres", [])
                            genres_to_set = sorted(list(set(existing + final_tags))) if is_merge_mode else sorted(list(set(final_tags)))
                            detailed_logs.append(self._generate_detailed_log("类型 (Genres)", existing, final_tags, genres_to_set, is_merge_mode))
                            if set(existing) != set(genres_to_set):
                                has_changes = True
                        
                        if write_to_tags:
                            existing = item.get("Tags", [])
                            tags_to_set = sorted(list(set(existing + final_tags))) if is_merge_mode else sorted(list(set(final_tags)))
                            detailed_logs.append(self._generate_detailed_log("标签 (Tags)", existing, final_tags, tags_to_set, is_merge_mode))
                            if set(existing) != set(tags_to_set):
                                has_changes = True
                        
                        # Output logs
                        yield await self._format_sse("log", f"\n({i+1}/{total_items}) 处理:《{item_name}》 (ID: {item_id}) [数据来源: {source_table}]")
                        for l in logs_for_item:
                            yield await self._format_sse("log", l)
                        
                        log_prefix = "[预览]" if is_preview else "[写入]"
                        yield await self._format_sse("log", f"{log_prefix}\n" + "\n".join(detailed_logs))

                        if not has_changes:
                            yield await self._format_sse("log", "  > 内容与目标一致，跳过写入。")
                        elif not is_preview:
                            success, msg = await emby_client.update_item_metadata(item_id, genres=genres_to_set, tags=tags_to_set)
                            if success:
                                if msg != "No Change":
                                    processed_count += 1
                                    yield await self._format_sse("log", "  > 写入成功")
                                else:
                                    yield await self._format_sse("log", "  > Emby返回: 无需变更")
                            else:
                                yield await self._format_sse("error", f"  > 写入失败: {msg}")
                        else:
                            processed_count += 1
            
            yield await self._format_sse("finished", f"任务完成！成功写入/预览 {processed_count} 个项目。")

        except Exception as e:
            log_audit("Emby标签", "处理", f"Sync error: {e}", level="ERROR")
            yield await self._format_sse("error", f"系统错误: {e}")