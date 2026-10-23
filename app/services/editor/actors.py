import os
import json
import re
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union

from ...common import SOURCE_OVERRIDE, SOURCE_PRIMARY
from ...logger import log_audit


class ActorsMixin:
    """演员导入和标准化相关的方法。"""

    async def import_actors_from_override_cache(self) -> Tuple[bool, str]:
        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            return False, "错误：未配置覆盖缓存目录。"

        log_audit("编辑", "开始", "开始从覆盖缓存导入演员...")

        def _scan_files():
            scanned_actors = []
            # (tmdb_id, name, original_name)
            seen = set()

            for item_type_key in ['tmdb-movies2', 'tmdb-tv']:
                type_path = os.path.join(override_path, item_type_key)
                if not os.path.isdir(type_path):
                    continue

                for tmdb_id in os.listdir(type_path):
                    item_folder = os.path.join(type_path, tmdb_id)
                    if not os.path.isdir(item_folder):
                        continue

                    # Scan all JSON files in the folder (all.json, series.json, season-X.json, episode files)
                    for filename in os.listdir(item_folder):
                        if not filename.endswith('.json'):
                            continue

                        json_path = os.path.join(item_folder, filename)
                        try:
                            with open(json_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)

                            # Look for cast in different structures
                            cast_list = []
                            # Movie/Series: data['casts']['cast']
                            if 'casts' in data and isinstance(data['casts'], dict) and 'cast' in data['casts']:
                                cast_list.extend(data['casts']['cast'])
                            # Episode/Season: data['credits']['cast'] or data['credits']['guest_stars']
                            if 'credits' in data and isinstance(data['credits'], dict):
                                if 'cast' in data['credits']:
                                    cast_list.extend(data['credits']['cast'])
                                if 'guest_stars' in data['credits']:
                                    cast_list.extend(data['credits']['guest_stars'])

                            for actor in cast_list:
                                if not isinstance(actor, dict): continue
                                aid = actor.get('id')
                                name = actor.get('name')
                                oname = actor.get('original_name')
                                dept = actor.get('known_for_department', 'Acting')

                                if aid and name and oname:
                                    key = (int(aid), name, oname)
                                    if key not in seen:
                                        scanned_actors.append({
                                            "id": int(aid),
                                            "name": name,
                                            "original_name": oname,
                                            "known_for_department": dept
                                        })
                                        seen.add(key)
                        except Exception as e:
                            log_audit("编辑", "失败", f"解析 {json_path} 中的演员信息时出错: {e}", level="ERROR")
            return scanned_actors

        actors_to_import = await asyncio.to_thread(_scan_files)

        if not actors_to_import:
            return True, "操作完成，但在覆盖缓存中没有找到演员信息。"

        try:
            await self.actor_service.batch_import_actors(actors_to_import)
            imported_count = len(actors_to_import)
            return True, f"操作成功！共从覆盖缓存导入了 {imported_count} 个演员。"
        except Exception as e:
            return False, f"数据库操作失败: {e}"

    async def import_actors_from_override_cache_task(self):
        from ...websocket_manager import manager
        from concurrent.futures import ThreadPoolExecutor
        import threading

        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            log_audit("编辑", "失败", "演员导入失败：未配置覆盖缓存 (Override) 目录。", level="ERROR")
            await manager.broadcast_progress("import_actors", "error", 0, 0, "错误：未配置覆盖缓存目录。")
            return

        log_audit("编辑", "开始", f"🚀 开始从覆盖缓存导入演员... 路径: {override_path}")
        await manager.broadcast_progress("import_actors", "running", 0, 0, "正在多线程扫描覆盖缓存中的演员...")

        def _process_single_file(json_path):
            """单个文件处理函数，由线程池调用"""
            found = []
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 兼容性演职员提取
                raw_cast_list = []

                # 情况 A: 位于 casts 对象中 (常见于电影 all.json 和剧集 series.json)
                if 'casts' in data and isinstance(data['casts'], dict):
                    if 'cast' in data['casts'] and isinstance(data['casts']['cast'], list):
                        raw_cast_list.extend(data['casts']['cast'])

                # 情况 B: 位于 credits 对象中 (常见于季度和分集)
                if 'credits' in data and isinstance(data['credits'], dict):
                    if 'cast' in data['credits'] and isinstance(data['credits']['cast'], list):
                        raw_cast_list.extend(data['credits']['cast'])
                    if 'guest_stars' in data['credits'] and isinstance(data['credits']['guest_stars'], list):
                        raw_cast_list.extend(data['credits']['guest_stars'])

                # 情况 C: 位于顶层 (容错)
                if 'cast' in data and isinstance(data['cast'], list):
                    raw_cast_list.extend(data['cast'])
                if 'guest_stars' in data and isinstance(data['guest_stars'], list):
                    raw_cast_list.extend(data['guest_stars'])

                for actor in raw_cast_list:
                    if not isinstance(actor, dict): continue

                    # 关键字段提取：TMDB ID, 姓名, 原始姓名
                    aid = actor.get('id')
                    name = actor.get('name')
                    oname = actor.get('original_name')
                    dept = actor.get('known_for_department', 'Acting')

                    if aid and name and oname:
                        found.append({
                            "id": int(aid),
                            "name": str(name).strip(),
                            "original_name": str(oname).strip(),
                            "known_for_department": str(dept).strip()
                        })
            except:
                pass
            return found

        def _scan_files_parallel():
            # 1. 搜寻所有 JSON 文件
            all_files = []
            for root, _, files in os.walk(override_path):
                for file in files:
                    if file.endswith('.json'):
                        all_files.append(os.path.join(root, file))

            total_files = len(all_files)
            if total_files == 0:
                return []

            scanned_actors = []
            seen = set()

            # 2. 执行并行处理
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(_process_single_file, all_files))

            # 3. 汇总结果并去重
            for actors_in_file in results:
                for actor in actors_in_file:
                    # 复合 Key：ID + 姓名 + 原始姓名
                    key = (actor['id'], actor['name'], actor['original_name'])
                    if key not in seen:
                        scanned_actors.append(actor)
                        seen.add(key)

            log_audit("编辑", "完成", f"✅ 解析完成: 从 {total_files} 个文件中提取出 {len(scanned_actors)} 位独立演员。")
            return scanned_actors

        try:
            actors_to_import = await asyncio.to_thread(_scan_files_parallel)
        except Exception as e:
            log_audit("编辑", "失败", f"❌ 并行扫描失败: {e}", level="ERROR")
            await manager.broadcast_progress("import_actors", "error", 0, 0, f"并行扫描失败: {e}")
            return

        if not actors_to_import:
            log_audit("编辑", "处理", "ℹ️ 未在覆盖缓存中发现任何有效的演员信息。")
            await manager.broadcast_progress("import_actors", "completed", 0, 0, "未发现可导入的演员信息。")
            return

        total = len(actors_to_import)
        log_audit("编辑", "开始", f"💾 正在将 {total} 位演员导入数据库...")
        await manager.broadcast_progress("import_actors", "running", 0, total, f"扫描完成，准备导入 {total} 个演员...")

        try:
            chunk_size = 500
            for i in range(0, total, chunk_size):
                chunk = actors_to_import[i: i + chunk_size]
                await self.actor_service.batch_import_actors(chunk)
                current = min(i + chunk_size, total)
                await manager.broadcast_progress("import_actors", "running", current, total, f"正在写入数据库... ({current}/{total})")
                await asyncio.sleep(0.01)

            log_audit("编辑", "完成", f"🎊 演员导入成功！共计 {total} 位演员已存入 actors.db。")
            await manager.broadcast_progress("import_actors", "completed", total, total, f"成功导入 {total} 个演员。")
        except Exception as e:
            log_audit("编辑", "失败", f"❌ 数据库写入失败: {e}", level="ERROR")
            await manager.broadcast_progress("import_actors", "error", 0, 0, f"导入失败: {e}")

    async def apply_actor_standards_to_overrides_task(self):
        """将数据库中的演员标准应用到所有本地 Override JSON 文件"""
        from ...websocket_manager import manager
        from concurrent.futures import ThreadPoolExecutor
        import json

        override_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)
        if not override_path:
            await manager.broadcast_progress("update_actors_override", "error", 0, 0, "错误：未配置覆盖缓存目录。")
            return

        log_audit("编辑", "开始", "🎬 开始执行 '一键更新 Override' 任务...")
        await manager.broadcast_progress("update_actors_override", "running", 0, 0, "正在构建演员标准字典...")

        # 1. 构建映射字典
        # Map: ID -> {id, name, original_name}
        actor_map = {}
        all_db_actors = await self.actor_service.get_all_actors()
        for actor in all_db_actors:
            standard_info = {
                "id": actor['tmdb_id'],
                "name": actor['name'],
                "original_name": actor['original_name']
            }
            # 映射主 ID
            actor_map[int(actor['tmdb_id'])] = standard_info
            # 映射所有副 ID
            if actor.get('duplicate_tmdb_id'):
                import re
                dup_ids = re.findall(r'\d+', actor['duplicate_tmdb_id'])
                for d_id in dup_ids:
                    actor_map[int(d_id)] = standard_info

        log_audit("编辑", "完成", f"📚 字典构建完成，共包含 {len(actor_map)} 条 ID 映射规则。")
        # 2. 收集所有 JSON 文件
        json_files = []
        for item_type in ['tmdb-movies2', 'tmdb-tv']:
            type_dir = os.path.join(override_path, item_type)
            if not os.path.isdir(type_dir): continue
            for tmdb_id in os.listdir(type_dir):
                item_dir = os.path.join(type_dir, tmdb_id)
                if not os.path.isdir(item_dir): continue
                for fname in os.listdir(item_dir):
                    if fname.endswith('.json'):
                        json_files.append(os.path.join(item_dir, fname))

        total_files = len(json_files)
        log_audit("编辑", "完成", f"🔍 检索完成，共需检查 {total_files} 个 JSON 文件。")
        # 3. 定义单个文件处理逻辑
        def _process_file(file_path):
            changed = False
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 定义处理列表的辅助函数
                def _update_list(target_list):
                    nonlocal changed
                    if not target_list or not isinstance(target_list, list): return
                    for actor in target_list:
                        if not isinstance(actor, dict): continue
                        aid = actor.get('id')
                        if aid and int(aid) in actor_map:
                            std = actor_map[int(aid)]
                            # 检查是否需要更新
                            if (actor.get('id') != std['id'] or
                                actor.get('name') != std['name'] or
                                actor.get('original_name') != std['original_name']):

                                actor['id'] = std['id']
                                actor['name'] = std['name']
                                actor['original_name'] = std['original_name']
                                changed = True

                # 遍历所有可能的演员位置
                if 'casts' in data and isinstance(data['casts'], dict):
                    _update_list(data['casts'].get('cast'))
                if 'credits' in data and isinstance(data['credits'], dict):
                    _update_list(data['credits'].get('cast'))
                    _update_list(data['credits'].get('guest_stars'))
                if 'cast' in data: _update_list(data['cast'])
                if 'guest_stars' in data: _update_list(data['guest_stars'])

                if changed:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    return True
            except:
                pass
            return False

        # 4. 多线程执行更新
        updated_count = 0
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(_process_file, json_files))
            updated_count = sum(1 for r in results if r)

        log_audit("编辑", "完成", f"✅ 任务完成！共检查 {total_files} 个文件，更新了其中 {updated_count} 个包含演员信息的文件。")
        await manager.broadcast_progress("update_actors_override", "completed", total_files, total_files, f"更新完成！已修正 {updated_count} 个文件。")
