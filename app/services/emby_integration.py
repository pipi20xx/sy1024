import os
import json
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union
from ..emby_client import EmbyClient
from ..emby_metadata_updater import EmbyMetadataUpdater
from .configuration import ConfigurationService
from ..common import SOURCE_PRIMARY, SOURCE_OVERRIDE, MAIN_JSON_FILENAMES
from ..logger import log_audit


class EmbyIntegrationService:
    def __init__(self, configuration_service: ConfigurationService):
        self.configuration_service = configuration_service
        self._emby_client: Optional[EmbyClient] = None
        self._initialize_client()

    def _initialize_client(self):
        emby_url = self.configuration_service.get("emby_server_url")
        emby_api_key = self.configuration_service.get("emby_api_key")
        if emby_url and emby_api_key:
            try:
                emby_user_id = self.configuration_service.get("emby_user_id", "")
                self._emby_client = EmbyClient(emby_url, emby_api_key, emby_user_id)
            except Exception as e:
                log_audit("Emby", "初始化", f"初始化Emby客户端失败: {e}", level="ERROR")
                self._emby_client = None
        else:
            self._emby_client = None

    @property
    def emby_client(self) -> Optional[EmbyClient]:
        # Always check config in case it changed (though ideally we use an event system)
        # For now, we rely on the caller to trigger re-init or we check lightly.
        # But wait, ConfigurationService handles updates.
        # If config changed, SystemService currently re-inits EmbyClient in ConfigMixin.
        # We should provide a method to reload.
        return self._emby_client

    def reload_client(self):
        self._initialize_client()

    def _get_titles_from_local_cache(self, item_type: str, tmdb_id: str) -> List[str]:
        """
        从本地 override / primary 缓存的 JSON 文件中读取标题列表。
        优先读取 override，其次 primary。
        返回去重后的标题列表（包含本地化标题和原始标题）。
        """
        main_json_file = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_file:
            return []

        titles = []
        for source in [SOURCE_OVERRIDE, SOURCE_PRIMARY]:
            cache_path = self.configuration_service.get_cache_path_for_source(source)
            if not cache_path:
                continue
            json_path = os.path.join(cache_path, item_type, tmdb_id, main_json_file)
            if not os.path.isfile(json_path):
                continue
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                if not isinstance(metadata, dict):
                    continue
                # 电影用 title, 剧集用 name
                name = metadata.get('name') or metadata.get('title')
                original_name = metadata.get('original_name') or metadata.get('original_title')
                if name:
                    titles.append(name)
                if original_name and original_name != name:
                    titles.append(original_name)
            except Exception as e:
                log_audit("Emby", "失败", f"读取本地 JSON 标题失败 {json_path}: {e}", level="WARN")
            # 找到 override 就不再读 primary
            if titles:
                break

        # 去重并保持顺序
        seen = set()
        result = []
        for t in titles:
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        if result:
            log_audit("Emby", "处理", f"从本地缓存读取到 TMDB ID {tmdb_id} 的标题: {result}")
        return result

    async def refresh_item_in_emby(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        client = self.emby_client
        if not client: return False, "Emby 客户端未配置。"

        titles = await asyncio.to_thread(self._get_titles_from_local_cache, item_type, item_id)
        found_items, error = await client.find_items_by_tmdb_id(item_id, item_type, titles=titles)
        if error: return False, error
        if not found_items: return False, f"在Emby中找不到TMDB ID为 {item_id} 的项目。"

        success_count, fail_count, messages = 0, 0, []
        for item in found_items:
            emby_item_id, item_name = item.get("Id"), item.get("Name", "未知项目")
            if not emby_item_id: continue
            success, msg = await client.trigger_refresh(emby_item_id)
            if success:
                success_count += 1
                messages.append(f"成功为 '{item_name}' (ID: {emby_item_id}) 发送刷新请求。")
            else:
                fail_count += 1
                messages.append(f"为 '{item_name}' (ID: {emby_item_id}) 发送刷新请求失败: {msg}")
        
        final_message = "\n".join(messages)
        if fail_count > 0: return False, f"刷新操作完成，但有失败项。\n\n{final_message}"
        return True, f"成功刷新所有 {success_count} 个匹配项。\n\n{final_message}"

    async def specify_scrape_in_emby(self, emby_item_id: str, new_tmdb_id: str) -> Tuple[bool, str]:
        client = self.emby_client
        if not client: return False, "Emby 客户端未配置。"
        
        item_details, err = await client.get_item_details(emby_item_id, fields="Type,Name")
        if err or not item_details:
            return False, f"无法获取 Emby Item (ID: {emby_item_id}) 的详情: {err}"
        
        item_type = item_details.get("Type")
        if item_type not in ["Movie", "Series"]:
            return False, f"不支持此操作，仅支持电影和剧集。"

        success, error = await client.update_provider_ids(emby_item_id, new_tmdb_id)
        if not success:
            return False, f"更新 ProviderIds 失败: {error}"
            
        success, message = await client.trigger_refresh(emby_item_id)
        if not success:
            return False, f"ProviderIds 已更新, 但刷新失败: {message}"
            
        return True, f"已成功指定新的 TMDB ID 并触发刷新。"

    async def batch_check_in_library(self, item_type: str, tmdb_ids: List[str]) -> Dict[str, bool]:
        """
        批量检查多个 TMDB ID 是否已入库到 Emby。
        委托给 EmbyClient.batch_check_items_exist，复用全库 3 分钟缓存。
        如果 Emby 未配置，返回全 False。
        """
        client = self.emby_client
        if not client:
            return {str(tid): False for tid in tmdb_ids}
        return await client.batch_check_items_exist(tmdb_ids, item_type)

    async def get_emby_web_url_info(self, item_type: str, item_id: str) -> Tuple[bool, Union[str, dict]]:
        client = self.emby_client
        if not client: return False, "Emby 客户端未配置。"

        titles = await asyncio.to_thread(self._get_titles_from_local_cache, item_type, item_id)
        found_items, error = await client.find_items_by_tmdb_id(item_id, item_type, titles=titles)
        if error: return False, error
        if not found_items: return False, f"在Emby中找不到TMDB ID为 {item_id} 的项目。"
        
        emby_item = found_items[0]
        emby_item_id = emby_item.get("Id")
            
        playback_info, err = await client.get_item_playback_info(emby_item_id)
        if err: return False, err
        
        server_url = client.server_url
        web_path = f"/web/index.html#!/item?id={playback_info['EmbyItemId']}&serverId={playback_info['ServerId']}"
        full_url = f"{server_url.rstrip('/')}{web_path}"

        return True, {"url": full_url, "name": playback_info.get("Name")}

    async def download_images_core(self, item_type: str, item_id: str, target_base_dir: str, broadcast: bool = True) -> Tuple[bool, str]:
        """
        Core logic for downloading images. Does not handle local DB updates.
        """
        client = self.emby_client
        if not client: return False, "Emby 客户端未配置。"

        os.makedirs(target_base_dir, exist_ok=True)
        titles = await asyncio.to_thread(self._get_titles_from_local_cache, item_type, item_id)
        return await client.download_all_images_for_tmdb_id(item_type, item_id, target_base_dir, broadcast=broadcast, titles=titles)

    async def run_metadata_updater_core(self, 
                                        item_type: str, 
                                        emby_item_id: str, 
                                        folder_tmdb_id: str, 
                                        original_emby_item_type: str, 
                                        fields_to_update: List[str], 
                                        update_children: bool,
                                        local_item_path: str) -> Tuple[bool, str]:
        """
        Core logic for running the metadata updater.
        """
        if not self.emby_client: return False, "Emby客户端未配置。"
        
        emby_server_url = self.configuration_service.get("emby_server_url")
        emby_api_key = self.configuration_service.get("emby_api_key")
        emby_user_id = self.configuration_service.get("emby_user_id", "")
        
        if not emby_user_id and "tags" in fields_to_update:
            return False, "配置中未设置 Emby User ID，无法执行标签同步。"

        override_cache_path = self.configuration_service.get("override_cache_path")
        
        def _run_updater_sync():
            updater = EmbyMetadataUpdater(
                server_url=emby_server_url,
                api_key=emby_api_key,
                user_id=emby_user_id,
                emby_item_id=emby_item_id,
                folder_tmdb_id=folder_tmdb_id,
                media_type=original_emby_item_type,
                local_item_path=local_item_path,
                override_cache_path=override_cache_path,
                fields_to_update=fields_to_update,
                update_children=update_children
            )
            updater.run_update()

        try:
            await asyncio.to_thread(_run_updater_sync)
            return True, "元数据已成功从 Emby 同步。"
        except Exception as e:
            log_audit("Emby", "失败", f"执行Emby元数据更新时发生严重错误: {e}", level="ERROR")
            return False, f"更新失败: {e}"