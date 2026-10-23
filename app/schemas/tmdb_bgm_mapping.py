from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class SeasonMapping(BaseModel):
    season_number: str
    bgm_ids: List[int] = Field(default_factory=list)


class TmdbBgmMappingItem(BaseModel):
    tmdb_id: int
    tmdb_type: str = Field(..., pattern="^(tv|movie)$")
    season_mappings: Dict[str, List[int]] = Field(default_factory=dict)


class TmdbBgmMappingList(BaseModel):
    items: List[TmdbBgmMappingItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 60


class DiffItem(BaseModel):
    tmdb_id: int
    tmdb_type: str
    season_number: str
    old_bgm_ids: List[int] = Field(default_factory=list)
    new_bgm_ids: List[int] = Field(default_factory=list)
    diff_type: str = Field(..., pattern="^(new|modified|deleted)$")


class ImportDiffRequest(BaseModel):
    import_data: List[TmdbBgmMappingItem]


class ImportDiffResponse(BaseModel):
    diff_items: List[DiffItem] = Field(default_factory=list)
    stats: Dict[str, int] = Field(default_factory=lambda: {
        "new": 0,
        "modified": 0,
        "deleted": 0,
        "unchanged": 0
    })


class ApplyImportRequest(BaseModel):
    selected_diff_items: List[DiffItem]


class TmdbBgmMappingUpdate(BaseModel):
    tmdb_id: int
    tmdb_type: str = Field(..., pattern="^(tv|movie)$")
    season_mappings: Dict[str, List[int]] = Field(default_factory=dict)
