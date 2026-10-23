import re
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, delete, or_, func, String
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import ActorsSessionLocal
from ..models import Actor
from ..websocket_manager import manager
from .. import globals
from ..logger import log_audit


class ActorService:
    def __init__(self):
        pass

    def get_origin_name_smart(self, data: Dict[str, Any]) -> str:
        """
        根据出生地 (place_of_birth) 智能推断原产地姓名。
        参考 ai_studio_code (91).py
        """
        place = data.get('place_of_birth', '') or ''
        akas = data.get('also_known_as', [])
        default_name = data.get('name', '') # TMDB的主名
        
        if not akas:
            return default_name

        # 正则表达式
        regex_han = re.compile(r'[\u4e00-\u9fa5]')  # 汉字
        regex_kana = re.compile(r'[\u3040-\u30ff]') # 日文假名
        regex_hangul = re.compile(r'[\uac00-\ud7af]') # 韩文谚文
        regex_cyrillic = re.compile(r'[\u0400-\u04FF]') # 西里尔(俄文)

        target_script = None

        # --- A. 地区判定 ---
        if any(k in place for k in ["China", "Hong Kong", "Taiwan", "Beijing", "Shanghai", "Canton"]):
            target_script = "chinese"
        elif any(k in place for k in ["Japan", "Tokyo", "Osaka", "Kyoto", "Okinawa"]):
            target_script = "japanese"
        elif any(k in place for k in ["Korea", "Seoul", "Busan"]):
            target_script = "korean"
        elif any(k in place for k in ["Russia", "Soviet", "Ukraine", "Moscow"]):
             target_script = "cyrillic"
        elif any(k in place for k in ["Thai", "Bangkok"]):
             target_script = "thai"

        # --- B. 别名匹配 ---
        found_name = None
        
        for aka in akas:
            if target_script == "chinese":
                if regex_han.search(aka) and not regex_kana.search(aka) and not regex_hangul.search(aka):
                    found_name = aka
                    break 
            
            elif target_script == "japanese":
                if regex_kana.search(aka):
                    found_name = aka
                    break
                elif regex_han.search(aka) and not found_name:
                    found_name = aka

            elif target_script == "korean":
                if regex_hangul.search(aka):
                    found_name = aka
                    break
            
            elif target_script == "cyrillic":
                if regex_cyrillic.search(aka):
                    found_name = aka
                    break
        
        if not found_name and not any(k in place for k in ["USA", "United Kingdom", "Australia", "Canada"]):
             for aka in akas:
                if any(ord(c) > 127 for c in aka):
                    found_name = aka
                    break
        
        return found_name if found_name else default_name

    async def update_actors_from_tmdb(self, actor_ids: List[int]) -> Tuple[int, int]:
        """从 TMDB 更新演员信息。返回 (成功数量, 失败数量)"""
        success_count = 0
        fail_count = 0
        total = len(actor_ids)
        
        await manager.broadcast_progress("actor_update", "running", 0, total, f"开始更新 {total} 位演员...")

        async with ActorsSessionLocal() as session:
            stmt = select(Actor).where(Actor.id.in_(actor_ids))
            res = await session.execute(stmt)
            actors = res.scalars().all()
            
            for idx, actor in enumerate(actors):
                try:
                    log_audit("演员", "开始", f"🔄 正在从 TMDB 更新演员: {actor.name} (ID: {actor.tmdb_id})")
                    data = await globals.service.tmdb_metadata_service.fetch_tmdb_data("person", str(actor.tmdb_id), "zh-CN")
                    
                    # 1. 提取中文名
                    tmdb_main_name = data.get('name', '')
                    chinese_name = ""
                    for t in data.get('translations', {}).get('translations', []):
                        if t.get('iso_639_1') in ['zh', 'cn']:
                            t_data = t.get('data', {})
                            if t_data.get('name'):
                                chinese_name = t_data.get('name')
                                break
                    
                    # 2. 提取原产地名
                    origin_name = self.get_origin_name_smart(data)
                    
                    # 3. 兜底逻辑
                    final_name = chinese_name or origin_name or tmdb_main_name
                    
                    # 4. 更新数据库（仅补充缺失字段，不覆盖用户已编辑的 name/original_name）
                    async with session.begin_nested():
                        # name 和 original_name：仅在为空时才从 TMDB 填充
                        name_changed = False
                        origin_changed = False
                        if not actor.name:
                            actor.name = final_name
                            name_changed = True
                        if not actor.original_name:
                            actor.original_name = origin_name
                            origin_changed = True
                        # profile_path 和 metadata_json 始终更新
                        actor.profile_path = data.get('profile_path', '')
                        actor.metadata_json = json.dumps(data, ensure_ascii=False)
                        await session.flush()

                    log_audit("演员", "完成", f"✅ 从 TMDB 获取成功: {actor.name} (ID: {actor.tmdb_id}) | 姓名{'(已补充)' if name_changed else '(保留)'}: {actor.name} | 原始姓名{'(已补充)' if origin_changed else '(保留)'}: {actor.original_name}")
                    
                    success_count += 1
                except Exception as e:
                    log_audit("演员", "失败", f"❌ 更新演员 {actor.tmdb_id} 失败: {e}", level="ERROR")
                    fail_count += 1
                
                # 广播进度
                if (idx + 1) % 5 == 0 or (idx + 1) == total:
                    await manager.broadcast_progress("actor_update", "running", idx + 1, total, f"正在更新演员: {actor.name} ({idx+1}/{total})")

                # 适当延时
                await asyncio.sleep(0.2)
            
            await session.commit()
            
        await manager.broadcast_progress("actor_update", "completed", total, total, f"演员更新完成：成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count

    async def update_all_actors_from_tmdb_task(self):
        """后台任务：全量从 TMDB 更新所有演员信息"""
        log_audit("演员", "初始化", "🚀 启动全量更新演员任务...")
        async with ActorsSessionLocal() as session:
            result = await session.execute(select(Actor.id))
            all_ids = result.scalars().all()
            total = len(all_ids)
            log_audit("演员", "更新", f"📊 共有 {total} 位演员待更新")
        # 调用现有的批量更新逻辑
        success, fail = await self.update_actors_from_tmdb(all_ids)
        log_audit("演员", "完成", f"🏁 全量更新演员任务完成: 成功 {success}, 失败 {fail}")
    async def get_actors(self, search: Optional[str] = None, duplicate_type: Optional[str] = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        async with ActorsSessionLocal() as session:
            log_audit("演员", "查询", f"🔍 查询演员列表: search='{search}', duplicate_type='{duplicate_type}', page={page}")
            query = select(Actor)

            if duplicate_type and duplicate_type in ['tmdb_id', 'name', 'original_name']:
                target_col = getattr(Actor, duplicate_type)
                dup_subq = (select(target_col.label('dup_val')).group_by(target_col).having(func.count(Actor.id) > 1)).subquery()
                check_stmt = select(func.count()).select_from(dup_subq)
                check_res = await session.execute(check_stmt)
                dup_count = check_res.scalar() or 0
                log_audit("演员", "处理", f"📊 发现重复的 {duplicate_type} 值共 {dup_count} 组")
                if dup_count == 0:
                    return {"items": [], "total": 0, "page": page, "page_size": page_size}

                query = query.join(dup_subq, target_col == dup_subq.c.dup_val)
                query = query.order_by(target_col.asc(), Actor.id.desc())
            else:
                query = query.order_by(Actor.id.desc())

            if search:
                if all(c.isdigit() or c == ',' or c.isspace() for c in search):
                    try:
                        id_list = [int(s.strip()) for s in search.split(',') if s.strip().isdigit()]
                        if id_list:
                            query = query.where(Actor.tmdb_id.in_(id_list))
                        else:
                            query = query.where(or_(Actor.name.contains(search), Actor.original_name.contains(search)))
                    except:
                        query = query.where(or_(Actor.name.contains(search), Actor.original_name.contains(search)))
                else:
                    query = query.where(or_(Actor.name.contains(search), Actor.original_name.contains(search)))

            final_count_stmt = select(func.count()).select_from(query.subquery())
            final_total_res = await session.execute(final_count_stmt)
            total = final_total_res.scalar() or 0
            
            log_audit("演员", "处理", f"📈 最终过滤后的记录总数: {total}")
            result = await session.execute(query.offset((page - 1) * page_size).limit(page_size))
            actors = result.scalars().all()

            return {
                "items": [actor.to_dict() for actor in actors],
                "total": total,
                "page": page,
                "page_size": page_size
            }

    async def get_all_actors(self) -> List[Dict[str, Any]]:
        """获取数据库中所有的演员（不分页）"""
        async with ActorsSessionLocal() as session:
            result = await session.execute(select(Actor))
            actors = result.scalars().all()
            return [actor.to_dict() for actor in actors]

    async def batch_import_actors(self, actors_data: List[Dict[str, Any]]):
        async with ActorsSessionLocal() as session:
            # 1. 整理当前批次的数据
            to_process = []
            tmdb_ids = set()
            for item in actors_data:
                aid = item.get('id')
                name = str(item.get('name', '')).strip()
                oname = str(item.get('original_name', '')).strip()
                if not aid or not name: continue
                
                # 转换为标准格式
                tmdb_id_int = int(aid)
                to_process.append({
                    'tmdb_id': tmdb_id_int,
                    'name': name,
                    'original_name': oname
                })
                tmdb_ids.add(tmdb_id_int)

            if not to_process:
                return

            # 2. 一次性查询数据库中已存在的、且具有这些 TMDB ID 的演员
            stmt = select(Actor).where(Actor.tmdb_id.in_(tmdb_ids))
            res = await session.execute(stmt)
            existing_db_actors = res.scalars().all()
            
            # 3. 构建已存在演员的特征集合 (tmdb_id, name, original_name) 用于快速比对
            existing_keys = {
                (a.tmdb_id, a.name, a.original_name) 
                for a in existing_db_actors
            }
            
            # 4. 过滤出真正需要新增的演员
            new_actors = []
            seen_in_batch = set() # 防止当前批次内部重复
            
            for p in to_process:
                key = (p['tmdb_id'], p['name'], p['original_name'])
                if key not in existing_keys and key not in seen_in_batch:
                    new_actors.append(Actor(
                        tmdb_id=p['tmdb_id'], 
                        name=p['name'], 
                        original_name=p['original_name'],
                        duplicate_tmdb_id=None
                    ))
                    seen_in_batch.add(key)
            
            # 5. 批量写入
            if new_actors:
                session.add_all(new_actors)
                await session.commit()
                log_audit("演员", "创建", f"批量导入: 提交了 {len(new_actors)} 位新演员")
            else:
                # 即使没有新增，也要结束事务
                await session.commit()

    async def delete_actor(self, actor_id: int):
        async with ActorsSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Actor).where(Actor.id == actor_id))
        log_audit("演员", "清理", f"已删除演员 ID: {actor_id}")
    async def delete_all_actors(self):
        async with ActorsSessionLocal() as session:
            async with session.begin():
                await session.execute(delete(Actor))
        log_audit("演员", "处理", "已清空所有演员数据")
    async def update_actor(self, actor_id: int, data: Dict[str, Any]) -> Tuple[bool, Any]:
        async with ActorsSessionLocal() as session:
            async with session.begin():
                stmt = select(Actor).where(Actor.id == actor_id)
                result = await session.execute(stmt)
                actor = result.scalar_one_or_none()
                if not actor: return False, "未找到该演员"
                if 'tmdb_id' in data: actor.tmdb_id = int(data['tmdb_id'])
                if 'name' in data: actor.name = str(data['name']).strip()
                if 'original_name' in data: actor.original_name = str(data['original_name']).strip()
                if 'duplicate_tmdb_id' in data:
                    raw_val = str(data['duplicate_tmdb_id']).strip()
                    if raw_val:
                        import re
                        found_ids = re.findall(r'\d+', raw_val)
                        if found_ids:
                            seen = set()
                            unique_ids = [x for x in found_ids if not (x in seen or seen.add(x))]
                            actor.duplicate_tmdb_id = ','.join(unique_ids)
                        else: actor.duplicate_tmdb_id = None
                    else: actor.duplicate_tmdb_id = None
                updated_dict = actor.to_dict()
                log_audit("演员", "更新", f"已更新演员信息: {actor.name} (ID: {actor_id})")
                return True, updated_dict

    async def prepare_merge(self, merge_type: str) -> List[Dict[str, Any]]:
        import re
        def is_chinese(text):
            if not text: return False
            return bool(re.search(r'[\u4e00-\u9fa5]', str(text)))

        async with ActorsSessionLocal() as session:
            target_col = getattr(Actor, merge_type)
            subq = (select(target_col).group_by(target_col).having(func.count(Actor.id) > 1))
            dup_values_res = await session.execute(subq)
            dup_values = dup_values_res.scalars().all()
            
            merge_groups = []
            for val in dup_values:
                stmt = select(Actor).where(target_col == val).order_by(Actor.id.asc())
                res = await session.execute(stmt)
                group_items = res.scalars().all()
                
                suggested_name = group_items[0].name
                for item in group_items:
                    if is_chinese(item.name):
                        suggested_name = item.name
                        break
                
                suggested_original_name = group_items[0].original_name
                suggested_tmdb_id = group_items[0].tmdb_id
                
                all_names = sorted(list(set(item.name for item in group_items if item.name)))
                all_original_names = sorted(list(set(item.original_name for item in group_items if item.original_name)))
                
                # 核心：收集该组内所有出现的 TMDB ID（包括主 ID 和副 ID 里的）
                all_tmdb_ids = set()
                for item in group_items:
                    all_tmdb_ids.add(item.tmdb_id)
                    if item.duplicate_tmdb_id:
                        # 尝试从副 ID 字符串中提取数字
                        found = re.findall(r'\d+', item.duplicate_tmdb_id)
                        for f in found: all_tmdb_ids.add(int(f))
                
                sorted_ids = sorted(list(all_tmdb_ids))

                merge_groups.append({
                    "merge_value": str(val),
                    "suggested_name": suggested_name,
                    "suggested_original_name": suggested_original_name,
                    "suggested_tmdb_id": suggested_tmdb_id, # 默认取第一个作为主 ID
                    "name_options": all_names,
                    "original_name_options": all_original_names,
                    "tmdb_id_options": sorted_ids, # 所有的 ID 候选
                    "all_ids_pool": sorted_ids, # 原始池，用于执行时计算副 ID
                    "count": len(group_items),
                    "item_ids": [item.id for item in group_items]
                })
            return merge_groups

    async def execute_merge(self, merge_plan: List[Dict[str, Any]]) -> Tuple[bool, str]:
        async with ActorsSessionLocal() as session:
            async with session.begin():
                for group in merge_plan:
                    item_ids = group.get('item_ids', [])
                    if not item_ids: continue
                    
                    main_id, other_ids = item_ids[0], item_ids[1:]
                    stmt = select(Actor).where(Actor.id == main_id)
                    res = await session.execute(stmt)
                    main_actor = res.scalar_one_or_none()
                    
                    if main_actor:
                        chosen_primary_id = int(group.get('suggested_tmdb_id'))
                        main_actor.name = group.get('suggested_name')
                        main_actor.original_name = group.get('suggested_original_name')
                        main_actor.tmdb_id = chosen_primary_id
                        
                        # 计算副 ID：池子里除了选中的主 ID 以外的所有 ID
                        id_pool = group.get('all_ids_pool', [])
                        secondary_ids = [str(i) for i in id_pool if i != chosen_primary_id]
                        main_actor.duplicate_tmdb_id = ','.join(secondary_ids) if secondary_ids else None
                        
                    if other_ids:
                        await session.execute(delete(Actor).where(Actor.id.in_(other_ids)))
                
                log_audit("演员", "完成", f"合并操作完成，共合并 {len(merge_plan)} 组重复数据。")
                return True, f"成功合并 {len(merge_plan)} 组重复数据"
