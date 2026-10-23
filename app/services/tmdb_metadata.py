import httpx
import json
import os
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from .configuration import ConfigurationService
from .editor import EditorService
from .scanner import ScannerService
from .emby_integration import EmbyIntegrationService
from .bangumi_provider import BangumiProvider
from .metadata_mapper import MetadataMapper
from ..logger import log_audit


TMDB_BASE_URL = "https://api.themoviedb.org/3"

class TmdbMetadataService:
    # ID to Chinese Name Map
    GENRE_ID_NAME_MAP = {
        28: "动作", 12: "冒险", 16: "动画", 35: "喜剧", 80: "犯罪",
        99: "纪录片", 18: "剧情", 10751: "家庭", 14: "奇幻", 36: "历史",
        27: "恐怖", 10402: "音乐", 9648: "悬疑", 10749: "爱情", 878: "科幻",
        10770: "电视电影", 53: "惊悚", 10752: "战争", 37: "西部",
        10759: "动作冒险", 10762: "儿童", 10763: "新闻", 10764: "真人秀",
        10765: "科幻奇幻", 10766: "肥皂剧", 10767: "脱口秀", 10768: "战争政治"
    }

    def __init__(self, 
                 config_service: ConfigurationService, 
                 editor_service: EditorService,
                 scanner_service: ScannerService,
                 emby_service: EmbyIntegrationService):
        self.config_service = config_service
        self.editor_service = editor_service
        self.scanner_service = scanner_service
        self.emby_service = emby_service
        self.bangumi_provider = BangumiProvider()
        self.mapper = MetadataMapper()
        self.mapping_rules = self._load_mapping_rules()

    def _load_mapping_rules(self) -> Dict[str, Any]:
        """Loads the TMDB to local metadata mapping rules."""
        # Order: 
        # 1. App Definitions (Built-in, standard)
        # 2. Data Directory (User override, optional)
        
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # app/
        definitions_path = os.path.join(base_path, "definitions", "tmdb_mapping.json")
        
        possible_paths = [
            definitions_path,
            "/data/tmdb_mapping.json",
            "data/tmdb_mapping.json"
        ]
        
        for mapping_path in possible_paths:
            if os.path.exists(mapping_path):
                try:
                    with open(mapping_path, 'r', encoding='utf-8') as f:
                        rules = json.load(f)
                        log_audit("元数据", "处理", f"✅ [映射] 已加载 TMDB 映射规则: {mapping_path}, 类型: {list(rules.keys())}")
                        return rules
                except Exception as e:
                    log_audit("元数据", "失败", f"从 {mapping_path} 加载映射规则失败: {e}", level="ERROR")
        log_audit("元数据", "处理", "在任何预期位置都找不到 tmdb_mapping.json。", level="CRITICAL")
        return {}

    async def fetch_tmdb_data(self, item_type: str, tmdb_id: str, lang: str, season_number: Optional[int] = None, episode_number: Optional[int] = None) -> Dict[str, Any]:
        """Fetches raw data from TMDB API."""
        api_key = self.config_service.get('tmdb_api_key')
        
        if not api_key:
            if hasattr(self.config_service, 'config') and isinstance(self.config_service.config, dict):
                 api_key = self.config_service.config.get('tmdb_api_key')
        
        if not api_key:
            log_audit("元数据", "处理", "配置中缺少 TMDB API Key。", level="ERROR")
            raise ValueError("TMDB API Key 未配置")

        # 获取配置中的回退语言
        fallback_langs = self.config_service.get('tmdb_image_languages', 'zh-CN,en,ja,ko,null')
        # 确保当前请求的语言排在回退列表的第一位
        final_image_langs = f"{lang},{fallback_langs}" if lang not in fallback_langs else fallback_langs

        params = {
            "api_key": api_key,
            "language": lang,
            "include_image_language": final_image_langs
        }
        
        endpoint = ""
        # Determine endpoint and extra appends based on type
        if item_type == "movie":
            endpoint = f"/movie/{tmdb_id}"
            params["append_to_response"] = "credits,images,videos,external_ids,release_dates,keywords,translations"
        elif item_type == "tv":
            endpoint = f"/tv/{tmdb_id}"
            params["append_to_response"] = "credits,aggregate_credits,external_ids,content_ratings,keywords,alternative_titles,translations,videos,images"
        elif item_type == "season":
            if season_number is None: raise ValueError("获取季度信息需要季号")
            endpoint = f"/tv/{tmdb_id}/season/{season_number}"
            params["append_to_response"] = "credits,aggregate_credits,images,videos,translations,external_ids"
        elif item_type == "episode":
            if season_number is None or episode_number is None: raise ValueError("获取剧集信息需要季号和集号")
            endpoint = f"/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}"
            params["append_to_response"] = "credits,images,videos,translations,external_ids"
        elif item_type == "person":
            endpoint = f"/person/{tmdb_id}"
            params["append_to_response"] = "combined_credits,external_ids,translations,images"
        else:
            raise ValueError(f"不支持的项目类型: {item_type}")

        url = f"{TMDB_BASE_URL}{endpoint}"
        
        log_audit("元数据", "开始", f"DEBUG: 准备请求 TMDB API")
        log_audit("元数据", "处理", f"DEBUG: URL: {url}")
        log_audit("元数据", "处理", f"DEBUG: Params: {params}")
        proxy_url = self.config_service.get_proxy_url('tmdb')
        proxies = {"http://": proxy_url, "https://": proxy_url} if proxy_url else None
        if proxy_url:
            log_audit("元数据", "处理", f"[Proxy] TMDB 元数据请求 (httpx) 将通过代理: {proxy_url}")
        async with httpx.AsyncClient(proxy=proxy_url) as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # 增加对返回内容的检查日志
                log_audit("元数据", "完成", f"DEBUG: TMDB 响应成功，Keys: {list(data.keys())}")
                if item_type == "person":
                    # person 类型使用 combined_credits 而非 credits
                    if "combined_credits" in data:
                        c = data["combined_credits"]
                        cast_len = len(c.get("cast", []))
                        crew_len = len(c.get("crew", []))
                        log_audit("元数据", "处理", f"DEBUG: 发现 combined_credits 数据 - Cast: {cast_len}, Crew: {crew_len}")
                    else:
                        log_audit("元数据", "处理", "DEBUG: TMDB 响应中缺失 'combined_credits' 字段！", level="WARN")
                else:
                    if "credits" in data:
                        c = data["credits"]
                        cast_len = len(c.get("cast", []))
                        crew_len = len(c.get("crew", []))
                        guest_len = len(c.get("guest_stars", []))
                        log_audit("元数据", "处理", f"DEBUG: 发现 credits 数据 - Cast: {cast_len}, Crew: {crew_len}, GuestStars: {guest_len}")
                    else:
                        log_audit("元数据", "处理", "DEBUG: TMDB 响应中缺失 'credits' 字段！", level="WARN")
                return data
            except httpx.HTTPStatusError as e:
                log_audit("元数据", "处理", f"TMDB API Error: {e.response.status_code} - {e.response.text}", level="ERROR")
                raise Exception(f"TMDB API Error: {e.response.status_code}")
            except Exception as e:
                log_audit("元数据", "失败", f"获取 TMDB 数据时发生 network 错误: {e}", level="ERROR")
                raise

    async def search_tmdb(self, item_type: str, query: str, lang: str = "zh-CN", page: int = 1) -> Dict[str, Any]:
        """Searches TMDB API for movies, tv shows or multi."""
        api_key = self.config_service.get('tmdb_api_key')
        if not api_key:
            raise ValueError("TMDB API Key 未配置")

        fallback_langs = self.config_service.get('tmdb_image_languages', 'zh-CN,en,ja,ko,null')
        final_image_langs = f"{lang},{fallback_langs}" if lang not in fallback_langs else fallback_langs

        params = {
            "api_key": api_key,
            "language": lang,
            "include_image_language": final_image_langs,
            "query": query,
            "page": page,
            "include_adult": "false"
        }
        
        # Determine endpoint
        if item_type == "movie": endpoint = "/search/movie"
        elif item_type == "tv": endpoint = "/search/tv"
        else: endpoint = "/search/multi"

        url = f"{TMDB_BASE_URL}{endpoint}"
        proxy_url = self.config_service.get_proxy_url('tmdb')
        
        async with httpx.AsyncClient(proxy=proxy_url) as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                log_audit("元数据", "处理", f"TMDB Search Error ({item_type}): {e}", level="ERROR")
                return {"page": page, "results": [], "total_pages": 0, "total_results": 0}

    def _transform_releases(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Transform 'release_dates' structure to local 'releases' structure if needed
        results = data.get("release_dates", {}).get("results", [])
        countries = []
        for res in results:
            iso = res.get("iso_3166_1")
            for rel in res.get("release_dates", []):
                countries.append({
                    "iso_3166_1": iso,
                    "certification": rel.get("certification", ""),
                    "release_date": rel.get("release_date"),
                    "primary": False 
                })
        return {"countries": countries}

    def _transform_trailers(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # Transform 'videos' to 'trailers'
        results = data.get("videos", {}).get("results", [])
        youtube = []
        for vid in results:
            if vid.get("site") == "YouTube":
                youtube.append({
                    "name": vid.get("name"),
                    "source": vid.get("key"),
                    "size": str(vid.get("size", "HD")),
                    "type": vid.get("type")
                })
        return {"youtube": youtube}

    def _transform_keywords(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # TMDB: {"keywords": {"keywords": [...]}} (Movie) or {"results": [...]} (TV)
        kws = data.get("keywords", {})
        keyword_list = kws.get("keywords", []) or kws.get("results", [])
        return {"keywords": keyword_list}

    def _transform_genres(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Transform genres to force Chinese names based on ID."""
        genres = data.get("genres", [])
        transformed_genres = []
        for g in genres:
            genre_id = g.get("id")
            name = g.get("name")
            
            # If ID is in our map, force the Chinese name
            if genre_id in self.GENRE_ID_NAME_MAP:
                name = self.GENRE_ID_NAME_MAP[genre_id]
            
            transformed_genres.append({
                "id": genre_id,
                "name": name
            })
        return transformed_genres

    def map_data(self, item_type: str, tmdb_data: Dict[str, Any], fields_to_update: Optional[List[str]] = None) -> Dict[str, Any]:
        """Maps TMDB data to local format based on rules."""
        if not self.mapping_rules:
            # Try reloading if empty
            log_audit("元数据", "处理", "映射规则为空，尝试重新加载...", level="WARN")
            self.mapping_rules = self._load_mapping_rules()
            
        if item_type not in self.mapping_rules:
            log_audit("元数据", "处理", f"未找到类型 '{item_type}' 的映射规则。可用键: {list(self.mapping_rules.keys())}", level="ERROR")
            return {}
        
        rules = self.mapping_rules[item_type]
        mapped_data = {}
        
        # If fields_to_update is None or empty, update ALL fields defined in rules
        target_fields = fields_to_update if fields_to_update else rules.keys()
        
        log_audit("元数据", "开始", f"正在映射 {item_type} 数据。目标字段: {target_fields}")
        for field in target_fields:
            if field not in rules:
                log_audit("元数据", "处理", f"请求了字段 '{field}' 但在 {item_type} 规则中未找到", level="WARN")
                continue
            
            rule = rules[field]
            source_key = rule.get("source")
            
            if field in ['credits', 'casts']:
                log_audit("元数据", "开始", f"DEBUG: 正在映射演职员字段 '{field}'，源键: '{source_key}'")
            if not source_key: 
                log_audit("元数据", "处理", f"规则字段 '{field}' 未定义源键", level="WARN")
                continue

            # Special intercept for genres
            if field == 'genres':
                mapped_data[field] = self._transform_genres(tmdb_data)
                continue

            if source_key not in tmdb_data and rule.get("type") not in ["transform_releases", "transform_trailers", "transform_keywords"]:
                 log_audit("元数据", "处理", f"Source key '{source_key}' missing in TMDB data for field '{field}'", level="DEBUG")
                 continue

            val = tmdb_data.get(source_key)
            
            # Apply transforms
            transform_type = rule.get("type")
            
            try:
                if transform_type == "complex_copy":
                    mapping = rule.get("mapping", {})
                    new_val = {}
                    source_obj = tmdb_data.get(source_key, {})
                    if isinstance(source_obj, dict):
                        for local_sub, tmdb_sub in mapping.items():
                            val = source_obj.get(tmdb_sub)
                            # 专项逻辑：如果是外部ID，则过滤掉 null/空值
                            if field == "external_ids":
                                if val is not None and val != "" and val != []:
                                    new_val[local_sub] = val
                            else:
                                # 其他字段（如 credits）保留默认值，即使是空列表
                                new_val[local_sub] = val if val is not None else []
                    if new_val or field != "external_ids":
                        mapped_data[field] = new_val

                elif transform_type == "transform_releases":
                    mapped_data[field] = self._transform_releases(tmdb_data)
                
                elif transform_type == "transform_trailers":
                    mapped_data[field] = self._transform_trailers(tmdb_data)
                    
                elif transform_type == "transform_keywords":
                    mapped_data[field] = self._transform_keywords(tmdb_data)

                else:
                    # Direct copy
                    if source_key in tmdb_data:
                         mapped_data[field] = tmdb_data[source_key]
            except Exception as e:
                log_audit("元数据", "处理", f"映射字段 '{field}' 时出错: {e}", level="ERROR")
        log_audit("元数据", "完成", f"映射完成。已映射键: {list(mapped_data.keys())}")
        return mapped_data

    async def update_metadata(self, 
                              item_type: str, 
                              tmdb_id: str, 
                              lang: str, 
                              fields: Optional[List[str]] = None, 
                              overwrite: bool = False,
                              season_number: Optional[int] = None,
                              episode_number: Optional[int] = None,
                              trigger_refresh: bool = False,
                              update_season_episodes: bool = False) -> Tuple[bool, str]:
        
        # 1. Fetch
        try:
            tmdb_data = await self.fetch_tmdb_data(item_type, tmdb_id, lang, season_number, episode_number)
        except Exception as e:
            return False, f"获取数据失败: {str(e)}"

        # 2. Map
        mapped_new_data = self.map_data(item_type, tmdb_data, fields)
        if not mapped_new_data:
            return False, "无数据被映射或规则丢失"
        
        log_audit("元数据", "完成", f"数据映射成功，准备更新本地文件...")
        # 3. Load Existing & Save (Main Item)
        editor_type_key = "tmdb-movies2" if item_type == "movie" else "tmdb-tv"
        target_filename = ""
        if item_type == "movie": target_filename = "all.json"
        elif item_type == "tv": target_filename = "series.json"
        elif item_type == "season": target_filename = f"season-{season_number}.json"
        elif item_type == "episode": target_filename = f"season-{season_number}-episode-{episode_number}.json"

        override_path = self.config_service.get('override_cache_path')
        if not override_path:
            return False, "覆盖路径未配置"

        target_dir = os.path.join(override_path, editor_type_key, tmdb_id)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
            
        target_file_path = os.path.join(target_dir, target_filename)
        
        current_data = {}
        if os.path.exists(target_file_path):
            try:
                with open(target_file_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            except Exception as e:
                log_audit("元数据", "处理", f"无法读取现有文件 {target_file_path}: {e}", level="WARN")
        if overwrite:
            current_data.update(mapped_new_data)
        else:
            for key, val in mapped_new_data.items():
                if key not in current_data or current_data[key] in [None, "", [], {}]:
                    current_data[key] = val

        try:
            with open(target_file_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=4)
            log_audit("元数据", "完成", f"成功更新文件: {target_file_path}")
        except Exception as e:
            return False, f"写入文件失败: {e}"

        # 5. Apply custom external_ids from external_ids.json if exists
        await self._apply_custom_external_ids(item_type, tmdb_id, target_dir, season_number, episode_number)

        # 4. Handle Recursive Updates
        # Case A: Whole Series Update (TV -> All Seasons -> All Episodes)
        if item_type == "tv" and update_season_episodes and "seasons" in tmdb_data:
            seasons = tmdb_data["seasons"]
            log_audit("元数据", "开始", f"整剧更新: 正在处理 TV {tmdb_id} 的 {len(seasons)} 个季度")
            # Filter fields to only those valid for season type
            season_fields = self._filter_fields_for_type(fields, "season")
            
            for season in seasons:
                s_num = season.get("season_number")
                if s_num is None: continue
                
                # Rate limiting to be safe
                await asyncio.sleep(0.5)
                
                log_audit("元数据", "开始", f"整剧更新: 正在处理第 {s_num} 季")
                # Recursively call update_metadata for the season with update_season_episodes=True
                # This will trigger Case B below for each season
                await self.update_metadata(
                    item_type="season",
                    tmdb_id=tmdb_id,
                    lang=lang,
                    fields=season_fields, # Filtered fields for season
                    overwrite=overwrite,
                    season_number=s_num,
                    update_season_episodes=True # Ensure episodes in season are updated
                )

        # Case B: Batch Season Episodes Update (Season -> All Episodes)
        if item_type == "season" and update_season_episodes and "episodes" in tmdb_data:
            episodes = tmdb_data["episodes"]
            log_audit("元数据", "更新", f"批量更新第 {season_number} 季的 {len(episodes)} 集")
            # Filter fields to only those valid for episode type
            episode_fields = self._filter_fields_for_type(fields, "episode")
            
            for ep_data in episodes:
                ep_num = ep_data.get("episode_number")
                if ep_num is None: continue
                
                # Adapt structure for map_data
                # Season response has guest_stars/crew at root of episode object
                # map_data expects them under 'credits' (based on direct API response structure)
                ep_data['credits'] = {
                    'guest_stars': ep_data.get('guest_stars', []),
                    'crew': ep_data.get('crew', [])
                }
                
                mapped_ep = self.map_data("episode", ep_data, episode_fields)
                if not mapped_ep: continue
                
                ep_filename = f"season-{season_number}-episode-{ep_num}.json"
                ep_path = os.path.join(target_dir, ep_filename)
                
                ep_current = {}
                if os.path.exists(ep_path):
                    try:
                        with open(ep_path, 'r', encoding='utf-8') as f:
                            ep_current = json.load(f)
                    except: pass
                
                if overwrite:
                    ep_current.update(mapped_ep)
                else:
                    for k, v in mapped_ep.items():
                        if k not in ep_current or ep_current[k] in [None, "", [], {}]:
                            ep_current[k] = v
                
                try:
                    with open(ep_path, 'w', encoding='utf-8') as f:
                        json.dump(ep_current, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    log_audit("元数据", "失败", f"更新第 {ep_num} 集失败: {e}", level="ERROR")
        # 6. Refresh
        if trigger_refresh:
            log_audit("元数据", "处理", "5秒后触发 Emby 刷新...")
            await asyncio.sleep(5)
            
            # For TV components (season/episode), we refresh the main TV series
            refresh_type = "tmdb-tv" if item_type in ["tv", "season", "episode"] else "tmdb-movies2"
            
            # tmdb_id is always the main ID (Movie ID or TV Series ID) in this context
            refresh_success, refresh_msg = await self.emby_service.refresh_item_in_emby(refresh_type, tmdb_id)
            if refresh_success:
                log_audit("元数据", "完成", f"Emby 刷新触发成功: {refresh_msg}")
            else:
                log_audit("元数据", "失败", f"Emby 刷新失败: {refresh_msg}", level="WARN")
        return True, "更新成功"

    async def get_bangumi_preview(self, subject_id: int) -> Dict[str, Any]:
        """
        Fetch preview info using BangumiProvider (API + cache).
        """
        subject_result = await self.bangumi_provider.get_subject(subject_id)
        subject = subject_result.get("data")
        if not subject:
            raise ValueError("未找到条目")

        episodes_result = await self.bangumi_provider.get_episodes(subject_id)
        episodes = episodes_result.get("data", [])

        return {
            "title": subject.get('name_cn') or subject.get('name'),
            "episodes": [
                {
                    "id": ep.get('id'),
                    "sort": ep.get('sort'),
                    "name": ep.get('name_cn') or ep.get('name'),
                    "airdate": ep.get('airdate'),
                    "type": ep.get('type')
                } for ep in episodes
            ]
        }

    async def generate_custom_override(self,
                                     source_item_type: str,
                                     source_tmdb_id: str,
                                     target_tmdb_id: str,
                                     lang: str = "zh-CN",
                                     fields: Optional[List[str]] = None,
                                     overwrite: bool = True,
                                     source_season: Optional[int] = None,
                                     target_season: Optional[int] = None,
                                     source_episode: Optional[int] = None,
                                     target_episode: Optional[int] = None,
                                     trigger_refresh: bool = False,
                                     recursive: bool = False,
                                     source: str = "tmdb",
                                     target_item_type: Optional[str] = None) -> Tuple[bool, str]:
        """
        [New Tool] Flexible override generation. Supports TMDB and Bangumi.
        Allows mapping from a source ID/Season/Episode to a different target folder/filename.
        """
        log_audit("元数据", "开始", f"开始生成自定义覆盖: 源={source}/{source_item_type}/{source_tmdb_id} -> 目标={target_tmdb_id}")
        try:
            # Determine effective target type for mapping and paths
            effective_target_type = target_item_type
            if not effective_target_type:
                if source_item_type in ["tv", "season", "episode"]: effective_target_type = "tv"
                else: effective_target_type = "movie"

            # 1. Fetch data from SOURCE
            tmdb_data = {}
            mapped_new_data = {}

            if source == "tmdb":
                tmdb_data = await self.fetch_tmdb_data(source_item_type, source_tmdb_id, lang, source_season, source_episode)
                mapped_new_data = self.map_data(source_item_type, tmdb_data, fields)
            elif source == "bangumi":
                # Handle Bangumi Source
                bgm_id = int(source_tmdb_id)
                if source_item_type in ["movie", "tv"]:
                    subject_result = await self.bangumi_provider.get_subject(bgm_id)
                    subject_data = subject_result.get("data")
                    if not subject_data: return False, f"未找到 Bangumi 条目 {bgm_id}"
                    
                    # New: Fetch Character data for real Cast mapping
                    characters_result = await self.bangumi_provider.get_characters(bgm_id)
                    characters_data = characters_result.get("data", [])
                    
                    target_map_type = 'Movie' if effective_target_type == "movie" else 'Series'
                    mapped_new_data = self.mapper.map_subject(subject_data, target_map_type, characters_data=characters_data)
                elif source_item_type == "episode":
                    # Fetch episodes via Provider (API + cache)
                    eps_result = await self.bangumi_provider.get_episodes(bgm_id)
                    eps_data = eps_result.get("data", [])
                    # Find the episode with matching 'sort' (episode number)
                    target_ep = next((ep for ep in eps_data if ep.get('sort') == source_episode), None)
                    if not target_ep: return False, f"在条目 {bgm_id} 中未找到序号为 {source_episode} 的 Bangumi 剧集"
                    mapped_new_data = self.mapper.map_episode(target_ep)
                else:
                    return False, f"Bangumi 源不支持项目类型: {source_item_type}"
            else:
                return False, f"不支持的源: {source}"

        except Exception as e:
            return False, f"获取/映射失败: {str(e)}"

        if not mapped_new_data:
            return False, "无数据被映射或规则丢失"

        # [Important] Apply Minimum Required Format Template & Coordinate Override
        final_json_data = {}
        target_id_val = None
        try: target_id_val = int(target_tmdb_id)
        except: target_id_val = target_tmdb_id

        if effective_target_type == "movie":
            # Template based on all.json
            final_json_data = {
                "id": target_id_val,
                "imdb_id": "", "title": "", "original_title": "", "overview": "", "tagline": "",
                "release_date": "", "vote_average": 0.0, "production_countries": [], "production_companies": [],
                "genres": [],
                "casts": {"cast": [], "crew": []},
                "releases": {"countries": []},
                "belongs_to_collection": None,
                "trailers": {"youtube": []}
            }
        elif effective_target_type == "tv":
            # Template based on series.json
            final_json_data = {
                "id": target_id_val,
                "name": "", "original_name": "", "overview": "", "vote_average": 0.0,
                "episode_run_time": [], "first_air_date": "", "last_air_date": "",
                "status": "", "networks": [], "genres": [],
                "external_ids": {"imdb_id": "", "tvrage_id": None, "tvdb_id": None},
                "videos": {"results": []},
                "content_ratings": {"results": []},
                "credits": {"cast": [], "crew": []}
            }
        
        # Specific overrides for Season/Episode which are sub-types of TV
        if source_item_type == "season":
            final_json_data = {
                "name": "", "overview": "", "air_date": "",
                "season_number": target_season,
                "external_ids": {},
                "credits": {"cast": [], "crew": []}
            }
        elif source_item_type == "episode":
            final_json_data = {
                "name": "", "overview": "", "air_date": "", "vote_average": 0.0,
                "production_code": "",
                "season_number": target_season, "episode_number": target_episode,
                "videos": {"results": []},
                "external_ids": {},
                "credits": {"cast": [], "guest_stars": [], "crew": []}
            }

        # Merge fetched data on top of template (preserving hierarchy for dicts if necessary)
        # For simplicity in this logic, we update the template with the flat results from map_data
        # but we need to handle specific nested objects that might be in mapped_new_data
        
        # [Cross-Type Mapping Fix]
        if source_item_type in ["tv", "season", "episode"] and effective_target_type == "movie":
            if "name" in mapped_new_data: mapped_new_data["title"] = mapped_new_data.pop("name")
            if "original_name" in mapped_new_data: mapped_new_data["original_title"] = mapped_new_data.pop("original_name")
            if "first_air_date" in mapped_new_data: mapped_new_data["release_date"] = mapped_new_data.pop("first_air_date")
            if "credits" in mapped_new_data: mapped_new_data["casts"] = mapped_new_data.pop("credits")
        elif source_item_type == "movie" and effective_target_type == "tv":
            if "title" in mapped_new_data: mapped_new_data["name"] = mapped_new_data.pop("title")
            if "original_title" in mapped_new_data: mapped_new_data["original_name"] = mapped_new_data.pop("original_title")
            if "release_date" in mapped_new_data: mapped_new_data["first_air_date"] = mapped_new_data.pop("release_date")
            if "casts" in mapped_new_data: mapped_new_data["credits"] = mapped_new_data.pop("casts")

        # [Tags Extraction]
        # 仅处理显式的 tags 字段（如来自 Bangumi），TMDB 的 keywords 留在主 JSON 中，不污染 tags.json
        tags_list = []
        if "tags" in mapped_new_data:
            tags_list = mapped_new_data.pop("tags")

        for k, v in mapped_new_data.items():
            if k in final_json_data and isinstance(final_json_data[k], dict) and isinstance(v, dict):
                final_json_data[k].update(v)
            else:
                final_json_data[k] = v

        # Final Force-Override for IDs and Coordinates to ensure mapping is correct
        # 注意：仅对根级别项目(电影/剧集)强制覆盖 ID 为目标 ID (文件夹名)
        if source_item_type in ["movie", "tv"]:
            if "id" in final_json_data: final_json_data["id"] = target_id_val
        
        if source_item_type == "season":
            final_json_data["season_number"] = target_season
        elif source_item_type == "episode":
            final_json_data["season_number"] = target_season
            final_json_data["episode_number"] = target_episode

        # 3. Path Setup (Using TARGET IDs/Numbers)
        editor_type_key = "tmdb-movies2" if effective_target_type == "movie" else "tmdb-tv"
        target_filename = ""
        if source_item_type == "movie": 
            target_filename = "all.json"
        elif source_item_type == "tv": 
            target_filename = "series.json"
        elif source_item_type == "season": 
            target_filename = f"season-{target_season}.json"
        elif source_item_type == "episode": 
            target_filename = f"season-{target_season}-episode-{target_episode}.json"
        
        # Override filename if it's a root subject but target type was changed
        if source_item_type in ["movie", "tv"]:
            target_filename = "all.json" if effective_target_type == "movie" else "series.json"

        override_path = self.config_service.get("override_cache_path")
        if not override_path:
            return False, "覆盖路径未配置"

        target_dir = os.path.join(override_path, editor_type_key, target_tmdb_id)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        # --- Save Tags to tags.json ---
        if tags_list:
            tags_file_path = os.path.join(target_dir, "tags.json")
            existing_tags = []
            if os.path.exists(tags_file_path):
                try:
                    with open(tags_file_path, "r", encoding="utf-8") as f:
                        t_data = json.load(f)
                        existing_tags = t_data.get("tags", [])
                except: pass
            
            if overwrite:
                final_tags = sorted(list(set(tags_list)))
            else:
                final_tags = sorted(list(set(existing_tags + tags_list)))
                
            try:
                with open(tags_file_path, "w", encoding="utf-8") as f:
                    json.dump({"tags": final_tags}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                log_audit("元数据", "失败", f"写入 tags.json 失败: {e}", level="ERROR")
        target_file_path = os.path.join(target_dir, target_filename)
        
        # 4. Save Logic (Independent Implementation)
        current_data = {}
        if os.path.exists(target_file_path):
            try:
                with open(target_file_path, "r", encoding="utf-8") as f:
                    current_data = json.load(f)
            except: pass

        # Merge mapped data into our template-based final_json_data first
        if overwrite:
            current_data.update(final_json_data)
        else:
            for key, val in final_json_data.items():
                if key not in current_data or current_data[key] in [None, "", [], {}]:
                    current_data[key] = val

        try:
            with open(target_file_path, "w", encoding="utf-8") as f:
                json.dump(current_data, f, ensure_ascii=False, indent=4)
            log_audit("元数据", "完成", f"成功生成覆盖文件: {target_file_path}")
        except Exception as e:
            return False, f"写入文件失败: {e}"

        # 5. Recursive (Standard 1:1 mapping when recursive)
        if recursive:
            if source == "tmdb":
                if source_item_type == "tv" and "seasons" in tmdb_data:
                    for season in tmdb_data["seasons"]:
                        s_num = season.get("season_number")
                        if s_num is None: continue
                        await asyncio.sleep(0.3)
                        await self.generate_custom_override(
                            source_item_type="season", source_tmdb_id=source_tmdb_id, target_tmdb_id=target_tmdb_id,
                            lang=lang, fields=fields, overwrite=overwrite,
                            source_season=s_num, target_season=s_num, recursive=True, source=source
                        )
                elif source_item_type == "season" and "episodes" in tmdb_data:
                    for ep_data in tmdb_data["episodes"]:
                        ep_num = ep_data.get("episode_number")
                        if ep_num is None: continue
                        
                        # [Important] 为了获取完整的演职员表(包括 cast)，必须递归调用 generate_custom_override
                        # 而不能直接处理季度接口返回的浅层 ep_data
                        log_audit("元数据", "开始", f"正在递归生成第 {target_season} 季 第 {ep_num} 集的完整元数据...")
                        await asyncio.sleep(0.2) # 稍微延迟避免频率限制
                        await self.generate_custom_override(
                            source_item_type="episode",
                            source_tmdb_id=source_tmdb_id,
                            target_tmdb_id=target_tmdb_id,
                            lang=lang,
                            fields=fields,
                            overwrite=overwrite,
                            source_season=source_season,
                            target_season=target_season,
                            source_episode=ep_num,
                            target_episode=ep_num,
                            recursive=False, # 剧集本身不再递归
                            source=source,
                            target_item_type=target_item_type,
                            trigger_refresh=False # 批量生成时中间步骤不刷新
                        )
            
            elif source == "bangumi" and source_item_type == "tv":
                # Bangumi Recursive: Fetch all episodes and generate JSONs
                try:
                    actual_target_season = target_season if target_season is not None else 1
                    eps_result = await self.bangumi_provider.get_episodes(int(source_tmdb_id))
                    eps_list = eps_result.get("data", [])
                    
                    log_audit("元数据", "处理", f"Bangumi 递归: 为条目 {source_tmdb_id} 找到 {len(eps_list)} 集 (来源: {self.bangumi_provider.get_source_label(eps_result.get('source', 'miss'))})")
                    for ep_data in eps_list:
                        ep_num = ep_data.get("sort")
                        if ep_num is None: continue
                        
                        mapped_ep = self.mapper.map_episode(ep_data)
                        mapped_ep["season_number"] = actual_target_season
                        
                        ep_filename = f"season-{actual_target_season}-episode-{ep_num}.json"
                        ep_full_path = os.path.join(target_dir, ep_filename)
                        
                        # Support Overwrite logic for Bangumi Recursive
                        ep_curr = {}
                        if os.path.exists(ep_full_path):
                            try:
                                with open(ep_full_path, "r", encoding="utf-8") as f: ep_curr = json.load(f)
                            except: pass
                        
                        if overwrite: ep_curr.update(mapped_ep)
                        else:
                            for k, v in mapped_ep.items():
                                if k not in ep_curr or ep_curr[k] in [None, "", [], {}]: ep_curr[k] = v

                        with open(ep_full_path, "w", encoding="utf-8") as f:
                            json.dump(ep_curr, f, ensure_ascii=False, indent=4)
                except Exception as e:
                    log_audit("元数据", "失败", f"Bangumi 递归失败: {e}", level="ERROR")
        # 6. Refresh
        if trigger_refresh:
            await asyncio.sleep(2)
            refresh_type = "tmdb-tv" if source_item_type in ["tv", "season", "episode"] else "tmdb-movies2"
            await self.emby_service.refresh_item_in_emby(refresh_type, target_tmdb_id)

        return True, "生成成功"

    def _filter_fields_for_type(self, fields: Optional[List[str]], target_type: str) -> Optional[List[str]]:
        """Filter a list of field names to only include those valid for the target type's mapping rules."""
        if not fields:
            return fields
        if target_type not in self.mapping_rules:
            return fields
        valid_keys = set(self.mapping_rules[target_type].keys())
        filtered = [f for f in fields if f in valid_keys]
        skipped = [f for f in fields if f not in valid_keys]
        if skipped:
            log_audit("元数据", "处理", f"字段过滤: 类型 '{target_type}' 跳过不适用字段: {skipped}")
        return filtered

    async def _apply_custom_external_ids(self, item_type: str, tmdb_id: str, target_dir: str, season_number: int = None, episode_number: int = None):
        """
        Apply custom external IDs from external_ids.json to the metadata file.
        This is called after updating metadata from TMDB/Bangumi.
        """
        external_ids_path = os.path.join(target_dir, "external_ids.json")
        
        if not os.path.exists(external_ids_path):
            return
        
        try:
            with open(external_ids_path, 'r', encoding='utf-8') as f:
                external_ids_data = json.load(f)
        except Exception as e:
            log_audit("元数据", "失败", f"读取 external_ids.json 失败: {e}", level="WARN")
            return
        
        # Determine which metadata file to update
        if item_type == "movie":
            target_filename = "all.json"
        elif item_type == "tv":
            target_filename = "series.json"
        elif item_type == "season":
            target_filename = f"season-{season_number}.json"
        elif item_type == "episode":
            target_filename = f"season-{season_number}-episode-{episode_number}.json"
        else:
            return
        
        target_file_path = os.path.join(target_dir, target_filename)
        
        if not os.path.exists(target_file_path):
            return
        
        try:
            with open(target_file_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            log_audit("元数据", "失败", f"读取元数据文件 {target_file_path} 失败: {e}", level="WARN")
            return
        
        # Determine which external IDs to apply
        custom_external_ids = {}
        
        if item_type in ["movie", "tv"]:
            # Apply main item external IDs
            custom_external_ids = external_ids_data.get("external_ids", {})
        elif item_type == "season":
            # Apply season-specific external IDs
            seasons_data = external_ids_data.get("seasons", [])
            for season in seasons_data:
                if season.get("season_number") == season_number:
                    custom_external_ids = season.get("external_ids", {})
                    break
        elif item_type == "episode":
            # Episodes inherit from season (no episode-specific IDs in external_ids.json)
            seasons_data = external_ids_data.get("seasons", [])
            for season in seasons_data:
                if season.get("season_number") == season_number:
                    custom_external_ids = season.get("external_ids", {})
                    break
        
        # Apply custom external IDs to metadata
        if custom_external_ids:
            if "external_ids" not in metadata:
                metadata["external_ids"] = {}
            
            for key, value in custom_external_ids.items():
                if value is not None and value != "":
                    metadata["external_ids"][key] = value
            
            # Save updated metadata
            try:
                with open(target_file_path, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=4)
                log_audit("元数据", "处理", f"已应用自定义外部ID到 {target_file_path}")
            except Exception as e:
                log_audit("元数据", "失败", f"写入元数据文件 {target_file_path} 失败: {e}", level="ERROR")