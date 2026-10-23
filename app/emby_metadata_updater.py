# -*- coding: utf-8 -*-
import os
import json
import sys
import logging
from datetime import datetime
from urllib.parse import urljoin

from .logger import log_audit

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    # This check remains useful for local script execution outside Docker
    log_audit("Emby", "初始化", "错误: 缺少 'requests' 库。请运行 'pip install requests' 来安装。", level="ERROR")
    sys.exit(1)

# --- 日志配置 ---
# Use the logger configured by the main FastAPI app

# --- 常量 ---
GENRE_ID_MAP = {
    "动作": 28, "冒险": 12, "动画": 16, "喜剧": 35, "犯罪": 80,
    "纪录片": 99, "剧情": 18, "家庭": 10751, "奇幻": 14, "历史": 36,
    "恐怖": 27, "音乐": 10402, "悬疑": 9648, "爱情": 10749, "科幻": 878,
    "电视电影": 10770, "惊悚": 53, "战争": 10752, "西部": 37,
    "动作冒险": 10759, "儿童": 10762, "新闻": 10763, "真人秀": 10764,
    "科幻奇幻": 10765, "肥皂剧": 10766, "脱口秀": 10767, "战争政治": 10768,
    # 英文映射
    "action": 28, "adventure": 12, "animation": 16, "comedy": 35, "crime": 80,
    "documentary": 99, "drama": 18, "family": 10751, "fantasy": 14, "history": 36,
    "horror": 27, "music": 10402, "mystery": 9648, "romance": 10749, "science fiction": 878,
    "tv movie": 10770, "thriller": 53, "war": 10752, "western": 37,
    "action & adventure": 10759, "kids": 10762, "news": 10763, "reality": 10764,
    "sci-fi & fantasy": 10765, "soap": 10766, "talk": 10767, "war & politics": 10768
}

class EmbyMetadataUpdater:
    """
    Web化改造版本：
    - 移除了所有 PyQt6 依赖。
    - 简化了类结构，将 Worker 和 Updater 合并。
    - 使用标准日志记录代替信号。
    - 设计为在 FastAPI 的后台任务中同步执行。
    """
    def __init__(self, server_url, api_key, user_id, emby_item_id, folder_tmdb_id, media_type, local_item_path,
                 override_cache_path, fields_to_update, update_children=False):
        self.server_url = server_url.strip().rstrip('/')
        self.api_key = api_key.strip()
        self.user_id = user_id # 直接使用传入的 UserID
        self.emby_item_id_to_update = str(emby_item_id).strip() # 新增：要更新的 Emby Item ID
        self.folder_tmdb_id = str(folder_tmdb_id).strip() # 新增：用于本地文件夹定位的 TMDB ID
        self.emby_media_type_overall = media_type
        self.local_item_path = local_item_path
        self.override_cache_path = override_cache_path # 新增：强制指定覆盖缓存路径
        self.fields_to_update = fields_to_update
        self.update_children_recursively = update_children
        
        self.session = self._create_session()
        
        # 根据媒体类型设置路径信息
        self.path_info = {}
        if self.emby_media_type_overall == "Series":
            self.path_info["series_folder_path"] = self.local_item_path
            self.path_info["main_json_path"] = os.path.join(self.local_item_path, "series.json")
        elif self.emby_media_type_overall == "Movie":
            self.path_info["series_folder_path"] = self.local_item_path # 对于电影，local_item_path 已经是包含 all.json 的目录
            self.path_info["main_json_path"] = os.path.join(self.local_item_path, "all.json") # 明确指定 all.json 文件

    def _create_session(self):
        session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _make_api_call(self, endpoint, params=None, method="GET", log_prefix="API"):
        url = f"{self.server_url}{endpoint}"
        headers = {'X-Emby-Token': self.api_key, 'accept': 'application/json'}
        try:
            response = self.session.request(method, url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            err_msg = f"{log_prefix} 错误: {method} {url} 失败: {e}"
            if hasattr(e, 'response') and e.response is not None:
                err_msg += f" - 状态码: {e.response.status_code}, 响应体: {e.response.text[:200]}"
            log_audit("Emby", "处理", err_msg, level="ERROR")
            raise

    def _fetch_tags_from_emby(self, emby_item_id_str: str, item_type: str):
        """
        使用特殊API端点根据 Emby Item ID 直接获取标签。
        """
        if not self.user_id:
            log_audit("Emby", "处理", "未提供UserID，无法继续获取标签。", level="ERROR")
            return []

        log_audit("Emby", "开始", f"正在使用特殊方法为 Emby Item ID {emby_item_id_str} ({item_type}) 获取标签...")
        params = {
            "UserId": self.user_id,
            "IncludeItemTypes": item_type,
            "Fields": "Tags,TagItems,ProviderIds",
            "Recursive": "true",
            "Ids": emby_item_id_str # 直接使用 Emby Item ID
        }
        
        # 尝试 /emby/Users/{uid}/Items 和 /Users/{uid}/Items
        item_endpoints = [f'/emby/Users/{self.user_id}/Items', f'/Users/{self.user_id}/Items']
        for endpoint in item_endpoints:
            try:
                response = self._make_api_call(endpoint, params=params, log_prefix="TagFetch")
                data = response.json()
                items = data.get("Items", [])
                if items:
                    item_data = items[0]
                    tags = []
                    if "Tags" in item_data and item_data["Tags"]:
                        tags = item_data["Tags"]
                    elif "TagItems" in item_data:
                        tags = [t.get('Name') for t in item_data["TagItems"] if t.get('Name')]
                    
                    log_audit("Emby", "完成", f"成功为《{item_data.get('Name', 'N/A')}》找到 {len(tags)} 个标签。")
                    return tags
            except Exception as e:
                log_audit("Emby", "失败", f"尝试端点 {endpoint} 获取标签失败: {e}", level="WARN")
                continue
        
        log_audit("Emby", "处理", f"未能通过特殊方法为 Emby Item ID {emby_item_id_str} 找到任何项目或标签。", level="WARN")
        return []

    # 移除 _get_emby_item_id_by_tmdb 方法，因为现在直接使用 Emby Item ID

    def _fetch_emby_item_details(self, emby_item_id_str: str, item_type_expected: str):
        log_audit("Emby", "开始", f"Emby获取: 正在获取 Emby Item ID {emby_item_id_str} ({item_type_expected}) 的详细信息...")
        fields_to_request = "Name,OriginalTitle,Overview,Genres,PremiereDate,EndDate,ProviderIds,People,Id,Type,Taglines,CommunityRating"
        if item_type_expected == "Season": fields_to_request += ",IndexNumber,ParentId"
        if item_type_expected == "Episode": fields_to_request += ",IndexNumber,ParentIndexNumber,ParentId"
            
        params_for_details = {'Fields': fields_to_request}
        # 直接使用 Emby Item ID 获取详情，不再需要通过 TMDB ID 查找
        detail_endpoints = [f"/Users/{self.user_id}/Items/{emby_item_id_str}", f"/Items/{emby_item_id_str}", f"/emby/Items/{emby_item_id_str}"]
        
        for endpoint_path in detail_endpoints:
            try:
                response = self._make_api_call(endpoint_path, params=params_for_details, log_prefix=f"EmbyDetails({item_type_expected})")
                item_details = response.json()
                if item_details and item_details.get("Type") == item_type_expected:
                    log_audit("Emby", "完成", f"Emby获取: 成功获取 '{item_details.get('Name', emby_item_id_str)}' 详细信息。")
                    return item_details
            except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                log_audit("Emby", "失败", f"Emby获取: 尝试端点 {endpoint_path} 时出错: {e}", level="WARN")
                continue
        log_audit("Emby", "失败", f"Emby获取错误: 无法获取 Emby Item ID {emby_item_id_str} ({item_type_expected}) 的详细数据。", level="ERROR")
        return None

    def _map_emby_data_to_local_format(self, emby_data: dict, emby_item_type: str) -> dict:
        mapped_data = {}
        if not emby_data: return mapped_data

        def format_emby_date_to_local(date_str):
            if not date_str: return ""
            try:
                dt_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt_obj.strftime("%Y-%m-%d")
            except Exception: return date_str.split("T")[0] if "T" in date_str else date_str

        # --- 剧集/电影级别字段 ---
        if emby_item_type in ["Series", "Movie"]:
            if "title" in self.fields_to_update:
                mapped_data["title"] = emby_data.get("Name") or emby_data.get("OriginalTitle") or ""
            if "original_title" in self.fields_to_update:
                mapped_data["original_title"] = emby_data.get("OriginalTitle", "")
            if "overview" in self.fields_to_update:
                mapped_data["overview"] = emby_data.get("Overview", "")
            if "tagline" in self.fields_to_update:
                taglines = emby_data.get("Taglines", [])
                mapped_data["tagline"] = taglines[0] if taglines else ""
            if "genres" in self.fields_to_update:
                emby_genres = emby_data.get("Genres", [])
                genres_list = []
                for g in emby_genres:
                    if not g: continue
                    genre_entry = {"name": g}
                    genre_id = GENRE_ID_MAP.get(g.lower())
                    if genre_id is not None:
                        genre_entry["id"] = genre_id
                    genres_list.append(genre_entry)
                mapped_data["genres"] = genres_list
            if "air_date" in self.fields_to_update:
                mapped_data["air_date"] = format_emby_date_to_local(emby_data.get("PremiereDate"))
            if "vote_average" in self.fields_to_update:
                mapped_data["vote_average"] = emby_data.get("CommunityRating")
            if emby_item_type == "Series" and "end_date" in self.fields_to_update:
                mapped_data["end_date"] = format_emby_date_to_local(emby_data.get("EndDate"))

        # --- 季级别字段 ---
        if emby_item_type == "Season":
            if "season_name" in self.fields_to_update:
                mapped_data["title"] = emby_data.get("Name") or ""
            if "season_overview" in self.fields_to_update:
                mapped_data["overview"] = emby_data.get("Overview", "")
            if "season_air_date" in self.fields_to_update:
                mapped_data["air_date"] = format_emby_date_to_local(emby_data.get("PremiereDate"))
        
        # --- 集级别字段 ---
        if emby_item_type == "Episode":
            if "episode_name" in self.fields_to_update:
                mapped_data["title"] = emby_data.get("Name") or ""
            if "episode_overview" in self.fields_to_update:
                mapped_data["overview"] = emby_data.get("Overview", "")
            if "episode_air_date" in self.fields_to_update:
                mapped_data["air_date"] = format_emby_date_to_local(emby_data.get("PremiereDate"))

        # --- 通用内部字段 ---
        mapped_data["_emby_item_id"] = emby_data.get("Id")
        if emby_item_type == "Season":
            mapped_data["_emby_season_number"] = emby_data.get("IndexNumber")
        elif emby_item_type == "Episode":
            mapped_data["_emby_parent_season_number"] = emby_data.get("ParentIndexNumber")
            mapped_data["_emby_episode_number"] = emby_data.get("IndexNumber")
        return mapped_data

    def _apply_updates_to_json_file(self, result: dict):
        # ... (此方法无需修改)
        target_path = result["local_json_path"]
        media_type = result["media_type"]
        emby_data = result["data_to_apply"]
        
        log_audit("Emby", "处理", f"收到 '{os.path.basename(target_path)}' ({media_type}) 的Emby元数据，准备应用更新。")
        # --- 修改开始：如果文件不存在，直接跳过 ---
        if not os.path.exists(target_path):
            log_audit("Emby", "处理", f"本地文件 '{target_path}' 不存在，跳过更新（已禁用自动创建）。", level="WARN")
            return
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                local_data = json.load(f)
        except Exception as e:
            log_audit("Emby", "处理", f"无法读取本地JSON文件 '{target_path}': {e}", level="ERROR")
            return


        # --- 应用逻辑 ---
        changed = False
        updated_data = json.loads(json.dumps(local_data)) # Deep copy
        
        key_map = {}
        if media_type in ["Series", "Movie"]:
            key_map = {
                "title": "title" if media_type == "Movie" else "name",
                "original_title": "original_title" if media_type == "Movie" else "original_name",
                "air_date": "release_date" if media_type == "Movie" else "first_air_date",
                "end_date": "last_air_date",
                "vote_average": "vote_average",
                "genres": "genres",
                "overview": "overview",
                "tagline": "tagline"
            }
        elif media_type == "Season":
            key_map = {
                "title": "name",
                "overview": "overview",
                "air_date": "air_date"
            }
        elif media_type == "Episode":
            key_map = {
                "title": "name",
                "overview": "overview",
                "air_date": "air_date"
            }

        for field, emby_value in emby_data.items():
            if field.startswith("_"): continue
            
            if field == "vote_average" and emby_value is None:
                continue

            json_key = key_map.get(field)
            if not json_key: continue
            if json_key in updated_data and updated_data[json_key] == emby_value:
                continue
            updated_data[json_key] = emby_value
            changed = True
            log_audit("Emby", "处理", f"  字段 '{json_key}' 已从 Emby 更新。")
        # --- 写入逻辑 ---
        if changed:
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    json.dump(updated_data, f, indent=4, ensure_ascii=False)
                log_audit("Emby", "完成", f"成功将更新后的元数据写入到 '{target_path}'。")
            except Exception as e:
                log_audit("Emby", "更新", f"写入JSON文件 '{target_path}' 失败: {e}", level="ERROR")
        else:
            log_audit("Emby", "处理", f"'{os.path.basename(target_path)}' 的元数据与Emby一致，无需写入。")
    def run_update(self):
        """启动更新流程。"""
        try:
            # --- 标签更新逻辑 ---
            if "tags" in self.fields_to_update:
                if not self.override_cache_path:
                    log_audit("Emby", "更新", "配置中未提供覆盖缓存路径 (override_cache_path)，无法写入 tags.json。", level="ERROR")
                    return

                tags_from_emby = self._fetch_tags_from_emby(self.emby_item_id_to_update, self.emby_media_type_overall)
                
                # 确定 item_id (folder_id) 使用 folder_tmdb_id
                if self.emby_media_type_overall == "Series":
                    item_folder_name = self.folder_tmdb_id
                    item_type_folder = "tmdb-tv"
                else: # Movie
                    item_folder_name = self.folder_tmdb_id
                    item_type_folder = "tmdb-movies2"

                if tags_from_emby:
                    # 强制使用 override_cache_path 构建路径
                    tags_json_path = os.path.join(self.override_cache_path, item_type_folder, item_folder_name, "tags.json")
                    
                    try:
                        log_audit("Emby", "开始", f"准备将 {len(tags_from_emby)} 个标签写入 '{tags_json_path}'...")
                        os.makedirs(os.path.dirname(tags_json_path), exist_ok=True)
                        with open(tags_json_path, 'w', encoding='utf-8') as f:
                            json.dump({"tags": tags_from_emby}, f, indent=2, ensure_ascii=False)
                        log_audit("Emby", "完成", f"成功写入标签文件。")
                    except Exception as e:
                        log_audit("Emby", "更新", f"写入标签文件 '{tags_json_path}' 失败: {e}", level="ERROR")
            # --- 其他元数据更新逻辑 ---
            # 检查是否还有除标签外的其他字段需要更新
            other_fields_to_update = [f for f in self.fields_to_update if f != 'tags']
            
            # 根据 emby_media_type_overall 确定主项的 local_json_path
            main_local_json_path = None
            if self.emby_media_type_overall == "Series":
                main_local_json_path = os.path.join(self.local_item_path, "series.json")
            elif self.emby_media_type_overall == "Movie":
                main_local_json_path = os.path.join(self.local_item_path, "all.json")
            elif self.emby_media_type_overall == "Season":
                # 对于季，需要获取其 IndexNumber 来构建路径
                season_details = self._fetch_emby_item_details(self.emby_item_id_to_update, "Season")
                if season_details and season_details.get("IndexNumber") is not None:
                    s_num = season_details["IndexNumber"]
                    main_local_json_path = os.path.join(self.local_item_path, f"season-{s_num}.json")
                else:
                    log_audit("Emby", "跳过", f"无法获取 Emby Item ID {self.emby_item_id_to_update} (Season) 的 IndexNumber，跳过季 JSON 文件更新。", level="WARN")
            elif self.emby_media_type_overall == "Episode":
                # 对于集，需要获取其 ParentIndexNumber 和 IndexNumber 来构建路径
                episode_details = self._fetch_emby_item_details(self.emby_item_id_to_update, "Episode")
                if episode_details and episode_details.get("ParentIndexNumber") is not None and episode_details.get("IndexNumber") is not None:
                    s_num = episode_details["ParentIndexNumber"]
                    ep_num = episode_details["IndexNumber"]
                    main_local_json_path = os.path.join(self.local_item_path, f"season-{s_num}-episode-{ep_num}.json")
                else:
                    log_audit("Emby", "跳过", f"无法获取 Emby Item ID {self.emby_item_id_to_update} (Episode) 的季或集编号，跳过集 JSON 文件更新。", level="WARN")
            if main_local_json_path and other_fields_to_update:
                main_emby_details = self._fetch_emby_item_details(self.emby_item_id_to_update, self.emby_media_type_overall)
                if not main_emby_details: return

                mapped_main_data = self._map_emby_data_to_local_format(main_emby_details, self.emby_media_type_overall)
                self._apply_updates_to_json_file({
                    "media_type": self.emby_media_type_overall,
                    "data_to_apply": mapped_main_data, 
                    "local_json_path": main_local_json_path
                })
            elif not other_fields_to_update:
                log_audit("Emby", "更新", f"当前更新项为 '{self.emby_media_type_overall}'，没有其他字段需要更新，跳过主项 JSON 文件更新。")
            else:
                log_audit("Emby", "处理", f"无法确定 '{self.emby_media_type_overall}' 类型的主项 JSON 文件路径，跳过更新。", level="WARN")
            # 只有当主项是 Series 且请求递归更新时，才处理子项
            if self.emby_media_type_overall == "Series" and self.update_children_recursively:
                series_root_folder = self.local_item_path # series_root_folder 应该直接是 local_item_path
                if not series_root_folder: 
                    log_audit("Emby", "处理", "剧集根目录未知，无法处理子项。", level="ERROR")
                    return
                
                season_fields_requested = any(f.startswith('season_') for f in self.fields_to_update)
                episode_fields_requested = any(f.startswith('episode_') for f in self.fields_to_update)

                if season_fields_requested or episode_fields_requested:
                    seasons_summary_resp = self._make_api_call(f"/Shows/{self.emby_item_id_to_update}/Seasons", {'Fields': 'Id,IndexNumber'})
                    seasons_summary = seasons_summary_resp.json().get("Items", [])

                    for season in seasons_summary:
                        s_id, s_num = season.get("Id"), season.get("IndexNumber")
                        if s_id is None or s_num is None: continue

                        if season_fields_requested:
                            s_details = self._fetch_emby_item_details(s_id, "Season")
                            if not s_details: continue
                            mapped_s_data = self._map_emby_data_to_local_format(s_details, "Season")
                            self._apply_updates_to_json_file({
                                "media_type": "Season", "data_to_apply": mapped_s_data,
                                "local_json_path": os.path.join(series_root_folder, f"season-{s_num}.json")
                            })
                        
                        if episode_fields_requested:
                            episodes_summary_resp = self._make_api_call(f"/Shows/{self.emby_item_id_to_update}/Episodes", {'SeasonId': s_id, 'Fields': 'Id,IndexNumber,ParentIndexNumber'})
                            episodes_summary = episodes_summary_resp.json().get("Items", [])
                            for episode in episodes_summary:
                                ep_id, ep_num = episode.get("Id"), episode.get("IndexNumber")
                                if ep_id is None or ep_num is None: continue
                                ep_details = self._fetch_emby_item_details(ep_id, "Episode")
                                if not ep_details: continue
                                mapped_ep_data = self._map_emby_data_to_local_format(ep_details, "Episode")
                                self._apply_updates_to_json_file({
                                    "media_type": "Episode", "data_to_apply": mapped_ep_data,
                                    "local_json_path": os.path.join(series_root_folder, f"season-{s_num}-episode-{ep_num}.json")
                                })
            log_audit("Emby", "处理", "Emby元数据获取流程执行完毕。")
        except Exception as e:
            log_audit("Emby", "失败", f"执行更新时发生严重错误: {e}", level="ERROR")
        finally:
            if self.session: self.session.close()
