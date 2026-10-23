import yaml
import os
from typing import Dict, Any, Optional

from app.logger import log_audit


class MetadataDefinitionService:
    def __init__(self, root_dir: Optional[str] = None):
        # If root_dir is not provided, calculate it relative to this file
        if root_dir is None:
            # This file is in app/services/
            # We want app/definitions/
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.definitions_dir = os.path.join(os.path.dirname(current_dir), 'definitions')
        else:
            self.definitions_dir = root_dir

        self.platforms = {}
        self.relations = {}
        self.staffs = {}
        self.load_definitions()

    def load_definitions(self):
        """Load all YAML definition files."""
        try:
            self.platforms = self._load_yaml("subject_platforms.yml")
            self.relations = self._load_yaml("subject_relations.yml")
            self.staffs = self._load_yaml("subject_staffs.yml")
        except Exception as e:
            log_audit("元数据定义", "处理", f"Failed to load metadata definitions: {e}", level="ERROR")
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(self.definitions_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        else:
            log_audit("元数据定义", "处理", f"Definition file not found: {path}", level="WARN")
            return {}

    def get_platform_info(self, type_id: int, platform_id: int) -> Dict[str, Any]:
        """
        Get platform info from subject_platforms.yml.
        
        Structure of YAML is complex with anchors.
        We need to navigate: platforms -> (Subject Type Key) -> (Platform ID)
        """
        # Mapping from numeric type_id to the key used in 'platforms' section of YAML
        # Based on 'define' -> 'type' section in YAML
        # book: 1, anime: 2, music: 3, game: 4, real: 6
        type_key_map = {
            1: 'book',     # *TYPE_BOOK
            2: 'anime',    # *TYPE_ANIME
            3: 'music',    # *TYPE_MUSIC
            4: 'game',     # *TYPE_GAME
            6: 'real'      # *TYPE_REAL
        }
        
        # Note: In the loaded YAML, anchors are resolved. 
        # But the keys in 'platforms' dict might be the integer values of the anchors if they were used as keys?
        # Let's look at the file content again.
        # platforms:
        #   *TYPE_BOOK : ...
        # Since *TYPE_BOOK is 1, the key in the python dict will be integer 1.
        
        if not self.platforms:
            return {}

        try:
            # The 'platforms' root key in YAML contains the mapping
            platforms_root = self.platforms.get('platforms', {})
            
            # The key for subject type (e.g., 2 for Anime)
            # In Python yaml loader, keys defined with anchors usually resolve to their values.
            # So platforms_root[2] should give the Anime platforms.
            type_platforms = platforms_root.get(type_id)
            
            if not type_platforms:
                return {}
                
            # The platform_id (e.g., 1 for TV)
            platform_info = type_platforms.get(platform_id)
            
            return platform_info or {}

        except Exception as e:
            log_audit("元数据定义", "处理", f"Error looking up platform info: {e}", level="ERROR")
            return {}

    def is_movie_platform(self, type_id: int, platform_id: int) -> bool:
        """Check if the platform corresponds to a Movie (Theatrical Release)."""
        info = self.get_platform_info(type_id, platform_id)
        if not info:
            return False
            
        # Check alias or type_cn
        alias = info.get('alias', '').lower()
        return alias == 'movie' or '剧场版' in info.get('type_cn', '')

    def is_tv_platform(self, type_id: int, platform_id: int) -> bool:
        """Check if the platform corresponds to TV/Web Series."""
        info = self.get_platform_info(type_id, platform_id)
        if not info:
            return False
            
        alias = info.get('alias', '').lower()
        # Common non-movie types for Anime
        return alias in ['tv', 'web', 'ova', 'anime_comic'] 

    def get_tmdb_media_type_preference(self, type_id: int, platform_id: int) -> Optional[str]:
        """
        Return 'movie' or 'tv' based on platform, or None if unsure.
        """
        # Only handle Anime (2) and Real (6) for now as they map to TMDB
        if type_id not in [2, 6]:
            return None
            
        if self.is_movie_platform(type_id, platform_id):
            return 'movie'
        if self.is_tv_platform(type_id, platform_id):
            return 'tv'
            
        return None
