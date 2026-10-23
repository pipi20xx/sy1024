from fastapi import APIRouter, BackgroundTasks
from typing import List, Dict, Optional, Any
import asyncio
from app.logger import logger, log_audit
from .. import globals
from ..schemas import WorkflowRequest
from ..websocket_manager import manager

# --- [修复] 工作流逻辑 ---
async def run_workflow_in_background(item_type: str, tasks: List[Dict], interval_seconds: int, 
                               item_ids: Optional[List[str]] = None, filters: Optional[Dict[str, Any]] = None):
    service = globals.service
    tag_service = globals.tag_service

    try:
        final_item_ids = []
        # 1. 优先检查 item_ids (针对选定项目)
        if item_ids:
            log_audit("工作流", "启动", "基于指定项目列表", level="START")
            final_item_ids = item_ids
            
        # 2. [核心修复] 使用 'is not None' 判断，允许空字典 {} (针对所有项目/筛选结果)
        elif filters is not None:
            log_audit("工作流", "启动", f"基于筛选条件执行", level="START")
            year_val = filters.get("year")
            month_val = filters.get("month")
            
            try:
                year_int = int(year_val) if year_val is not None else None
            except (ValueError, TypeError):
                year_int = None

            try:
                month_int = int(month_val) if month_val is not None else None
            except (ValueError, TypeError):
                month_int = None

            final_item_ids = await service.scanner_service.get_all_item_ids_by_filter(
                item_type=item_type,
                search_term=filters.get("search_term"),
                source=filters.get("source"),
                poster_status=filters.get("poster_status"),
                genres=list(filters.get("genres")) if filters.get("genres") else None,
                year=year_int,
                month=month_int
            )
        else:
            log_audit("工作流", "启动失败", "未提供项目ID或筛选条件", level="WARN")
            return

        total_items = len(final_item_ids)
        if total_items == 0:
            log_audit("工作流", "无匹配项目", "工作流结束")
            return
            
        log_audit("工作流", "开始执行", f"共 {total_items} 个项目", level="START")
        await manager.broadcast_progress(
            task_type="batch_workflow",
            status="running",
            current=0,
            total=total_items,
            message=f"工作流启动，共 {total_items} 个项目"
        )

        for i, item_id in enumerate(final_item_ids):
            # Update progress
            await manager.broadcast_progress(
                task_type="batch_workflow",
                status="running",
                current=i + 1,
                total=total_items,
                message=f"正在处理项目 {i+1}/{total_items}: {item_id}"
            )
            
            log_audit("工作流", "处理", f"处理项目 ({i+1}/{total_items}): {item_type}/{item_id}")
            try:
                for task in tasks:
                    task_type = task.get("type")
                    log_audit("工作流", "处理", f"  -> 执行任务: {task_type}")
                    success = True
                    message = ""

                    if task_type == "download_web_images":
                        params = task.get("params", {})
                        sources = params.get("sources", ["tmdb", "fanart"])
                        image_types = params.get("image_types", ["poster", "fanart", "logo"])
                        behavior = params.get("behavior", "overwrite")
                        lang_priority = params.get("lang_priority", "zh")
                        source_priority = params.get("source_priority", "")
                        
                        # 1. Fetch images
                        fetch_success, result = service.image_service.get_web_images(item_type, item_id, image_types, sources)
                        
                        if not fetch_success:
                            if "均未找到" in str(result):
                                success, message = True, f"未找到图片: {result}"
                            else:
                                success, message = False, f"获取网络图片失败: {result}"
                        elif isinstance(result, list) and len(result) > 0:
                            # 2. Sort images by priority
                            def get_image_score(img):
                                score = 0
                                # Language Score (High Priority)
                                lang = str(img.get("lang", "")).lower()
                                target_lang = lang_priority.lower()
                                if lang == target_lang or (target_lang and lang.startswith(target_lang)):
                                    score += 20
                                elif not lang or lang == "n/a" or lang == "null" or lang == "none":
                                    score += 10
                                
                                # Source Score (Medium Priority)
                                source = str(img.get("source", "")).lower() # e.g. "TMDb", "Fanart.tv"
                                target_source = source_priority.lower()
                                if target_source and target_source in source:
                                    score += 5
                                    
                                return score
                            
                            # Sort descending by score
                            result.sort(key=get_image_score, reverse=True)

                            # 3. Select best (first) image for each type
                            images_to_save = []
                            seen_types = set()
                            for img in result:
                                itype = img.get("type")
                                if itype not in seen_types:
                                    images_to_save.append(img)
                                    seen_types.add(itype)
                            
                            if images_to_save:
                                success, message = await service.image_service.save_web_images(item_type, item_id, images_to_save, behavior=behavior)
                            else:
                                success, message = True, "未筛选到有效图片"
                        else:
                             success, message = True, "未找到符合条件的网络图片"

                    elif task_type == "emby_download_images":
                        success, message = await service.image_service.download_images_from_emby(item_type, item_id, broadcast=False)
                    elif task_type == "copy_to_override":
                        success, message = await service.editor_service.copy_item_to_override(item_type, item_id)
                    elif task_type == "emby_update_metadata":
                        if not service.emby_client:
                            success, message = False, "Emby客户端未配置。"
                        else:
                            titles = await asyncio.to_thread(service.emby_integration_service._get_titles_from_local_cache, item_type, item_id)
                            found_items, error = await service.emby_client.find_items_by_tmdb_id(item_id, item_type, titles=titles)
                            if error:
                                success, message = False, f"在Emby中查找项目失败: {error}"
                            elif not found_items:
                                success, message = False, f"在Emby中找不到TMDB ID为 {item_id} 的项目。"
                            else:
                                emby_item = found_items[0]
                                emby_item_id = emby_item.get("Id")
                                original_emby_item_type = emby_item.get("Type")
                                if not emby_item_id or not original_emby_item_type:
                                    success, message = False, "从Emby获取的项目信息无效。"
                                else:
                                    params = task.get("params", {})
                                    success, message = await service.editor_service.update_metadata_from_emby(
                                        item_type=item_type,
                                        emby_item_id=emby_item_id,
                                        folder_tmdb_id=item_id,
                                        original_emby_item_type=original_emby_item_type,
                                        fields_to_update=params.get("fields_to_update", []),
                                        update_children=params.get("update_children", False)
                                    )
                    elif task_type == "delete_override":
                        success, message = await service.editor_service.delete_override_folder(item_type, item_id)
                    elif task_type == "emby_refresh":
                        success, message = await service.emby_integration_service.refresh_item_in_emby(item_type, item_id)
                    elif task_type == "delete_all_images":
                        success, message = await service.editor_service.delete_item_images(item_type, item_id)
                    elif task_type == "generate_item_tags":
                        params = task.get("params", {})
                        success, message = await tag_service.generate_and_save_item_tag(
                            item_type=item_type,
                            item_id=item_id,
                            mode=params.get("mode", "merge")
                        )
                    elif task_type == "delete_override_files":
                        params = task.get("params", {})
                        targets = params.get("targets", [])
                        results = []
                        for target in targets:
                            if target == "metadata":
                                s, m = await service.editor_service.delete_item_metadata(item_type, item_id, mode="all")
                                results.append((s, m))
                            elif target == "tags":
                                s, m = await tag_service.delete_item_tags(item_type, item_id)
                                results.append((s, m))
                            elif target == "external_ids":
                                s, m = await service.editor_service.delete_external_ids_file(item_type, item_id)
                                results.append((s, m))
                            elif target == "episode_order":
                                s, m = await service.editor_service.delete_episode_order_file(item_id)
                                results.append((s, m))
                            elif target == "episode_group":
                                s, m = await service.editor_service.delete_episode_group_file(item_id)
                                results.append((s, m))
                        # Aggregate results
                        failed = [r for r in results if not r[0]]
                        if failed:
                            success, message = False, f"部分删除失败: {failed[0][1]}"
                        else:
                            success, message = True, f"成功删除 {len(results)} 个文件"
                    elif task_type == "lock_name":
                        params = task.get("params", {})
                        mode = params.get("mode")
                        success, message = await service.editor_service.lock_item_name(item_type, item_id, mode)
                    elif task_type == "tmdb_update_metadata":
                        params = task.get("params", {})
                        # Map editor item_type to tmdb item_type
                        tmdb_type = "movie" if item_type == "tmdb-movies2" else "tv"
                        
                        success, message = await service.tmdb_metadata_service.update_metadata(
                            item_type=tmdb_type,
                            tmdb_id=item_id,
                            lang=params.get("lang", "zh-CN"),
                            fields=params.get("fields_to_update", None),
                            overwrite=params.get("overwrite", False),
                            trigger_refresh=params.get("trigger_emby_refresh", False),
                            update_season_episodes=params.get("update_season_episodes", False)
                        )
                    elif task_type == "bangumi_update_metadata":
                        params = task.get("params", {})
                        success, message = await service.editor_service.update_metadata_from_bangumi(
                            item_type=item_type,
                            item_id=item_id,
                            bangumi_id=None, # Auto resolve
                            fields=params.get("fields_to_update", None),
                            force_refresh=params.get("force_refresh", False),
                            use_whitelist=params.get("use_whitelist", False),
                            mode=params.get("mode", "merge"),
                            auto_match=params.get("auto_match", False)
                        )
                    elif task_type == "ai_translate":
                        params = task.get("params", {})
                        success, message = await service.editor_service.ai_translate_item_metadata(
                            item_type=item_type,
                            item_id=item_id,
                            config=params
                        )
                    else:
                        success = False
                        message = f"未知的任务类型: {task_type}"

                    if not success:
                        log_audit("工作流", "任务失败", f"{task_type} @ {item_id}: {message}", level="ERROR")
                        break 
                    else:
                        log_audit("工作流", "完成", f"任务 {task_type} 在项目 {item_id} 上成功")
                if i < total_items - 1:
                    await asyncio.sleep(interval_seconds)

            except Exception as e:
                log_audit("工作流", "失败", f"处理项目 {item_id} 时发生意外错误: {e}", level="ERROR")
        log_audit("工作流", "执行完毕", f"共处理 {total_items} 个项目", level="DONE")
        await manager.broadcast_progress(
            task_type="batch_workflow",
            status="idle",
            current=total_items,
            total=total_items,
            message="工作流执行完毕"
        )
    except Exception as e:
        log_audit("工作流", "致命错误", "任务提前终止", level="ERROR")
        await manager.broadcast_progress(
            task_type="batch_workflow",
            status="idle",
            current=0,
            total=0,
            message=f"工作流发生错误: {str(e)}"
        )

router = APIRouter(tags=["工作流管理"])

@router.post("/api/workflow/run", summary="执行后台工作流")
async def run_workflow(request: WorkflowRequest, background_tasks: BackgroundTasks):
    """
    提交一个包含多个任务的后台工作流，按顺序在指定的媒体项目上执行。
    """
    # 将 Pydantic 模型转换为字典列表，以便传递给后台任务
    tasks_as_dicts = [task.dict() for task in request.tasks]
    
    background_tasks.add_task(
        run_workflow_in_background,
        item_type=request.item_type,
        tasks=tasks_as_dicts,
        interval_seconds=request.interval_seconds,
        item_ids=request.item_ids,
        filters=request.filters
    )
    
    return {"message": "工作流已成功提交到后台执行。"}