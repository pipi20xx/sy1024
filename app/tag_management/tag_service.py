# app/tag_management/tag_service.py

import os
import json
import uuid
from typing import Dict, Any, Tuple, Union, Optional, List

from ..common import get_config_path, MAIN_JSON_FILENAMES, SOURCE_OVERRIDE
from ..services import SystemService
from .constants import COUNTRY_CODE_MAP, LANG_TO_COUNTRY_MAP, GENRE_ID_MAP

class TagService:
    def __init__(self, system_service: SystemService):
        """
        Initializes the TagService.
        :param system_service: An instance of SystemService to access shared resources like file paths.
        """
        self.system_service = system_service
        # 配置文件路径指向 data/ 目录
        self.custom_tags_config_path = os.path.join(get_config_path(""), "custom_tags.json")
        self.tag_rules_path = os.path.join(get_config_path(""), "tag_rules.json")
    async def get_tag_editor_info(self, item_type: str, item_id: str) -> Tuple[bool, Union[Dict, str]]:
        """
        Gathers all necessary information for the tag editor UI.
        It reads production countries and genres from the item's metadata
        and loads the globally saved custom tag combinations.
        """
        main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_filename:
            return False, f"不支持的项目类型: {item_type}"

        json_path = self.system_service.editor_service._get_actual_json_path(item_type, item_id, main_json_filename)
        if not json_path:
            return False, "无法找到该项目的元数据文件。"

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"读取元数据文件失败: {e}"

        # Extract countries and genres
        countries = sorted(list(set(c.get("iso_3166_1") for c in metadata.get("production_countries", []) if c.get("iso_3166_1"))))
        genres = sorted(list(set(g.get("name") for g in metadata.get("genres", []) if g.get("name"))))

        # Load custom tag combinations
        custom_tags = self._load_custom_tags()
        
        # Automatically determine the region tag
        determined_region = self._determine_region_tag(item_type, metadata)

        return True, {
            "available_countries": countries,
            "available_genres": genres,
            "custom_tag_presets": custom_tags,
            "determined_region": determined_region
        }

    def _determine_region_tag(self, item_type: str, data: Dict) -> Optional[str]:
        """
        Determines the region tag based on the item's metadata using the logic
        from the provided desktop script.
        """
        country_tag = None
        if item_type == 'tmdb-tv':
            if data.get('origin_country') and isinstance(data.get('origin_country'), list) and data['origin_country']:
                country_code = data['origin_country'][0]
                country_tag = COUNTRY_CODE_MAP.get(country_code)
            if not country_tag and data.get('languages') and isinstance(data.get('languages'), list) and data['languages']:
                lang_code = data['languages'][0]
                country_code = LANG_TO_COUNTRY_MAP.get(lang_code)
                if country_code:
                    country_tag = COUNTRY_CODE_MAP.get(country_code)
        elif item_type == 'tmdb-movies2':
            if data.get('original_language'):
                lang_code = data.get('original_language')
                country_code = LANG_TO_COUNTRY_MAP.get(lang_code)
                if country_code:
                    country_tag = COUNTRY_CODE_MAP.get(country_code)
            if not country_tag and data.get('production_countries') and isinstance(data.get('production_countries'), list) and data['production_countries']:
                country_code = data['production_countries'][0].get('iso_3166_1')
                if country_code:
                    country_tag = COUNTRY_CODE_MAP.get(country_code)
            if not country_tag and data.get('spoken_languages') and isinstance(data.get('spoken_languages'), list) and data['spoken_languages']:
                lang_code = data['spoken_languages'][0].get('iso_639_1')
                if lang_code:
                    country_code = LANG_TO_COUNTRY_MAP.get(lang_code)
                    if country_code:
                        country_tag = COUNTRY_CODE_MAP.get(country_code)
            if not country_tag and data.get('production_companies') and isinstance(data.get('production_companies'), list):
                for company in data['production_companies']:
                    if isinstance(company, dict) and company.get('origin_country'):
                        country_code = company['origin_country']
                        country_tag = COUNTRY_CODE_MAP.get(country_code)
                        if country_tag:
                            break
        return country_tag

    def _load_custom_tags(self) -> Dict:
        """Loads the custom tags configuration file."""
        if not os.path.exists(self.custom_tags_config_path):
            return {}
        try:
            with open(self.custom_tags_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    def save_custom_tags(self, tags_data: Dict) -> Tuple[bool, str]:
        """Saves the custom tags configuration file."""
        try:
            with open(self.custom_tags_config_path, "w", encoding="utf-8") as f:
                json.dump(tags_data, f, indent=2, ensure_ascii=False)
            return True, "自定义标签预设保存成功。"
        except IOError as e:
            return False, f"保存自定义标签失败: {e}"

    async def generate_and_save_item_tag(self, item_type: str, item_id: str, mode: str = 'merge') -> Tuple[bool, str]:
        """
        Generates tags based on region and rules, then saves them to the item's
        tags.json file according to the specified mode ('merge' or 'overwrite').
        """
        main_json_filename = MAIN_JSON_FILENAMES.get(item_type)
        if not main_json_filename:
            return False, f"Unsupported item type: {item_type}"

        # [Fixed] Access EditorService
        json_path = self.system_service.editor_service._get_actual_json_path(item_type, item_id, main_json_filename)
        if not json_path:
            return False, "Could not find the metadata file for the item."

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as e:
            return False, f"Failed to read metadata file: {e}"

        # 步骤1: 根据地区信息生成标签 (用户要求移除此默认行为)
        # region_tag = self._determine_region_tag(item_type, metadata)
        
        # 步骤2: 根据自定义规则生成标签
        rule_based_tags = self._apply_tag_rules(item_type, metadata)

        # 合并所有需要添加的标签，并去重
        tags_to_add = []
        # if region_tag: # 用户要求移除此默认行为
        #     tags_to_add.append(region_tag)
        tags_to_add.extend(rule_based_tags)
        
        if not tags_to_add:
            return False, "未根据规则为此项目确定任何标签。请检查您的标签规则或项目元数据。" # [修改] 提示信息

        # 无论元数据是从 primary 还是 override 目录读取，生成的标签都必须写入 override 目录。
        # [Fixed] Access ConfigurationService
        override_root_path = self.system_service.configuration_service.get_cache_path_for_source("override")
        if not override_root_path:
            return False, "未配置覆盖缓存目录。"

        actual_item_folder = os.path.basename(os.path.dirname(json_path))
        item_override_folder_path = os.path.join(override_root_path, item_type, actual_item_folder)
        os.makedirs(item_override_folder_path, exist_ok=True)
        tags_json_path = os.path.join(item_override_folder_path, 'tags.json')
        
        # 根据模式决定最终的标签列表
        final_tags = []
        unique_tags_to_add = sorted(list(set(tags_to_add)))

        if mode == 'overwrite':
            final_tags = unique_tags_to_add
            action_message = f"成功覆盖了 {len(final_tags)} 个标签。"
        else:  # 默认为 'merge'
            existing_tags = []
            if os.path.exists(tags_json_path):
                try:
                    with open(tags_json_path, 'r', encoding='utf-8') as f:
                        tags_data = json.load(f)
                        if "tags" in tags_data and isinstance(tags_data.get("tags"), list):
                            existing_tags = tags_data["tags"]
                except (json.JSONDecodeError, IOError):
                    pass  # 文件损坏则视为空

            # 合并并去重
            final_tags = sorted(list(set(existing_tags + unique_tags_to_add)))
            added_count = len(final_tags) - len(existing_tags)
            if added_count == 0 and len(unique_tags_to_add) > 0:
                action_message = "所有识别出的标签均已存在。"
            else:
                action_message = f"成功合并，新增了 {added_count} 个标签。"


        # 写回更新后的 tags.json
        try:
            with open(tags_json_path, 'w', encoding="utf-8") as f:
                json.dump({"tags": final_tags}, f, ensure_ascii=False, indent=2)
            # [Fixed] Await ScannerService call
            await self.system_service.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, action_message
        except Exception as e:
            return False, f"写入 tags.json 失败: {e}"

    def _apply_tag_rules(self, item_type: str, data: Dict) -> List[str]:
        """
        Applies the custom tag rules to the item's metadata and returns a list of matching tags.
        """
        rules = self._load_rules()
        if not rules:
            return []

        # 转换 item_type 以匹配规则中的 'movie' 或 'tv'
        media_type_for_rule = 'movie' if item_type == 'tmdb-movies2' else 'tv' if item_type == 'tmdb-tv' else None

        # 提取元数据中的国家和类型ID
        item_countries = {c.get("iso_3166_1") for c in data.get("production_countries", []) if c.get("iso_3166_1")}
        # 对于电视剧，也检查 origin_country
        if media_type_for_rule == 'tv' and data.get('origin_country'):
            item_countries.update(data.get('origin_country', []))
            
        item_genre_ids = {g.get("id") for g in data.get("genres", []) if g.get("id")}
        
        # 提取年份信息
        item_year = None
        if item_type == 'tmdb-movies2':
            release_date = data.get('release_date')
            if release_date and len(release_date) >= 4:
                item_year = int(release_date[:4])
        elif item_type == 'tmdb-tv':
            first_air_date = data.get('first_air_date')
            if first_air_date and len(first_air_date) >= 4:
                item_year = int(first_air_date[:4])

        matched_tags = []
        for rule in rules:
            # 检查媒体类型是否匹配
            if rule.get("media_type") != "all" and rule.get("media_type") != media_type_for_rule:
                continue

            # 收集所有匹配条件
            conditions_met = []
            
            # 国家/地区条件
            rule_countries = set(rule.get("countries", []))
            country_match = not rule_countries or bool(item_countries.intersection(rule_countries))
            conditions_met.append(country_match)

            # 类型条件
            rule_genres = set(rule.get("genres", []))
            genre_match = not rule_genres or bool(item_genre_ids.intersection(rule_genres))
            conditions_met.append(genre_match)
            
            # 年份条件
            rule_year = rule.get("year")
            year_match = True
            if rule_year:
                if item_year is None:
                    year_match = False # 如果规则有年份要求但项目没有年份，则不匹配
                elif isinstance(rule_year, int):
                    year_match = (item_year == rule_year)
                elif isinstance(rule_year, str) and '-' in rule_year:
                    try:
                        start_year, end_year = map(int, rule_year.split('-'))
                        year_match = (start_year <= item_year <= end_year)
                    except ValueError:
                        year_match = False # 解析失败则不匹配
                elif isinstance(rule_year, list): # 支持年份列表
                    year_match = (item_year in rule_year)
                else:
                    year_match = False # 未知年份格式

            conditions_met.append(year_match)

            # 检查严格匹配或模糊匹配
            strict_match_enabled = rule.get("strict_match", False)
            negative_match_enabled = rule.get("negative_match", False) # 新增：负向匹配

            rule_matches = False # 规则是否匹配的最终判断

            if strict_match_enabled:
                # 严格匹配：所有在规则中定义的条件都必须完全匹配
                all_strict_conditions_met = True

                # 检查国家/地区严格匹配
                if rule_countries: # 如果规则定义了国家
                    # [修改] 媒体的国家必须包含规则中定义的所有国家 (Superset check)
                    if not rule_countries.issubset(item_countries):
                        all_strict_conditions_met = False
                
                # 检查类型严格匹配
                if rule_genres: # 如果规则定义了类型
                    # [修改] 媒体的类型必须包含规则中定义的所有类型 (Superset check)
                    if not rule_genres.issubset(item_genre_ids):
                        all_strict_conditions_met = False
                
                # 检查年份严格匹配
                if rule_year: # 如果规则定义了年份
                    if not year_match: # 年份必须完全匹配
                        all_strict_conditions_met = False
                
                # 如果规则中没有任何条件被定义，则不匹配（避免空规则匹配所有项）
                if not (rule_countries or rule_genres or rule_year):
                    all_strict_conditions_met = False

                rule_matches = all_strict_conditions_met
            else:
                # 模糊匹配：所有在规则中定义的条件都必须满足
                all_conditions_met_for_fuzzy = True
                if rule_countries and not country_match:
                    all_conditions_met_for_fuzzy = False
                if rule_genres and not genre_match:
                    all_conditions_met_for_fuzzy = False
                if rule_year and not year_match:
                    all_conditions_met_for_fuzzy = False
                
                # 检查是否有任何条件被定义，避免空规则匹配所有项
                has_defined_condition = bool(rule_countries) or bool(rule_genres) or bool(rule_year)
                if not has_defined_condition:
                    all_conditions_met_for_fuzzy = False

                rule_matches = all_conditions_met_for_fuzzy
            
            # 根据负向匹配模式反转结果
            if negative_match_enabled:
                rule_matches = not rule_matches

            if rule_matches:
                matched_tags.append(rule["tag"])
            
        return list(set(matched_tags)) # 返回去重后的标签列表

    # --- Tag Rules Management ---

    def _load_rules(self) -> List[Dict]:
        if not os.path.exists(self.tag_rules_path):
            return []
        try:
            with open(self.tag_rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_rules(self, rules: List[Dict]):
        with open(self.tag_rules_path, "w", encoding="utf-8") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)

    def get_all_rules(self) -> List[Dict]:
        return self._load_rules()

    def create_rule(self, rule_data: Dict) -> Dict:
        rules = self._load_rules()
        rule_data['id'] = str(uuid.uuid4())
        rules.append(rule_data)
        self._save_rules(rules)
        return rule_data

    def update_rule(self, rule_id: str, rule_data: Dict) -> Optional[Dict]:
        rules = self._load_rules()
        for i, rule in enumerate(rules):
            if rule.get('id') == rule_id:
                rule_data['id'] = rule_id
                rules[i] = rule_data
                self._save_rules(rules)
                return rule_data
        return None

    def delete_rule(self, rule_id: str) -> bool:
        rules = self._load_rules()
        original_length = len(rules)
        rules = [rule for rule in rules if rule.get('id') != rule_id]
        if len(rules) < original_length:
            self._save_rules(rules)
            return True
        return False

    def _get_tags_json_path(self, item_type: str, item_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Helper to get the path to tags.json, ensuring override directory exists."""
        # [Fixed] Access ConfigurationService
        override_path = self.system_service.configuration_service.get_cache_path_for_source("override")
        if not override_path:
            return None, "错误：未配置覆盖缓存目录。"
        
        item_folder = os.path.join(override_path, item_type, item_id)
        os.makedirs(item_folder, exist_ok=True)
        return os.path.join(item_folder, "tags.json"), None

    async def add_tags_to_item(self, item_type: str, item_id: str, tags_to_add: Optional[List[str]] = None, mode: str = 'merge') -> Tuple[bool, str]:
        """
        向项目的 tags.json 文件中添加一个或多个标签。
        如果 tags_to_add 为空或未提供，则根据规则自动生成标签。
        """
        if not tags_to_add:
            # 如果没有提供标签，则调用 generate_and_save_item_tag 来自动生成标签
            return await self.generate_and_save_item_tag(item_type, item_id, mode)

        tags_json_path, error = self._get_tags_json_path(item_type, item_id)
        if error:
            return False, error

        existing_tags = []
        if os.path.isfile(tags_json_path):
            try:
                with open(tags_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data.get("tags"), list):
                        existing_tags = data["tags"]
            except (json.JSONDecodeError, IOError):
                pass

        if mode == 'overwrite':
            final_tags = sorted(list(set(tags_to_add)))
            message = f"成功覆盖 {len(final_tags)} 个标签。"
        else:  # 'merge'
            initial_count = len(existing_tags)
            final_tags = sorted(list(set(existing_tags + tags_to_add)))
            message = f"成功添加 {len(final_tags) - initial_count} 个标签。"
        
        try:
            with open(tags_json_path, "w", encoding="utf-8") as f:
                json.dump({"tags": final_tags}, f, indent=2, ensure_ascii=False)
            # [Fixed] Access ScannerService
            await self.system_service.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, message
        except IOError as e:
            return False, f"写入标签文件时发生错误: {e}"

    async def delete_tags_from_item(self, item_type: str, item_id: str, tags_to_delete: List[str]) -> Tuple[bool, str]:
        """从项目的 tags.json 文件中删除一个或多个标签。如果 tags_to_delete 为空，则删除所有标签。"""
        tags_json_path, error = self._get_tags_json_path(item_type, item_id)
        if error:
            return False, error

        if not os.path.isfile(tags_json_path):
            return True, "标签文件不存在，无需删除。"

        if not tags_to_delete:  # 如果列表为空，则删除所有标签
            return await self.delete_item_tags(item_type, item_id)

        existing_tags = []
        try:
            with open(tags_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("tags"), list):
                    existing_tags = data["tags"]
        except (json.JSONDecodeError, IOError):
            return False, "无法读取或解析现有的标签文件。"

        tags_to_delete_set = set(tags_to_delete)
        final_tags = [tag for tag in existing_tags if tag not in tags_to_delete_set]
        
        try:
            with open(tags_json_path, "w", encoding="utf-8") as f:
                json.dump({"tags": final_tags}, f, indent=2, ensure_ascii=False)
            # [Fixed] Access ScannerService
            await self.system_service.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, f"成功删除 {len(existing_tags) - len(final_tags)} 个标签。"
        except IOError as e:
            return False, f"写入标签文件时发生错误: {e}"

    async def delete_item_tags(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        """删除特定项目的 tags.json 文件。"""
        tags_json_path, error = self._get_tags_json_path(item_type, item_id)
        if error:
            return False, error

        if not os.path.isfile(tags_json_path):
            return True, "标签文件未找到，无需删除。"

        try:
            os.remove(tags_json_path)
            # [Fixed] Access ScannerService
            await self.system_service.scanner_service._refresh_item_in_db(item_type, item_id)
            return True, "标签文件已成功删除。"
        except OSError as e:
            return False, f"删除标签文件时发生错误: {e}"