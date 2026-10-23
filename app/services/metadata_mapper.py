import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class MetadataMapper:
    """
    Responsible for mapping Bangumi JSON data to the internal dictionary format.
    Refers to app/definitions/tmdb_mapping.json for target structure.
    """
    
    def map_subject(self, bgm_data: Dict[str, Any], target_type: str = 'Movie', characters_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Maps Bangumi V0 Subject JSON to internal metadata format.
        :param bgm_data: The JSON data from Bangumi API
        :param target_type: 'Movie' or 'Series' (determines field names)
        :param characters_data: Optional character list from Bangumi v0 API
        """
        if not bgm_data:
            return {}

        mapped = {}
        
        # 1. Basic Fields - Strict separation based on target_type
        # Bangumi 'name' is usually original name, 'name_cn' is localized
        original_title_val = bgm_data.get('name', '')
        localized_title_val = bgm_data.get('name_cn') or bgm_data.get('name', '')
        date_val = bgm_data.get('date', '')
        
        if target_type == 'Movie':
            mapped['original_title'] = original_title_val
            mapped['title'] = localized_title_val
            mapped['release_date'] = date_val
        else:
            # Assume Series/TV for anything else
            mapped['original_name'] = original_title_val
            mapped['name'] = localized_title_val
            mapped['first_air_date'] = date_val
            
        # Clean up overview: normalize newlines and strip whitespace
        raw_summary = bgm_data.get('summary', '') or ''
        mapped['overview'] = raw_summary.replace('\r\n', '\n').strip()
        mapped['status'] = 'Released' # Default
        
        # 2. Infobox Parsing
        infobox = bgm_data.get('infobox', [])
        info_dict = self._parse_infobox(infobox)
        
        # 3. Crew / Cast
        credits_data = {"cast": [], "crew": []}
        
        # Crew Mapping
        # Mapping Bangumi keys to TMDB-like Job titles
        crew_jobs = {
            "导演": "Director",
            "监督": "Director",
            "脚本": "Writer",
            "系列构成": "Writer",
            "原作": "Original Concept",
            "音乐": "Original Music Composer",
            "人物设定": "Character Designer",
            "动画制作": "Animation Production",
            "美术监督": "Art Direction",
            "摄影监督": "Director of Photography",
            "音响监督": "Sound Director"
        }
        
        for key, value in info_dict.items():
            if key in crew_jobs:
                job = crew_jobs[key]
                names = value if isinstance(value, list) else [value]
                for name in names:
                    credits_data['crew'].append({
                        "name": name,
                        "job": job,
                        "department": "Production"
                    })

        # --- Cast Mapping (Actors/Seiyuu) ---
        if characters_data:
            credits_data['cast'] = self.map_characters(characters_data)
        else:
            # Fallback to infobox matching if no character data provided
            cast_keys = ["主演", "声优", "CV"]
            for k in cast_keys:
                if k in info_dict:
                    names = info_dict[k] if isinstance(info_dict[k], list) else [info_dict[k]]
                    for name in names:
                         credits_data['cast'].append({
                            "name": name,
                            "character": "", 
                            "order": len(credits_data['cast'])
                         })

        # 演职员表键名分配
        if target_type == 'Series':
            # 修复：剧集模式也应该包含 crew 信息
            mapped['credits'] = {
                "cast": credits_data['cast'],
                "crew": credits_data['crew']
            }
        else:
            # 根据电影模板，需要 casts 且包含 cast 和 crew
            mapped['casts'] = credits_data
        
        # 4. Tags
        raw_tags = bgm_data.get('tags', [])
        meta_tags = bgm_data.get('meta_tags', [])
        
        # User tags: Only keep count > 1 to filter noise
        user_tag_names = [t['name'] for t in raw_tags if t.get('count', 0) > 1]
        
        # Combine user tags and meta tags, ensuring uniqueness
        all_tags = list(set(user_tag_names + meta_tags))
        
        # Sort for consistency
        all_tags.sort()
        mapped['tags'] = all_tags
        
        # 5. Rating
        # Bangumi V0 API puts score inside 'rating' object
        rating_obj = bgm_data.get('rating', {})
        if rating_obj:
            mapped['vote_average'] = rating_obj.get('score', 0.0)
            mapped['vote_count'] = rating_obj.get('total', 0)
            
        # 6. Images
        images = bgm_data.get('images', {})
        mapped['poster_path'] = images.get('large') or images.get('common') or ""
        mapped['backdrop_path'] = images.get('large') or ""

        # 7. Production Companies / Networks
        studios = info_dict.get("动画制作") or info_dict.get("制作")
        if studios:
            company_list = [{"name": s} for s in (studios if isinstance(studios, list) else [studios])]
            if target_type == 'Series':
                mapped['networks'] = company_list
            else:
                mapped['production_companies'] = company_list

        # --- 8. 模板补全逻辑 (确保满足最低要求格式) ---
        if target_type == 'Movie':
            # all.json 独有/必有字段补全
            if 'imdb_id' not in mapped: mapped['imdb_id'] = ""
            if 'tagline' not in mapped: mapped['tagline'] = ""
            if 'belongs_to_collection' not in mapped: mapped['belongs_to_collection'] = None
            if 'production_countries' not in mapped: mapped['production_countries'] = []
            if 'production_companies' not in mapped: mapped['production_companies'] = []
            if 'genres' not in mapped: mapped['genres'] = []
            if 'releases' not in mapped: mapped['releases'] = {"countries": []}
            if 'trailers' not in mapped: mapped['trailers'] = {"youtube": []}
        else:
            # series.json 独有/必有字段补全
            if 'last_air_date' not in mapped: mapped['last_air_date'] = date_val
            if 'episode_run_time' not in mapped: mapped['episode_run_time'] = []
            if 'networks' not in mapped: mapped['networks'] = []
            if 'genres' not in mapped: mapped['genres'] = []
            if 'external_ids' not in mapped: mapped['external_ids'] = {"imdb_id": "", "tvrage_id": None, "tvdb_id": None}
            if 'videos' not in mapped: mapped['videos'] = {"results": []}
            if 'content_ratings' not in mapped: mapped['content_ratings'] = {"results": []}
        
        return mapped

    def map_characters(self, characters_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Maps Bangumi v0 characters to internal cast format.
        """
        cast = []
        if not characters_data:
            return cast
            
        # Helper to score relation for sorting (leads first)
        def get_relation_score(rel_text):
            rel_map = {"主角": 10, "主要角色": 8, "客串": 1, "配角": 5}
            return rel_map.get(rel_text, 0)
            
        # Sort characters by relation importance
        sorted_chars = sorted(characters_data, key=lambda x: get_relation_score(x.get('relation', '')), reverse=True)
        
        for idx, char in enumerate(sorted_chars):
            actors = char.get('actors', [])
            if not actors:
                continue
                
            # Use the first actor as primary
            actor = actors[0]
            
            cast.append({
                "name": actor.get('name') or 'Unknown',
                "character": char.get('name') or '', # characters/ API often puts localized in 'name'
                "order": idx,
                "profile_path": actor.get('images', {}).get('large') or ""
            })
            
        return cast

    def map_episode(self, bgm_ep_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps Bangumi V0 Episode JSON to internal episode metadata format.
        Based on real Bangumi v0 API structure.
        """
        if not bgm_ep_data:
            return {}

        mapped = {}
        
        # 1. Basic Fields from Bangumi v0
        # name_cn: 中文标题, name: 原始标题, desc: 剧情简介, airdate: 放送日期
        mapped['name'] = bgm_ep_data.get('name_cn') or bgm_ep_data.get('name') or ''
        mapped['overview'] = (bgm_ep_data.get('desc') or '').replace('\r\n', '\n').strip()
        mapped['air_date'] = bgm_ep_data.get('airdate') or ''
        mapped['vote_average'] = 0.0 # Single episodes in v0 don't have scores
        
        # 2. Coordinates
        mapped['episode_number'] = bgm_ep_data.get('sort')
        
        # 3. Minimum Format Filling (Standard structures required by the user)
        mapped['videos'] = {"results": []}
        mapped['external_ids'] = {
            "tvdb_id": None,
            "tvrage_id": None,
            "imdb_id": ""
        }
        mapped['credits'] = {
            "cast": [],
            "guest_stars": [],
            "crew": []
        }
        
        return mapped

    def _parse_infobox(self, infobox: List[Dict]) -> Dict[str, Any]:
        """
        Parses infobox list into a dictionary.
        Values are either string or list of strings.
        """
        result = {}
        if not infobox:
            return result
            
        for item in infobox:
            key = item.get('key')
            val = item.get('value')
            
            final_val = val
            if isinstance(val, list):
                # If value is a list, it's usually [{"v": "Value1"}, {"v": "Value2"}]
                extracted = []
                for x in val:
                    if isinstance(x, dict) and 'v' in x:
                        extracted.append(x['v'])
                    elif isinstance(x, str):
                        extracted.append(x)
                if extracted:
                    final_val = extracted
            
            result[key] = final_val
        return result