from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, RootModel
from .tmdb_bgm_mapping import (
    SeasonMapping,
    TmdbBgmMappingItem,
    TmdbBgmMappingList,
    DiffItem,
    ImportDiffRequest,
    ImportDiffResponse,
    ApplyImportRequest,
    TmdbBgmMappingUpdate
)

class BatchDetailsRequest(BaseModel):
    movie_ids: Optional[List[str]] = []
    series_ids: Optional[List[str]] = []

class EmbyMetadataUpdateRequest(BaseModel):
    fields_to_update: List[str]
    update_children: bool

class TmdbMetadataUpdateRequest(BaseModel):
    fields_to_update: Optional[List[str]] = None
    overwrite: bool = False
    trigger_emby_refresh: bool = False
    update_season_episodes: bool = False

class TmdbManualGenerateRequest(BaseModel):
    source: str = "tmdb" # "tmdb" or "bangumi"
    source_item_type: str # movie, tv, season, episode
    target_item_type: Optional[str] = None # New: movie or tv
    source_tmdb_id: str
    target_tmdb_id: str
    lang: str = "zh-CN"
    source_season: Optional[int] = None
    target_season: Optional[int] = None
    source_episode: Optional[int] = None
    target_episode: Optional[int] = None
    selected_episodes: Optional[List[int]] = None # For batch generation from Bangumi
    overwrite: bool = True
    recursive: bool = False
    trigger_emby_refresh: bool = False

class ResourceModel(BaseModel):
    team: Optional[str] = ""
    url: Optional[str] = ""
    magnet: Optional[str] = ""
    season_episode: Optional[str] = ""
    subtitles: Optional[str] = ""
    media: Optional[str] = ""
    codec: Optional[str] = ""
    resolution: Optional[str] = ""
    remarks: Optional[str] = ""
    attachment: Optional[List[str]] = []

class ResourceUpdateRequest(RootModel[List[ResourceModel]]):
    pass

class TagRuleCreateUpdate(BaseModel):
    name: str
    tag: str
    countries: List[str] = []
    genres: List[int] = []
    media_type: str # "all", "movie", "tv"
    year: Optional[Union[int, str, List[int]]] = None
    strict_match: bool = False
    negative_match: bool = False

class ItemTagRequest(BaseModel):
    tags_to_add: Optional[List[str]] = None
    mode: str = 'merge'

class ItemTagDeleteRequest(BaseModel):
    tags_to_delete: List[str]

class CustomTagPresets(RootModel[Dict[str, Any]]):
    pass

class LockNameRequest(BaseModel):
    mode: Optional[str] = None

class WorkflowTask(BaseModel):
    type: str
    params: Optional[Dict[str, Any]] = {}

class WorkflowRequest(BaseModel):
    item_type: str
    tasks: List[WorkflowTask]
    interval_seconds: int = 2
    item_ids: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None