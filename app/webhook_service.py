# app/webhook_service.py

import re
import os
import shutil # Added import
from typing import Dict, Any, Optional

# 确保可以正确地进行类型提示和访问其他服务
from .services import SystemService 
from .common import sanitize_filename
from .logger import log_audit

class WebhookService:
    def __init__(self, config: Dict[str, Any], system_service: SystemService):
        self.config = config
        self.system_service = system_service
        log_audit("Webhook", "初始化", "WebhookService 初始化成功。")
    # [核心修正] 替换为支持合集自动化的新版完整函数
    async def handle_emby_webhook(self, payload: Dict[str, Any]):
        """
        处理 Webhook 事件的路由器。
        """
        log_audit("Webhook", "处理", f"收到 Webhook 原始数据: {payload}", level="DEBUG")
        event_type = payload.get("Event")
        item_data = payload.get("Item")
        description = payload.get("Description", "")

        if not event_type or not item_data:
            log_audit("Webhook", "跳过", "收到的 Webhook 缺少 Event 或 Item 字段，已忽略。", level="DEBUG")
            return

        item_type_emby = item_data.get("Type")
        item_name = item_data.get("Name", "未知项目")
        log_prefix = f"Webhook [{event_type}] for '{item_name}':"

        # --- 事件路由 ---

        # 1. 处理自定义脚本事件 (来自油猴等)
        if event_type in ["download_to_override", "supplement_to_override", "delete_override"]:
            if not self.config.get("webhook_action_script_enabled", False):
                log_audit("Webhook", "跳过", f"{log_prefix} 自定义脚本自动化开关已关闭，操作被跳过。")
                return

            tmdb_id = item_data.get("ProviderIds", {}).get("Tmdb")
            if item_type_emby not in ["Movie", "Series"] or not tmdb_id:
                log_audit("Webhook", "跳过", f"{log_prefix} 收到的项目缺少必要信息 (类型或TMDB ID)，已忽略。", level="WARN")
                return
            
            item_type_internal = "tmdb-movies2" if item_type_emby == "Movie" else "tmdb-tv"
            
            success, message = False, "未知的事件类型"
            if event_type == "download_to_override":
                success, message = await self.system_service.image_service.download_images_from_emby(item_type_internal, tmdb_id)
            elif event_type == "supplement_to_override":
                success, message = await self.system_service.editor_service.copy_item_to_override(item_type_internal, tmdb_id)
            elif event_type == "delete_override":
                success, message = await self.system_service.editor_service.delete_override_folder(item_type_internal, tmdb_id)

            if success: log_audit("Webhook", "脚本", f"{log_prefix} 操作成功: {message}", level="SUCCESS")
            else: log_audit("Webhook", "脚本", f"{log_prefix} 操作失败: {message}", level="ERROR")
        
        # 2. 处理 Emby 原生图片更新事件 (非合集)
        elif event_type == "image.update" and item_type_emby != "BoxSet":
            if not self.config.get("webhook_action_image_update_enabled", False):
                return
            await self._handle_image_update(item_data, description)

        # 3. [核心新增] 统一处理所有与“自定义合集”相关的自动化事件
        elif item_type_emby == "BoxSet" and event_type in ["collection.items.added", "collection.items.removed", "image.update"]:
            if not self.config.get("webhook_action_collection_sync_enabled", False):
                log_audit("Webhook", "跳过", f"{log_prefix} 自定义合集自动同步开关已关闭，操作被跳过。")
                return

            log_audit("Webhook", "开始", f"{log_prefix} 检测到合集变更，开始执行自动化同步...")
            # 根据具体事件调用不同方法
            if event_type in ["collection.items.added", "collection.items.removed"]:
                # 当成员变动时，从Emby重新拉取合集数据并覆盖本地JSON
                collection_service = self.system_service.collection_service
                success, message = await collection_service.sync_single_collection_from_emby_by_name(item_name)
                if success:
                    log_audit("Webhook", "完成", f"{log_prefix} 成员同步成功: {message}")
                else:
                    # [核心修正] 增加对合集已被删除情况的特殊处理
                    if "在Emby中未找到名为" in message:
                        log_audit("Webhook", "清理", f"{log_prefix} Emby端合集已不存在，将尝试删除本地对应的自定义合集...", level="WARN")
                        # 构造本地文件名
                        local_filename = f"{sanitize_filename(item_name)}.json"
                        delete_success, delete_message = collection_service.delete_collection(local_filename)
                        if delete_success:
                            log_audit("Webhook", "处理", f"{log_prefix} 本地自定义合集 '{local_filename}' 已被成功自动删除。")
                        else:
                            # [核心修正] 如果文件本就不存在，这不是一个错误，而是一个状态确认
                            if "不存在" in delete_message:
                                log_audit("Webhook", "处理", f"{log_prefix} 确认本地自定义合集 '{local_filename}' 已不存在，无需操作。")
                            else:
                                log_audit("Webhook", "清理", f"{log_prefix} 尝试删除本地合集 '{local_filename}' 失败: {delete_message}", level="ERROR")
                    else:
                        log_audit("Webhook", "失败", f"{log_prefix} 成员同步失败: {message}", level="ERROR")
            elif event_type == "image.update":
                # 当图片变动时，仅下载并覆盖对应的图片文件
                self._handle_collection_image_update(item_data, description)
        
        # 4. [核心新增] 处理 Emby 原生元数据更新事件
        elif event_type == "metadata.update":
            if not self.config.get("webhook_action_metadata_update_enabled", False):
                log_audit("Webhook", "跳过", f"{log_prefix} 元数据更新自动化开关已关闭，操作被跳过。")
                return
            
            emby_item_id = item_data.get("Id")
            if not emby_item_id:
                log_audit("Webhook", "更新", f"{log_prefix} 缺少 Emby Item ID，无法执行元数据更新。", level="WARN")
                return
            
            # 将 Emby 的 Type 映射到内部使用的 item_type
            internal_item_type = None
            tmdb_id_for_update = None

            if item_type_emby == "Movie":
                internal_item_type = "tmdb-movies2"
                tmdb_id_for_update = item_data.get("ProviderIds", {}).get("Tmdb")
            elif item_type_emby == "Series":
                internal_item_type = "tmdb-tv"
                tmdb_id_for_update = item_data.get("ProviderIds", {}).get("Tmdb")
            elif item_type_emby in ["Season", "Episode"]:
                internal_item_type = "tmdb-tv"
                series_id = item_data.get("SeriesId")
                if series_id and self.system_service.emby_client:
                    series_details, err = await self.system_service.emby_client.get_item_details(series_id, fields="ProviderIds") # 移除 await
                    if series_details and not err:
                        tmdb_id_for_update = series_details.get("ProviderIds", {}).get("Tmdb")
            
            if not internal_item_type or not tmdb_id_for_update:
                log_audit("Webhook", "处理", f"{log_prefix} 无法确定有效的内部项目类型或 TMDB ID (Emby Item Type: '{item_type_emby}')，已忽略。", level="WARN")
                return
            
            fields_to_update = []

            if item_type_emby == "Movie":
                fields_to_update.extend(["title", "original_title", "overview", "genres", "air_date", "vote_average", "tags"])
            elif item_type_emby == "Series":
                fields_to_update.extend(["title", "original_title", "overview", "genres", "air_date", "vote_average", "end_date", "tags"])
            elif item_type_emby == "Season":
                fields_to_update.extend(["season_name", "season_overview", "season_air_date"])
            elif item_type_emby == "Episode":
                fields_to_update.extend(["episode_name", "episode_overview", "episode_air_date"])
            
            update_children = (item_type_emby == "Series") # 只有剧集类型才递归更新子项

            log_audit("Webhook", "开始", f"{log_prefix} 检测到元数据更新，开始执行自动化同步 (Emby Item ID: {emby_item_id}, TMDB ID: {tmdb_id_for_update})...")
            success, message = await self.system_service.update_metadata_from_emby(
                item_type=internal_item_type,
                emby_item_id=emby_item_id, # 传递 Emby Item ID
                folder_tmdb_id=tmdb_id_for_update, # 传递 TMDB ID 用于文件夹定位
                original_emby_item_type=item_type_emby, # 传递原始 Emby Item Type
                fields_to_update=fields_to_update,
                update_children=update_children
            )
            if success:
                log_audit("Webhook", "完成", f"{log_prefix} 元数据同步成功: {message}")
            else:
                log_audit("Webhook", "失败", f"{log_prefix} 元数据同步失败: {message}", level="ERROR")
        # 5. [核心新增] 处理高级截图 (advanced_screenshot) 自动化事件
        elif event_type == "advanced_screenshot":
            log_audit("Webhook", "开始", f"{log_prefix} 收到高级截图生成请求，开始处理...")
            item_id = item_data.get("Id")
            if not item_id:
                log_audit("Webhook", "处理", f"{log_prefix} 缺少 Item Id，无法生成截图。", level="WARN")
                return

            try:
                # 1. 获取配置
                from .services.preview_generator import preview_service
                config = preview_service.get_config()
                
                count = config.get("count", 12)
                start_pct = config.get("start_pct", 10)
                end_pct = config.get("end_pct", 90)
                path_mappings = config.get("path_mappings", [])

                log_audit("Webhook", "处理", f"{log_prefix} 使用配置: 数量={count}, 范围={start_pct}%-{end_pct}%")
                # 2. 生成预览图
                success, msg, images, session_id = await preview_service.generate_previews(
                    item_id=item_id,
                    count=count,
                    start_pct=start_pct,
                    end_pct=end_pct,
                    path_mappings=path_mappings
                )

                if not success or not images:
                    log_audit("Webhook", "失败", f"{log_prefix} 生成截图失败: {msg}", level="ERROR")
                    return

                log_audit("Webhook", "完成", f"{log_prefix} 成功生成 {len(images)} 张预览图。")
                # 3. 自动选择一张 (这里选择中间那张，或者随机，或者第二张)
                # 策略：如果有多张，选第二张 (index 1)，因为通常片头已过。如果只有一张，选第一张。
                import random
                selected_image_relative_path = ""
                if len(images) > 1:
                    # 尝试选择前部靠后的位置，比如 1/3 处，或者简单的随机
                    # 之前沟通提到“自动选择”，这里默认随机选择一张，或者您可以指定策略
                    # 简单策略：随机选择一张，增加变化性
                    selected_image_relative_path = random.choice(images)
                else:
                    selected_image_relative_path = images[0]
                
                log_audit("Webhook", "处理", f"{log_prefix} 自动选择了图片: {selected_image_relative_path}")
                # 4. 上传封面
                up_success, up_msg = await preview_service.upload_selected_image(item_id, selected_image_relative_path)
                
                if up_success:
                    log_audit("Webhook", "完成", f"{log_prefix} 自动设置封面成功！")
                else:
                    log_audit("Webhook", "失败", f"{log_prefix} 设置封面失败: {up_msg}", level="ERROR")
                # 5. 清理临时文件 (可选，如果不希望临时文件无限增长)
                # 目前 upload_selected_image 并不删除文件。
                # 我们可以删除 session 目录
                try:
                    session_dir = os.path.dirname(os.path.join("app/static", selected_image_relative_path.strip("/").replace("static/", "")))
                    # 注意：路径拼接可能需要根据 relative_path 的实际格式调整
                    # images 返回的是 /static/temp_previews/{session_id}/preview_x.jpg
                    # 真实路径是 app/static/temp_previews/{session_id}
                    if "temp_previews" in session_dir:
                         shutil.rmtree(session_dir)
                         log_audit("Webhook", "清理", f"{log_prefix} 已清理临时会话目录: {session_dir}")
                except Exception as e:
                    log_audit("Webhook", "失败", f"{log_prefix} 清理临时文件失败: {e}", level="WARN")
            except Exception as e:
                log_audit("Webhook", "处理", f"{log_prefix} 处理高级截图自动化时发生异常: {e}", level="ERROR")

        else:
            log_audit("Webhook", "处理", f"收到非目标 Emby 事件 '{event_type}' (类型: {item_type_emby})，已忽略。", level="DEBUG")
    async def _handle_collection_image_update(self, item_data: Dict[str, Any], description: str):
        """处理自定义合集的图片更新事件。"""
        collection_name = item_data.get("Name")
        collection_id = item_data.get("Id")
        
        match = re.search(r"Image Type:\s*(\w+)", description)
        if not match:
            log_audit("Webhook", "处理", f"[image.update] 无法从合集 '{collection_name}' 的更新描述中解析出图片类型: '{description}'", level="WARN")
            return
        
        emby_image_type = match.group(1)
        log_prefix = f"Webhook [image.update] for collection '{collection_name}':"
        
        collection_service = self.system_service.collection_service
        emby_client = self.system_service.emby_client
        
        if not collection_service.collections_path or not emby_client:
            log_audit("Webhook", "更新", f"{log_prefix} 无法执行图片同步，因为自定义合集路径或Emby客户端未配置。", level="ERROR")
            return
            
        image_type_map = {
            "Primary": "_poster.jpg",
            "Backdrop": "_fanart.jpg",
            "Logo": "_logo.png"
        }
        filename_suffix = image_type_map.get(emby_image_type)
        if not filename_suffix:
            log_audit("Webhook", "处理", f"{log_prefix} 图片类型 '{emby_image_type}' 不在我们的自动化处理范围内，已忽略。")
            return

        base_filename_no_ext = sanitize_filename(collection_name)
        save_path = os.path.join(collection_service.collections_path, f"{base_filename_no_ext}{filename_suffix}")

        log_audit("Webhook", "开始", f"{log_prefix} 准备将新的 '{emby_image_type}' 图片下载到 '{save_path}'...")
        success = await emby_client.download_image_for_item(
            emby_item_id=collection_id,
            image_type=emby_image_type,
            save_path=save_path
        )
        
        if success:
            log_audit("Webhook", "完成", f"{log_prefix} 图片同步成功！")
        else:
            log_audit("Webhook", "失败", f"{log_prefix} 图片同步失败。请检查日志获取更多信息。", level="ERROR")
    async def _handle_image_update(self, item_data: Dict[str, Any], description: str):
        """处理非合集项目的图片更新事件 (原有逻辑)"""
        match = re.search(r"Image Type:\s*(\w+)", description)
        if not match:
            log_audit("Webhook", "处理", f"[image.update] 无法从描述中解析出图片类型: '{description}'", level="WARN")
            return
        
        emby_image_type = match.group(1)
        item_name = item_data.get("Name", "未知项目")
        item_type_emby = item_data.get("Type")
        
        tmdb_id = None
        item_type_internal = None

        if item_type_emby == "Movie":
            tmdb_id = item_data.get("ProviderIds", {}).get("Tmdb")
            item_type_internal = "tmdb-movies2"
        elif item_type_emby == "Series":
            tmdb_id = item_data.get("ProviderIds", {}).get("Tmdb")
            item_type_internal = "tmdb-tv"
        elif item_type_emby in ["Season", "Episode"]:
            series_id = item_data.get("SeriesId")
            if series_id and self.system_service.emby_client:
                series_details, err = await self.system_service.emby_client.get_item_details(series_id, fields="ProviderIds")
                if series_details and not err:
                    tmdb_id = series_details.get("ProviderIds", {}).get("Tmdb")
                    item_type_internal = "tmdb-tv"

        if not tmdb_id or not item_type_internal:
            log_audit("Webhook", "处理", f"[image.update] 无法为项目 '{item_name}' (类型: {item_type_emby}) 确定有效的TMDB ID或内部类型，已忽略。", level="WARN")
            return

        log_audit("Webhook", "处理", f"Webhook [image.update]: Emby项目 '{item_name}' (根TMDB ID: {tmdb_id}) 的 '{emby_image_type}' 图片已更新。")
        override_path = self.system_service._get_cache_path_for_source("override")
        if not override_path:
            log_audit("Webhook", "下载", "  -> 无法执行下载，因为 Override 缓存路径未配置。", level="ERROR")
            return

        target_base_dir = os.path.join(override_path, item_type_internal, tmdb_id)
        
        log_audit("Webhook", "开始", f"  -> 开始为 {tmdb_id} 精确下载 '{emby_image_type}' 类型的图片...")
        success, message = await self.system_service.emby_client.download_single_image_for_item(
            item_details=item_data, 
            emby_image_type=emby_image_type, 
            target_base_dir=target_base_dir
        )

        if success:
            log_audit("Webhook", "处理", f"  -> {message}")
            self.system_service._refresh_item_in_db(item_type_internal, tmdb_id)
        else:
            log_audit("Webhook", "失败", f"  -> 精确下载失败: {message}", level="ERROR")
    # --- 保留旧的、当前已禁用的事件处理器作为参考 ---
    def _handle_item_add(self, item_data: Dict[str, Any]):
        """处理新媒体入库事件 (当前已禁用)"""
        if not self.config.get("webhook_action_item_add_enabled", False):
            return

        item_name = item_data.get("Name", "未知项目")
        tmdb_id = item_data.get("ProviderIds", {}).get("Tmdb")
        log_audit("Webhook", "处理", f"Webhook [item.add]: 收到新项目 '{item_name}' (TMDB ID: {tmdb_id}) 的通知，但当前未配置任何自动化操作，已忽略。")