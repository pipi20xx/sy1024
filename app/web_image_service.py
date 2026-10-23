# app/web_image_service.py

import requests
import os  # <-- [核心修正] 添加这一行，导入 os 模块
from typing import Dict, Any, List, Tuple, Union, Optional

from app.logger import log_audit

class WebImageService:
    """
    一个专门用于从外部网络源 (如 TMDb, Fanart.tv) 获取和下载图片的服务。
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化服务，需要传入应用的主配置以获取API Key。
        """
        self.config = config
        self.session = requests.Session()

    def _get_proxies(self, target: str):
        # 动态从当前配置中解析代理，不依赖全局单例防止初始化顺序问题
        network_config = self.config.get("network", {})
        if network_config.get("enable_global") and network_config.get("proxy_url"):
            targets = network_config.get("proxy_targets", {})
            if targets.get(target):
                proxy_url = network_config.get("proxy_url")
                log_audit("图片", "代理", f"{target} 请求将通过代理: {proxy_url}")
                return {"http": proxy_url, "https": proxy_url}
        return None

    def _parse_fanart_data(self, data: Dict[str, Any], image_list: List[Dict], requested_types: List[str]):
        """
        解析来自 Fanart.tv 的API响应，并根据请求的类型进行筛选。
        """
        # --- [核心修正] 更新了这个字典，加入了从日志中看到的正确名称 ---
        fanart_map = {
            # 电影相关的键
            "movieposter": "poster",
            "moviebackground": "fanart",
            "hdmovielogo": "logo",
            "hdmovieclearart": "clearart",
            "moviebanner": "banner",
            "moviethumb": "thumb",
            "moviedisc": "disc",
            # 电视剧相关的键 (根据您的日志进行了修正和补充)
            "tvposter": "poster",       # <-- 新增：这解决了海报不显示的问题
            "showbackground": "fanart",
            "hdtvlogo": "logo",
            "hdclearart": "clearart",
            "tvbanner": "banner",
            "tvthumb": "thumb",
            # 为了兼容性保留的旧键名
            "seriesposter": "poster",
            "clearlogo": "logo",
            "clearart": "clearart",
        }
        show_all = not requested_types

        for api_type, images in data.items():
            if isinstance(images, list) and api_type in fanart_map:
                std_type = fanart_map[api_type]
                if show_all or std_type in requested_types:
                    for image in images:
                        image_list.append({
                            "full_url": image.get('url'),
                            "preview_url": image.get('url', '').replace('/fanart/', '/preview/'),
                            "type": std_type,
                            "source": "Fanart.tv",
                            "info": f"赞: {image.get('likes', 'N/A')}",
                            "lang": image.get('lang', 'N/A')
                        })

    def _parse_tmdb_data(self, data: Dict[str, Any], image_list: List[Dict], requested_types: List[str]):
        """
        解析来自 TMDb 的API响应，并根据请求的类型进行筛选。
        """
        base_url = "https://image.tmdb.org/t/p/original"
        preview_url_base = "https://image.tmdb.org/t/p/w500"
        type_map = {"backdrops": "fanart", "logos": "logo", "posters": "poster"}
        show_all = not requested_types

        for api_type, images in data.items():
            if api_type in type_map:
                std_type = type_map[api_type]
                if show_all or std_type in requested_types:
                    for image in images:
                        image_list.append({
                            "full_url": f"{base_url}{image['file_path']}",
                            "preview_url": f"{preview_url_base}{image['file_path']}",
                            "type": std_type,
                            "source": "TMDb",
                            "info": f"评分: {image.get('vote_average', 0):.1f}",
                            "lang": image.get('iso_639_1', 'N/A')
                        })

    def _parse_tmdb_season_data(self, data: Dict[str, Any], image_list: List[Dict], requested_types: List[str]):
        """
        解析来自 TMDb 季度图片 API 的响应。
        TMDB 季度图片返回 posters, backdrops, logos。
        """
        base_url = "https://image.tmdb.org/t/p/original"
        preview_url_base = "https://image.tmdb.org/t/p/w500"
        type_map = {"posters": "poster", "backdrops": "fanart", "logos": "logo"}
        show_all = not requested_types

        for api_type, images in data.items():
            if api_type in type_map and isinstance(images, list):
                std_type = type_map[api_type]
                if show_all or std_type in requested_types:
                    for image in images:
                        image_list.append({
                            "full_url": f"{base_url}{image['file_path']}",
                            "preview_url": f"{preview_url_base}{image['file_path']}",
                            "type": std_type,
                            "source": "TMDb",
                            "info": f"评分: {image.get('vote_average', 0):.1f}",
                            "lang": image.get('iso_639_1', 'N/A')
                        })

    def _parse_tmdb_episode_data(self, data: Dict[str, Any], image_list: List[Dict], requested_types: List[str]):
        """
        解析来自 TMDb 集图片 API 的响应。
        TMDB 集图片返回 stills。
        """
        base_url = "https://image.tmdb.org/t/p/original"
        preview_url_base = "https://image.tmdb.org/t/p/w500"
        type_map = {"stills": "thumb"}
        show_all = not requested_types

        for api_type, images in data.items():
            if api_type in type_map and isinstance(images, list):
                std_type = type_map[api_type]
                if show_all or std_type in requested_types:
                    for image in images:
                        image_list.append({
                            "full_url": f"{base_url}{image['file_path']}",
                            "preview_url": f"{preview_url_base}{image['file_path']}",
                            "type": std_type,
                            "source": "TMDb",
                            "info": f"评分: {image.get('vote_average', 0):.1f}",
                            "lang": image.get('iso_639_1', 'N/A')
                        })

    def _fetch_tvdb_id_from_tmdb_api(self, tmdb_id: str) -> Optional[str]:
        """
        当本地没有TVDB ID时，通过TMDB API获取。
        """
        tmdb_key = self.config.get("tmdb_api_key")
        if not tmdb_key:
            log_audit("图片", "查询", "无法从API获取TVDB ID，TMDb API Key未配置", level="WARN")
            return None

        try:
            log_audit("图片", "查询", f"正在通过 TMDB API 为 {tmdb_id} 查询 external_ids")
            url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids?api_key={tmdb_key}"
            response = self.session.get(url, timeout=10, proxies=self._get_proxies('tmdb'))
            response.raise_for_status()
            data = response.json()
            tvdb_id = data.get("tvdb_id")
            if tvdb_id:
                log_audit("图片", "查询", f"通过 API 成功获取到 TVDB ID: {tvdb_id}", level="SUCCESS")
                return str(tvdb_id)
            else:
                log_audit("图片", "查询", "TMDB API 的 external_ids 响应中不包含 tvdb_id", level="WARN")
                return None
        except requests.RequestException as e:
            log_audit("图片", "查询", f"通过 TMDB API 获取 external_ids 失败: {e}", level="ERROR")
            return None


    def get_available_images(self, item_type: str, item_id: str, image_types: List[str] = None, tvdb_id: Optional[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        fanart_key = self.config.get("fanart_api_key")
        tmdb_key = self.config.get("tmdb_api_key")

        # Default to all sources if not specified
        enabled_sources = sources or ['fanart', 'tmdb']
        
        # Filter sources based on available keys
        valid_sources = []
        for source in enabled_sources:
            if source == 'fanart':
                if fanart_key:
                    valid_sources.append('fanart')
                else:
                    log_audit("图片", "查询", "未配置 Fanart.tv API Key，跳过 Fanart 源", level="WARN")
            elif source == 'tmdb':
                if tmdb_key:
                    valid_sources.append('tmdb')
                else:
                    log_audit("图片", "查询", "未配置 TMDb API Key，跳过 TMDb 源", level="WARN")
        
        enabled_sources = valid_sources

        if not enabled_sources:
            return False, "所选图片源的 API Key 均未配置，请检查设置。"

        all_images = []
        requested_types_list = image_types or []

        fanart_id_to_use = None
        if item_type == "tmdb-movies2":
            fanart_id_to_use = item_id
        elif item_type == "tmdb-tv":
            final_tvdb_id = tvdb_id
            if not final_tvdb_id:
                final_tvdb_id = self._fetch_tvdb_id_from_tmdb_api(item_id)
            fanart_id_to_use = final_tvdb_id
        
        # --- Fanart.tv Source ---
        if 'fanart' in enabled_sources:
            if fanart_id_to_use:
                api_media_type = 'movies' if item_type == "tmdb-movies2" else 'tv'
                try:
                    log_audit("图片", "获取", f"正在为 Fanart ID {fanart_id_to_use} 从 Fanart.tv 获取图片")
                    fanart_url = f"http://webservice.fanart.tv/v3/{api_media_type}/{fanart_id_to_use}?api_key={fanart_key}"
                    response = self.session.get(fanart_url, timeout=15, proxies=self._get_proxies('fanart'))
                    if response.status_code != 404:
                        response.raise_for_status()
                        # --- [核心修正] 添加日志，打印从Fanart获取到的原始数据 ---
                        fanart_data = response.json()
                        log_audit("图片", "获取", f"从 Fanart.tv 收到的原始数据: {fanart_data}", level="DEBUG")
                        self._parse_fanart_data(fanart_data, all_images, requested_types_list)
                    else:
                        log_audit("图片", "获取", f"在 Fanart.tv 中未找到 ID: {fanart_id_to_use} 的条目", level="WARN")
                except Exception as e: # 使用更宽泛的Exception来捕获可能的JSON解码错误
                    log_audit("图片", "获取", f"获取或解析 Fanart.tv 数据时发生错误: {e}", level="WARN")
            else:
                if item_type == "tmdb-tv":
                    log_audit("图片", "获取", f"无法为电视剧 {item_id} 找到TVDB ID，将跳过Fanart.tv的查询", level="WARN")

        # --- TMDb Source ---
        if 'tmdb' in enabled_sources:
            try:
                log_audit("图片", "获取", f"正在为 TMDB ID {item_id} 从 TMDb 获取图片")
                tmdb_api_type = 'movie' if item_type == "tmdb-movies2" else 'tv'
                tmdb_url = f"https://api.themoviedb.org/3/{tmdb_api_type}/{item_id}/images?api_key={tmdb_key}"
                response = self.session.get(tmdb_url, timeout=15, proxies=self._get_proxies('tmdb'))
                response.raise_for_status()
                self._parse_tmdb_data(response.json(), all_images, requested_types_list)
            except requests.RequestException as e:
                log_audit("图片", "获取", f"获取 TMDb 数据时发生严重错误: {e}", level="ERROR")
                # Don't return failure immediately if Fanart succeeded, just log it
                if not all_images:
                     return False, f"获取 TMDb 数据失败: {e}"

        if not all_images:
            return False, "在所有已配置且选定的图片源中，均未找到任何图片。"
        
        log_audit("图片", "获取", f"共为项目 {item_id} 找到 {len(all_images)} 张网络图片", level="SUCCESS")
        return True, all_images

    def get_available_season_images(self, series_id: str, season_number: int, image_types: List[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        """
        从 TMDb 获取指定季度的图片（主要是海报）。
        Fanart.tv 不支持季度级别的图片，因此只查 TMDB。
        """
        tmdb_key = self.config.get("tmdb_api_key")
        if not tmdb_key:
            return False, "TMDb API Key 未配置，无法获取季度图片。"

        # TMDB is the only source for season images
        enabled_sources = sources or ['tmdb']
        if 'tmdb' not in enabled_sources:
            return False, "季度图片仅支持从 TMDb 获取。"

        all_images = []
        requested_types_list = image_types or ['poster']

        try:
            log_audit("图片", "获取", f"正在为剧集 {series_id} 第 {season_number} 季从 TMDb 获取图片")
            tmdb_url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/images?api_key={tmdb_key}"
            response = self.session.get(tmdb_url, timeout=15, proxies=self._get_proxies('tmdb'))
            response.raise_for_status()
            self._parse_tmdb_season_data(response.json(), all_images, requested_types_list)
        except requests.RequestException as e:
            log_audit("图片", "获取", f"获取 TMDb 季度图片时发生错误: {e}", level="ERROR")
            return False, f"获取 TMDb 季度图片失败: {e}"

        if not all_images:
            return False, "未找到任何季度图片。"

        log_audit("图片", "获取", f"共为剧集 {series_id} 第 {season_number} 季找到 {len(all_images)} 张网络图片", level="SUCCESS")
        return True, all_images

    def get_available_episode_images(self, series_id: str, season_number: int, episode_number: int, image_types: List[str] = None, sources: List[str] = None) -> Tuple[bool, Union[List[Dict], str]]:
        """
        从 TMDb 获取指定集的图片（主要是剧照 stills）。
        Fanart.tv 不支持集级别的图片，因此只查 TMDB。
        """
        tmdb_key = self.config.get("tmdb_api_key")
        if not tmdb_key:
            return False, "TMDb API Key 未配置，无法获取集图片。"

        enabled_sources = sources or ['tmdb']
        if 'tmdb' not in enabled_sources:
            return False, "集图片仅支持从 TMDb 获取。"

        all_images = []
        requested_types_list = image_types or ['thumb']

        try:
            log_audit("图片", "获取", f"正在为剧集 {series_id} S{season_number}E{episode_number} 从 TMDb 获取图片")
            tmdb_url = f"https://api.themoviedb.org/3/tv/{series_id}/season/{season_number}/episode/{episode_number}/images?api_key={tmdb_key}"
            response = self.session.get(tmdb_url, timeout=15, proxies=self._get_proxies('tmdb'))
            response.raise_for_status()
            self._parse_tmdb_episode_data(response.json(), all_images, requested_types_list)
        except requests.RequestException as e:
            log_audit("图片", "获取", f"获取 TMDb 集图片时发生错误: {e}", level="ERROR")
            return False, f"获取 TMDb 集图片失败: {e}"

        if not all_images:
            return False, "未找到任何集图片。"

        log_audit("图片", "获取", f"共为剧集 {series_id} S{season_number}E{episode_number} 找到 {len(all_images)} 张网络图片", level="SUCCESS")
        return True, all_images

    def download_image(self, image_url: str, save_path: str) -> Tuple[bool, str]:
        """
        从给定的URL下载一张图片并保存到本地。
        """
        try:
            # 现在 os 已经被导入，这行代码可以正常工作了
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            target = 'tmdb' if 'tmdb.org' in image_url else 'fanart'
            proxies = self._get_proxies(target)
            
            log_audit("图片", "下载", f"正在从 {image_url} 下载图片 (target: {target})")
            response = self.session.get(image_url, stream=True, timeout=30, proxies=proxies)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            log_audit("图片", "下载", f"图片已成功保存到: {save_path}", level="SUCCESS")
            return True, f"成功保存 {os.path.basename(save_path)}。"

        except requests.RequestException as e:
            log_audit("图片", "下载", f"下载图片时发生网络错误 {image_url}: {e}", level="ERROR")
            return False, f"下载失败: {e}"
        except IOError as e:
            log_audit("图片", "下载", f"保存文件时发生IO错误 {save_path}: {e}", level="ERROR")
            return False, f"保存文件失败: {e}"