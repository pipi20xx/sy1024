import json
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..schemas.tmdb_bgm_mapping import (
    TmdbBgmMappingItem,
    TmdbBgmMappingList,
    DiffItem,
    ImportDiffResponse,
    TmdbBgmMappingUpdate
)
from ..models import TmdbBgmMapping
from ..database import TmdbBgmMappingSessionLocal
from ..logger import log_audit



class TmdbBgmMappingService:
    async def load_mappings(
        self,
        search: Optional[str] = None,
        tmdb_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 60,
    ) -> TmdbBgmMappingList:
        async with TmdbBgmMappingSessionLocal() as session:
            query = select(TmdbBgmMapping)
            count_query = select(func.count()).select_from(TmdbBgmMapping)

            # 类型筛选
            if tmdb_type and tmdb_type != 'all':
                query = query.where(TmdbBgmMapping.tmdb_type == tmdb_type)
                count_query = count_query.where(TmdbBgmMapping.tmdb_type == tmdb_type)

            # 搜索（按 TMDB ID）
            if search:
                try:
                    search_int = int(search)
                    query = query.where(TmdbBgmMapping.tmdb_id == search_int)
                    count_query = count_query.where(TmdbBgmMapping.tmdb_id == search_int)
                except ValueError:
                    # 非数字搜索，尝试模糊匹配 season_mappings 中的 BGM ID
                    query = query.where(TmdbBgmMapping.season_mappings.contains(search))
                    count_query = count_query.where(TmdbBgmMapping.season_mappings.contains(search))

            # 总数
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

            result = await session.execute(query)
            db_mappings = result.scalars().all()

            mappings = []
            for db_mapping in db_mappings:
                try:
                    season_mappings = json.loads(db_mapping.season_mappings) if db_mapping.season_mappings else {}
                    mappings.append(TmdbBgmMappingItem(
                        tmdb_id=db_mapping.tmdb_id,
                        tmdb_type=db_mapping.tmdb_type,
                        season_mappings=season_mappings
                    ))
                except Exception as e:
                    log_audit("映射", "解析", f"解析 season_mappings 失败 (TMDB {db_mapping.tmdb_id}): {e}", level="ERROR")
            return TmdbBgmMappingList(
                items=mappings,
                total=total,
                page=page,
                page_size=page_size,
            )

    async def export_mappings(self) -> List[Dict[str, Any]]:
        mappings = await self.load_mappings(page_size=1000000)
        export_data = []
        for item in mappings.items:
            season_mappings = {}
            for season_num, bgm_ids in item.season_mappings.items():
                if bgm_ids:  # 只保留非空的 BGM ID 列表
                    season_mappings[season_num] = bgm_ids
            export_data.append({
                "tmdb_id": item.tmdb_id,
                "tmdb_type": item.tmdb_type,
                "season_mappings": season_mappings
            })
        return export_data

    async def import_and_diff(self, import_data: List[TmdbBgmMappingItem]) -> ImportDiffResponse:
        try:
            current_mappings = await self.load_mappings(page_size=1000000)
            current_map = self._create_lookup_map(current_mappings.items)
            import_map = self._create_lookup_map(import_data)
            
            diff_items: List[DiffItem] = []
            stats = {"new": 0, "modified": 0, "deleted": 0, "unchanged": 0}
            
            all_keys = set(current_map.keys()) | set(import_map.keys())
            
            for key in all_keys:
                tmdb_id, tmdb_type = key
                current_seasons = current_map.get(key, {})
                import_seasons = import_map.get(key, {})
                
                all_seasons = set(current_seasons.keys()) | set(import_seasons.keys())
                
                for season_num in all_seasons:
                    current_bgm_ids = set(current_seasons.get(season_num, []))
                    import_bgm_ids = set(import_seasons.get(season_num, []))
                    
                    if not current_bgm_ids and not import_bgm_ids:
                        continue
                    
                    if not current_bgm_ids:
                        diff_type = "new"
                        stats["new"] += 1
                    elif not import_bgm_ids:
                        diff_type = "deleted"
                        stats["deleted"] += 1
                    elif current_bgm_ids != import_bgm_ids:
                        diff_type = "modified"
                        stats["modified"] += 1
                    else:
                        diff_type = "unchanged"
                        stats["unchanged"] += 1
                        continue  # 数据完全相同，不创建 DiffItem
                    
                    diff_item = DiffItem(
                        tmdb_id=tmdb_id,
                        tmdb_type=tmdb_type,
                        season_number=season_num,
                        old_bgm_ids=list(current_bgm_ids),
                        new_bgm_ids=list(import_bgm_ids),
                        diff_type=diff_type
                    )
                    diff_items.append(diff_item)
            
            return ImportDiffResponse(diff_items=diff_items, stats=stats)
        except Exception as e:
            log_audit("映射", "导入", f"导入差异比对失败: {e}", level="ERROR")
            raise

    async def apply_import(self, selected_diff_items: List[DiffItem]) -> bool:
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                # 按照 (tmdb_id, tmdb_type) 分组
                grouped_items: Dict[Tuple[int, str], List[DiffItem]] = {}
                for diff_item in selected_diff_items:
                    key = (diff_item.tmdb_id, diff_item.tmdb_type)
                    if key not in grouped_items:
                        grouped_items[key] = []
                    grouped_items[key].append(diff_item)
                
                # 对每个组进行一次数据库操作
                for (tmdb_id, tmdb_type), items in grouped_items.items():
                    result = await session.execute(
                        select(TmdbBgmMapping).where(
                            TmdbBgmMapping.tmdb_id == tmdb_id,
                            TmdbBgmMapping.tmdb_type == tmdb_type
                        )
                    )
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        season_mappings = json.loads(existing.season_mappings) if existing.season_mappings else {}
                    else:
                        season_mappings = {}
                    
                    # 处理该组中的所有 diff_item
                    for diff_item in items:
                        if diff_item.diff_type == "deleted":
                            season_mappings.pop(diff_item.season_number, None)
                        else:
                            season_mappings[diff_item.season_number] = diff_item.new_bgm_ids
                    
                    if season_mappings:
                        season_mappings_json = json.dumps(season_mappings, ensure_ascii=False)
                        if existing:
                            existing.season_mappings = season_mappings_json
                        else:
                            new_mapping = TmdbBgmMapping(
                                tmdb_id=tmdb_id,
                                tmdb_type=tmdb_type,
                                season_mappings=season_mappings_json
                            )
                            session.add(new_mapping)
                    elif existing:
                        # 如果 season_mappings 为空且存在记录，则删除该记录
                        await session.delete(existing)
                
                await session.commit()
                log_audit("映射", "导入", f"已应用 {len(selected_diff_items)} 条差异到数据库")
                return True
        except Exception as e:
            log_audit("映射", "导入", f"应用导入失败: {e}", level="ERROR")
            return False

    async def update_mapping(self, update: TmdbBgmMappingUpdate) -> bool:
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                result = await session.execute(
                    select(TmdbBgmMapping).where(
                        TmdbBgmMapping.tmdb_id == update.tmdb_id,
                        TmdbBgmMapping.tmdb_type == update.tmdb_type
                    )
                )
                existing = result.scalar_one_or_none()
                
                season_mappings_json = json.dumps(update.season_mappings, ensure_ascii=False)
                
                if existing:
                    existing.season_mappings = season_mappings_json
                    log_audit("映射", "更新", f"更新已有映射: TMDB {update.tmdb_id} ({update.tmdb_type})")
                else:
                    new_mapping = TmdbBgmMapping(
                        tmdb_id=update.tmdb_id,
                        tmdb_type=update.tmdb_type,
                        season_mappings=season_mappings_json
                    )
                    session.add(new_mapping)
                    log_audit("映射", "更新", f"新建映射: TMDB {update.tmdb_id} ({update.tmdb_type})")
                
                await session.commit()
                return True
        except Exception as e:
            log_audit("映射", "更新", f"更新映射失败 (TMDB {update.tmdb_id}): {e}", level="ERROR")
            return False

    async def delete_mapping(self, tmdb_id: int, tmdb_type: str) -> bool:
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                result = await session.execute(
                    select(TmdbBgmMapping).where(
                        TmdbBgmMapping.tmdb_id == tmdb_id,
                        TmdbBgmMapping.tmdb_type == tmdb_type
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    await session.delete(existing)
                    log_audit("映射", "删除", f"已从数据库删除映射: TMDB {tmdb_id} ({tmdb_type})")
                else:
                    log_audit("映射", "删除", f"映射不存在，无需删除: TMDB {tmdb_id} ({tmdb_type})", level="WARN")

                await session.commit()
                return True
        except Exception as e:
            log_audit("映射", "删除", f"删除映射失败 (TMDB {tmdb_id}): {e}", level="ERROR")
            return False

    async def clear_all_mappings(self) -> bool:
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                await session.execute(delete(TmdbBgmMapping))
                await session.commit()
                log_audit("映射", "清除", "已清除数据库中所有映射记录")
                return True
        except Exception as e:
            log_audit("映射", "清除", f"清除所有映射失败: {e}", level="ERROR")
            return False

    def _create_lookup_map(self, mappings: List[TmdbBgmMappingItem]) -> Dict[tuple, Dict[str, List[int]]]:
        lookup_map = {}
        for mapping in mappings:
            key = (mapping.tmdb_id, mapping.tmdb_type)
            lookup_map[key] = mapping.season_mappings
        return lookup_map
