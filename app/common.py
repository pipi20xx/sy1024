# app/common.py

import logging
import sys
import os
import re
from typing import Dict, Any, List, Tuple, Optional
import base64

from app.logger import init_logging, get_logger, log_audit

# --- 日志配置 ---
log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)

# 初始化日志系统 (如果尚未初始化，由 main.py 优先调用)
root = logging.getLogger()
if not root.handlers:
    init_logging(level=log_level)

logger = get_logger(__name__)

# --- 常量定义 ---
SOURCE_PRIMARY = "primary"
SOURCE_OVERRIDE = "override"
SOURCE_DISPLAY_NAMES = {
    SOURCE_PRIMARY: "主缓存",
    SOURCE_OVERRIDE: "覆盖缓存"
}

APP_CONFIG_FILENAME = "tmdb_browser_config.json"
APP_CACHE_FILENAME = "app_data_cache.json" # 保留以供参考，但不再使用
APP_DB_FILENAME = "items_cache.db" # SQLite数据库文件名

# TMDB 媒体类型键与显示名称的映射
TYPE_DISPLAY_NAMES: Dict[str, str] = {
    "tmdb-tv": "剧集",
    "tmdb-movies2": "电影",
    "tmdb-collections": "合集",
    # "tmdb-actors": "演员" # 暂时不实现演员扫描
}

# 各种媒体类型的主 JSON 文件名
MAIN_JSON_FILENAMES: Dict[str, str] = {
    "tmdb-tv": "series.json",
    "tmdb-movies2": "all.json",
    #"tmdb-collections": "all.json",
}

# Emby 图片命名规则 (用于判断图片文件是否存在)
IMAGE_NAMING_RULES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "series_movie": {
        "poster": {"label": "海报 (Poster)", "files": ["poster.{ext}"]}, # 简化，只保留最常见的 poster.ext
        "fanart": {"label": "背景图 (Fanart)", "files": ["fanart.{ext}"]},
        "banner": {"label": "横幅 (Banner)", "files": ["banner.{ext}"]},
        "logo": {"label": "徽标 (clearlogo)", "files": ["clearlogo.{ext}", "logo.{ext}"]},
        "art": {"label": "艺术图 (clearart)", "files": ["clearart.{ext}", "art.{ext}"]},
        "thumb": {"label": "缩略图 (Landscape)", "files": ["landscape.{ext}", "thumb.{ext}"]},
        "disc": {"label": "光盘图 (Disc)", "files": ["disc.{ext}"]},
    },
    "season": {
        "poster": {"label": "季海报 (Season Poster)", "files": [
            "season-{s_num}.{ext}",
            "season-{s_num_formatted}-poster.{ext}",
            "season-specials-poster.{ext}",
        ]}
    },
    "episode": {
        "thumb": {"label": "剧集截图 (Episode Thumbnail)", "files": [
            "season-{s_num}-episode-{e_num}.{ext}",
            "S{s_num_formatted}E{e_num_formatted}-thumb.{ext}",
            "season{s_num_formatted}-episode{e_num_formatted}-thumb.{ext}",
        ]}
    }
}

# 常用的图片扩展名
COMMON_IMAGE_EXTENSIONS: List[str] = ['jpg', 'jpeg', 'png', 'webp'] # 不带点号，因为规则中 {ext} 不带点

# --- 工具函数 ---
def get_config_path(filename: str) -> str:
    """获取配置文件或缓存文件的绝对路径。优先使用环境变量，否则放当前目录。"""
    data_dir = os.environ.get("DATA_PATH", ".")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)

def sanitize_filename(name_str: Any) -> str:
    """清理字符串，使其适合作为文件名或文件夹名。"""
    if not isinstance(name_str, str):
        name_str = str(name_str)
    # 移除文件名中不允许的字符
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name_str)
    # 移除前后空格和点号
    sanitized = sanitized.strip(". ")
    if not sanitized:
        return "unknown_item"
    return sanitized

def format_date_to_year(date_str: Optional[str]) -> str:
    """从日期字符串中提取年份。"""
    if not date_str:
        return "N/A"
    try:
        # 兼容 YYYY-MM-DD 和 YYYY-MM-DDTHH:MM:SS.ffffffZ 两种格式
        if 'T' in date_str:
            return date_str.split('T')[0].split('-')[0]
        else:
            return date_str.split('-')[0]
    except IndexError:
        return "N/A"

def image_to_base64(image_path: str) -> Optional[str]:
    """
    将图片文件转换为Base64编码的字符串。
    """
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        log_audit("工具", "转换", f"图片转 Base64 成功: {image_path}", level="DEBUG")
        return encoded_string
    except FileNotFoundError:
        log_audit("工具", "转换", f"图片转 Base64 失败: 文件未找到 {image_path}", level="ERROR")
        return None
    except Exception as e:
        log_audit("工具", "转换", f"图片转 Base64 转换错误: {e}", level="ERROR")
        return None

def find_image_files_for_item(item_data: Dict[str, Any], base_folder_path_of_item: str) -> Dict[str, str]:
    """
    根据项目的元数据和命名规则，在指定 base_folder_path_of_item 下的 'images' 子目录中查找图片文件。
    返回一个字典，键为图片类型（如 'poster'），值为完整的文件路径。
    """
    found_images_map: Dict[str, str] = {}
    node_type_display = item_data.get("node_type", "未知") # 例如 "剧集", "电影", "季", "集"

    # 图片所在的实际目录，例如 /primary_cache/tmdb-tv/12345/images
    images_dir_to_search = os.path.join(base_folder_path_of_item, "images")
    if not os.path.isdir(images_dir_to_search):
        return {}

    rules_category_key: str = ""
    season_num_for_rule: int | None = None
    episode_num_for_rule: int | None = None

    # 根据 node_type 确定规则类别和需要的数字
    if node_type_display in ["剧集", "电影", "合集"]:
        rules_category_key = "series_movie"
    elif node_type_display == "季":
        rules_category_key = "season"
        season_num_for_rule = item_data.get("season_number") # TMDB 季号
    elif node_type_display == "集":
        rules_category_key = "episode"
        season_num_for_rule = item_data.get("season_number")
        episode_num_for_rule = item_data.get("episode_number")

    if not rules_category_key or rules_category_key not in IMAGE_NAMING_RULES:
        return {}

    rules_to_apply = IMAGE_NAMING_RULES[rules_category_key]

    for image_type_key, rule_details in rules_to_apply.items():
        if image_type_key in found_images_map: # 已经找到这个类型的图片了
            continue
        
        filename_patterns = rule_details.get("files", [])
        
        for pattern_template in filename_patterns:
            processed_pattern = pattern_template
            valid_substitution = True

            # 替换季号和集号占位符
            if "{s_num}" in processed_pattern or "{s_num_formatted}" in processed_pattern:
                if season_num_for_rule is None or not isinstance(season_num_for_rule, int):
                    valid_substitution = False
                else:
                    processed_pattern = processed_pattern.replace("{s_num_formatted}", f"{season_num_for_rule:02d}")
                    processed_pattern = processed_pattern.replace("{s_num}", str(season_num_for_rule))
            
            if "{e_num}" in processed_pattern or "{e_num_formatted}" in processed_pattern:
                if episode_num_for_rule is None or not isinstance(episode_num_for_rule, int):
                    valid_substitution = False
                else:
                    processed_pattern = processed_pattern.replace("{e_num_formatted}", f"{episode_num_for_rule:03d}")
                    processed_pattern = processed_pattern.replace("{e_num}", str(episode_num_for_rule))
            
            # 特殊处理：season-specials-poster (0代表特别篇)
            if "season-specials-poster" in processed_pattern and (season_num_for_rule is None or season_num_for_rule != 0):
                valid_substitution = False

            if not valid_substitution:
                continue # 如果任何一个必要的替换值无效，则跳过当前这个 filename_pattern

            for ext in COMMON_IMAGE_EXTENSIONS: # 遍历所有可能的扩展名
                final_filename_with_ext = processed_pattern.replace("{ext}", ext)
                full_image_path = os.path.join(images_dir_to_search, final_filename_with_ext)
                
                if os.path.exists(full_image_path) and os.path.isfile(full_image_path):
                    found_images_map[image_type_key] = full_image_path
                    break # 找到第一个就够了，跳到下一个图片类型
            
            if image_type_key in found_images_map:
                break # 找到了这个类型的图片，跳到下一个图片类型

    return found_images_map


# app/common.py (在文件末尾追加)


# --- Patches 深度合并工具函数 ---

def deep_merge_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 patch 字典深度合并到 base 字典中并返回 base。
    - 对于 dict 类型的值，递归合并
    - 对于其他类型（str, int, list, bool 等），patch 的值直接覆盖 base 的值
    - 不修改原始 patch 字典
    """
    for key, patch_val in patch.items():
        if key in base and isinstance(base[key], dict) and isinstance(patch_val, dict):
            deep_merge_dict(base[key], patch_val)
        else:
            base[key] = patch_val
    return base


# --- 新增: 固定的静态类型列表 ---
# 基于用户提供的列表，用于前端筛选器
STATIC_GENRES: List[str] = sorted([
    "动作", "冒险", "动画", "喜剧", "犯罪", "纪录", "剧情", "家庭", "奇幻", 
    "历史", "恐怖", "音乐", "悬疑", "爱情", "科幻", "电视电影", "惊悚", 
    "战争", "西部", "动作冒险", "儿童", "新闻", "真人秀", "科幻奇幻", 
    "肥皂剧", "脱口秀", "战争政治"
])
