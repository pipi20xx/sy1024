from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, Index
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    # 列表接口按 item_type 过滤并按 full_date 排序；
    # 主键 (item_id, item_type) 的前缀是 item_id，无法命中该查询
    __table_args__ = (
        Index('ix_items_item_type_full_date', 'item_type', 'full_date'),
    )

    item_id = Column(String, primary_key=True)
    item_type = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    name = Column(String)
    year = Column(Integer)
    full_date = Column(String)
    poster_path = Column(String)
    genres = Column(Text) # Stored as JSON string
    folder_id = Column(String, nullable=False)
    json_path = Column(String)
    last_scanned = Column(String, nullable=False)
    has_episode_group = Column(Boolean, default=False)
    has_external_ids = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.item_id,
            "type": self.item_type,
            "source": self.source,
            "name": self.name,
            "year": self.year,
            "full_date": self.full_date,
            "poster_path": self.poster_path,
            "has_episode_group": self.has_episode_group
        }

class Actor(Base):
    __tablename__ = "actors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tmdb_id = Column(Integer, index=True)
    name = Column(String, index=True)
    original_name = Column(String, index=True)
    duplicate_tmdb_id = Column(String) # 新增字段，用于存放多组 ID
    profile_path = Column(String) # TMDB 头像路径
    metadata_json = Column(Text) # 完整 TMDB Person JSON

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "tmdb_id": self.tmdb_id,
            "name": self.name,
            "original_name": self.original_name,
            "duplicate_tmdb_id": self.duplicate_tmdb_id or "",
            "profile_path": self.profile_path or "",
            "metadata": json.loads(self.metadata_json) if self.metadata_json else None
        }

class LocalCollection(Base):
    __tablename__ = "local_collections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, unique=True, nullable=False, index=True) # e.g. "avengers.json"
    collection_name = Column(String, nullable=False, index=True)
    tmdb_collection_id = Column(String)
    movie_count = Column(Integer, default=0)
    series_count = Column(Integer, default=0)
    poster_path = Column(String) # Relative path for frontend
    created_at = Column(String) # ISO format string
    updated_at = Column(String) # ISO format string

    def to_dict(self):
        p_path = self.poster_path
        if p_path and self.updated_at:
            # Append updated_at as timestamp for cache busting
            ts = self.updated_at.replace(":", "").replace("-", "").replace(".", "")
            p_path = f"{p_path}?t={ts}"
            
        return {
            "id": self.id,
            "filename": self.filename,
            "collection_name": self.collection_name,
            "tmdb_collection_id": self.tmdb_collection_id,
            "movie_count": self.movie_count,
            "series_count": self.series_count,
            "poster_path": p_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    task_type = Column(String, nullable=False) # 'cover', 'collection_poster', 'backup', etc.
    cron_expression = Column(String, nullable=False) # e.g. "0 3 * * *"
    enabled = Column(Boolean, default=True)
    last_run = Column(String)
    next_run = Column(String)
    params = Column(Text) # JSON string for preset parameters

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "task_type": self.task_type,
            "cron_expression": self.cron_expression,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "params": self.params
        }

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, index=True)
    method = Column(String)
    path = Column(String)
    status_code = Column(Integer)
    ip = Column(String)
    query_params = Column(Text)
    payload = Column(Text)
    user_agent = Column(String)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "ip": self.ip,
            "query_params": self.query_params,
            "payload": self.payload,
            "user_agent": self.user_agent
        }

class TmdbApiResponse(Base):
    __tablename__ = "tmdb_api_responses"

    tmdb_id = Column(String, primary_key=True)
    tmdb_type = Column(String, primary_key=True)
    name_cn = Column(String)
    original_json = Column(Text)
    updated_at = Column(DateTime)

    def to_dict(self):
        import json
        return {
            "tmdb_id": self.tmdb_id,
            "tmdb_type": self.tmdb_type,
            "name_cn": self.name_cn,
            "original_json": json.loads(self.original_json) if self.original_json else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

class BangumiAppConfig(Base):
    __tablename__ = "app_config"

    key = Column(String, primary_key=True)
    value = Column(Text)

class BangumiDataItem(Base):
    """bangumi-data 映射表：BGM ID 到 TMDB/MAL 等的映射，含播出日期用于判断完结状态"""
    __tablename__ = "bangumi_data_item"

    bgm_id = Column(Integer, primary_key=True, index=True)
    tmdb_id = Column(Integer, index=True, nullable=True)
    media_type = Column(String, default="tv")
    title = Column(Text)
    title_cn = Column(Text, index=True)
    begin = Column(Text)
    end = Column(Text)
    broadcast = Column(Text)
    updated_at = Column(DateTime)

class BangumiSubjectCache(Base):
    """永久缓存：完结番剧的 Subject/Episodes/Characters 原始 API 响应"""
    __tablename__ = "bangumi_subject_cache"

    bgm_id = Column(Integer, primary_key=True, index=True)
    subject_json = Column(Text)
    episodes_json = Column(Text)
    characters_json = Column(Text)
    fetched_at = Column(DateTime)

class BangumiTempCache(Base):
    """临时缓存：未完结/未知完结状态番剧的原始 API 响应，带过期时间"""
    __tablename__ = "bangumi_temp_cache"

    bgm_id = Column(Integer, primary_key=True, index=True)
    subject_json = Column(Text)
    episodes_json = Column(Text)
    characters_json = Column(Text)
    fetched_at = Column(DateTime)
    expire_at = Column(DateTime)

class TmdbBangumiMap(Base):
    __tablename__ = "tmdb_bangumi_map"
    # get_relation_by_bangumi 只按 bangumi_id 查询，
    # 主键前缀 (tmdb_id, tmdb_type) 用不上，否则全表扫描
    __table_args__ = (
        Index('ix_tmdb_bangumi_map_bangumi_id', 'bangumi_id'),
    )

    tmdb_id = Column(String, primary_key=True)
    tmdb_type = Column(String, primary_key=True)
    bangumi_id = Column(Integer, primary_key=True)
    note = Column(Text)
    score = Column(Integer)
    status = Column(Integer, default=0)
    season_number = Column(Integer, default=1)
    updated_at = Column(DateTime)

class TmdbBgmMapping(Base):
    __tablename__ = "tmdb_bgm_mapping"

    tmdb_id = Column(Integer, primary_key=True, nullable=False)
    tmdb_type = Column(String, primary_key=True, nullable=False)
    season_mappings = Column(Text, nullable=False)

    def to_dict(self):
        import json
        return {
            "tmdb_id": self.tmdb_id,
            "tmdb_type": self.tmdb_type,
            "season_mappings": json.loads(self.season_mappings) if self.season_mappings else {}
        }


