import os
import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from ..common import get_config_path, APP_DB_FILENAME, SOURCE_PRIMARY, SOURCE_OVERRIDE
from ..web_image_service import WebImageService
from ..logger import log_audit
from .configuration import ConfigurationService
from .emby_integration import EmbyIntegrationService
from .scanner import ScannerService
from .actor import ActorService
from .editor import EditorService
from .images import ImageService
from .tmdb_metadata import TmdbMetadataService
from .file_watcher import FileWatcherService
from ..emby_metadata_updater import EmbyMetadataUpdater
from ..database import tmdb_cache_engine, tmdb_bgm_mapping_engine
from ..models import TmdbApiResponse, TmdbBgmMapping


class SystemService:
    def __init__(self):
        self.configuration_service = ConfigurationService()
        self.config = self.configuration_service.get_config()
        
        # 版本检查缓存
        self._update_cache = {
            "latest_version": None,
            "last_check": None
        }
        self._current_version = "1.4.4"
        self._docker_repo = "pipi20xx/sy1024"
        self.emby_integration_service = EmbyIntegrationService(self.configuration_service)
        self.scanner_service = ScannerService(self.configuration_service, self.emby_integration_service)
        self.actor_service = ActorService()
        
        self.editor_service = EditorService(self.configuration_service, self.scanner_service, self.emby_integration_service, self.actor_service)
        self.web_image_service = WebImageService(self.config)
        
        self.image_service = ImageService(self.configuration_service, self.scanner_service, self.editor_service, self.web_image_service, self.emby_integration_service)
        self.tmdb_metadata_service = TmdbMetadataService(self.configuration_service, self.editor_service, self.scanner_service, self.emby_integration_service)

        self.file_watcher_service = FileWatcherService(self.configuration_service, self.scanner_service)

        self.db_path = get_config_path(APP_DB_FILENAME)
        self.actors_db_path = get_config_path('actors.db')
        self.audit_log_db_path = get_config_path('audit_logs.db')

    @property
    def emby_client(self):
        return self.emby_integration_service.emby_client

    def _get_cache_path_for_source(self, source: str) -> Optional[str]:
        """
        Helper method to get cache paths from configuration service.
        """
        return self.configuration_service.get_cache_path_for_source(source)
    async def get_latest_version(self, force: bool = False) -> Dict[str, Any]:
        """从 Docker Hub 获取最新标签，带有缓存及代理支持"""
        now = datetime.now()
        
        # 如果不是强制检查，且缓存未过期，则返回缓存
        if not force and self._update_cache["last_check"] and \
           (now - self._update_cache["last_check"]) < timedelta(hours=24):
            return {
                "current": self._current_version,
                "latest": self._update_cache["latest_version"],
                "has_update": self._is_newer(self._update_cache["latest_version"]),
                "cached": True
            }

        try:
            log_audit("系统", "版本检查", f"检查 Docker Hub 更新 (强制={force})", level="START")
            
            proxy_url = self.configuration_service.config.get("network", {}).get("proxy_url")
            enable_global = self.configuration_service.config.get("network", {}).get("enable_global", False)
            
            # 使用 proxy 参数替代过时的 proxies 参数
            proxy = proxy_url if (enable_global and proxy_url) else None
            if proxy:
                log_audit("系统", "处理", f"版本检查使用代理: {proxy}", level="DEBUG")
            async with httpx.AsyncClient(timeout=10.0, proxy=proxy) as client:
                url = f"https://hub.docker.com/v2/repositories/{self._docker_repo}/tags/?page_size=20&ordering=last_updated"
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    tags = data.get("results", [])
                    
                    latest_tag = None
                    for tag in tags:
                        tag_name = tag.get("name")
                        if tag_name and tag_name != "latest" and any(c.isdigit() for c in tag_name):
                            latest_tag = tag_name.lstrip('vV')
                            break
                    
                    if latest_tag:
                        self._update_cache["latest_version"] = latest_tag
                        self._update_cache["last_check"] = now
                        
                        return {
                            "current": self._current_version,
                            "latest": latest_tag,
                            "has_update": self._is_newer(latest_tag),
                            "cached": False
                        }
        except Exception as err:
            log_audit("系统", "版本检查失败", str(err), level="ERROR")
            return {
                "current": self._current_version,
                "latest": self._update_cache["latest_version"],
                "has_update": self._is_newer(self._update_cache["latest_version"]),
                "error": str(err),
                "cached": True
            }
            
        return {
            "current": self._current_version,
            "latest": self._update_cache["latest_version"],
            "has_update": self._is_newer(self._update_cache["latest_version"]),
            "cached": True
        }

    def _is_newer(self, latest: Optional[str]) -> bool:
        if not latest: return False
        try:

            def parse_v(v): return [int(x) for x in v.split('.') if x.isdigit()]
            return parse_v(latest) > parse_v(self._current_version)
        except:
            return latest != self._current_version

    @property
    def emby_client(self):
        return self.emby_integration_service.emby_client

    def _get_cache_path_for_source(self, source: str) -> Optional[str]:
        """
        Helper method to get cache paths from configuration service.
        """
        return self.configuration_service.get_cache_path_for_source(source)

    async def update_metadata_from_emby(self,
                                        item_type: str,
                                        emby_item_id: str,
                                        folder_tmdb_id: str,
                                        original_emby_item_type: str,
                                        fields_to_update: List[str],
                                        update_children: bool) -> Tuple[bool, str]:
        """
        Orchestrates the update of metadata for an Emby item using EmbyMetadataUpdater.
        """
        emby_client = self.emby_client
        if not emby_client:
            return False, "Emby客户端未初始化，无法更新元数据。"

        server_url = self.config.get("emby_server_url")
        api_key = self.config.get("emby_api_key")
        user_id = self.config.get("emby_user_id")

        if not all([server_url, api_key, user_id]):
            return False, "Emby服务器配置不完整，无法更新元数据。"

        primary_cache_path = self._get_cache_path_for_source(SOURCE_PRIMARY)
        override_cache_path = self._get_cache_path_for_source(SOURCE_OVERRIDE)

        if not primary_cache_path or not override_cache_path:
            return False, "缓存路径未配置，无法更新元数据。"
        
        # Construct local_item_path
        # Assuming the structure: {primary_cache_path}/{item_type}/{folder_tmdb_id}
        local_item_path = os.path.join(override_cache_path, item_type, folder_tmdb_id)

        try:
            updater = EmbyMetadataUpdater(
                server_url=server_url,
                api_key=api_key,
                user_id=user_id,
                emby_item_id=emby_item_id,
                folder_tmdb_id=folder_tmdb_id,
                media_type=original_emby_item_type,
                local_item_path=local_item_path,
                override_cache_path=override_cache_path,
                fields_to_update=fields_to_update,
                update_children=update_children
            )
            # EmbyMetadataUpdater's run_update is synchronous, run it in a separate thread
            await asyncio.to_thread(updater.run_update)
            return True, "元数据更新已成功启动。"
        except Exception as e:
            log_audit("Emby", "元数据更新失败", str(e), level="ERROR")
            return False, f"元数据更新失败: {e}"

    async def _refresh_item_in_db(self, item_type: str, tmdb_id: str):
        """
        Delegates to scanner_service to refresh the item's record in the DB after edits.
        """
        await self.scanner_service._refresh_item_in_db(item_type, tmdb_id)

    def reload_services(self):
        """Re-initialize services that depend on configuration."""
        log_audit("系统", "服务重载", "配置变更，重新加载服务", level="START")
        self.emby_integration_service.reload_client()
        # WebImageService holds a reference to config dict, so if that dict is updated in place, 
        # it might not need re-creation unless it caches values. 
        # But for safety, we recreate it.
        self.web_image_service = WebImageService(self.config)
        self.image_service.web_image_service = self.web_image_service # Update reference in ImageService

        # 重启文件监控服务（根据最新配置决定是否启动）
        self.file_watcher_service.stop()
        if self.config.get("file_watcher_enabled", False):
            # 确保事件循环已设置（可能启动时未启用，首次在设置中开启）
            if not self.file_watcher_service._loop:
                try:
                    self.file_watcher_service.set_event_loop(asyncio.get_running_loop())
                except RuntimeError:
                    pass
            self.file_watcher_service.start()

        log_audit("系统", "服务重载完成", "服务重新初始化完成", level="DONE")

    def get_emby_config_status(self) -> dict:
        return {"configured": self.emby_client is not None}

    async def init_databases(self):
        """Async initialization of database tables."""
        from ..database import items_engine, actors_engine, collections_engine, audit_log_engine, tasks_engine, bangumi_engine, bangumi_cache_engine, media_relations_engine, sessions_engine, users_engine
        from ..models import Base, Item, Actor, LocalCollection, AuditLog, ScheduledTask
        from ..models import BangumiAppConfig, BangumiDataItem, BangumiSubjectCache, BangumiTempCache, TmdbBangumiMap
        from ..models.session import Session
        from ..models.user import User
        
        log_audit("数据库", "初始化", "正在初始化数据库表 (SQLAlchemy)", level="START")
        
        # Initialize Items DB (Only Item table)
        async with items_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[Item.__table__]))
        
        # Initialize Actors DB (Only Actor table)
        async with actors_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[Actor.__table__]))
             
        # Initialize Collections DB (Only LocalCollection table)
        async with collections_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[LocalCollection.__table__]))

        # Initialize Tasks DB (Only ScheduledTask table)
        async with tasks_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[ScheduledTask.__table__]))
        
        # Initialize Audit Logs DB (Only AuditLog table)
        async with audit_log_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[AuditLog.__table__]))

        # Initialize TMDB Cache DB (Only TmdbApiResponse table)
        async with tmdb_cache_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[TmdbApiResponse.__table__]))
             
        # Initialize Bangumi DB (BangumiAppConfig + BangumiDataItem)
        async with bangumi_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[
                 BangumiAppConfig.__table__,
                 BangumiDataItem.__table__
             ]))
             
        # Initialize Bangumi Cache DB (BangumiSubjectCache + BangumiTempCache)
        async with bangumi_cache_engine.begin() as conn:
             await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[
                 BangumiSubjectCache.__table__,
                 BangumiTempCache.__table__
             ]))
             
        # Initialize Media Relations DB (Only TmdbBangumiMap table)
        async with media_relations_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[TmdbBangumiMap.__table__]))
            
        # Initialize TmdbBgmMapping DB (Only TmdbBgmMapping table)
        async with tmdb_bgm_mapping_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[TmdbBgmMapping.__table__]))
             
        # Initialize Users DB (Only User table)
        async with users_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[User.__table__]))
             
        # Initialize Sessions DB (Only Session table)
        async with sessions_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[Session.__table__]))
             
        # Run database migrations to ensure new columns exist
        await self._run_database_migrations(items_engine, users_engine)
        
        log_audit("数据库", "初始化完成", "数据库初始化完成", level="DONE")

    async def _run_database_migrations(self, items_engine, users_engine):
        """
        Run database migrations to add missing columns.
        This is a simple migration system that checks for missing columns and adds them.
        """
        from ..database import DB_TYPE
        from ..models import Item
        from ..models.user import User
        from sqlalchemy import inspect, text
        
        log_audit("系统", "处理", "检查数据库迁移...")
        # Migrate items table
        async with items_engine.begin() as conn:
            def check_and_add_items_column(sync_conn):
                inspector = inspect(sync_conn)
                columns = [col['name'] for col in inspector.get_columns('items')]
                
                if 'has_external_ids' not in columns:
                    log_audit("系统", "创建", "添加 has_external_ids 列到 items 表...")
                    if DB_TYPE == 'sqlite':
                        sync_conn.execute(text("ALTER TABLE items ADD COLUMN has_external_ids BOOLEAN DEFAULT 0"))
                    elif DB_TYPE == 'postgresql':
                        sync_conn.execute(text("ALTER TABLE items ADD COLUMN has_external_ids BOOLEAN DEFAULT FALSE"))
                    
                    sync_conn.commit()
                    log_audit("系统", "完成", "成功添加 has_external_ids 列")
                else:
                    log_audit("系统", "跳过", "has_external_ids 列已存在，跳过迁移")
            await conn.run_sync(check_and_add_items_column)
        
        # Migrate users table
        async with users_engine.begin() as conn:
            def check_and_add_users_column(sync_conn):
                inspector = inspect(sync_conn)
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'token_version' not in columns:
                    log_audit("系统", "创建", "添加 token_version 列到 users 表...")
                    if DB_TYPE == 'sqlite':
                        sync_conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1"))
                    elif DB_TYPE == 'postgresql':
                        sync_conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1"))
                    
                    sync_conn.commit()
                    log_audit("系统", "完成", "成功添加 token_version 列")
                else:
                    log_audit("系统", "跳过", "token_version 列已存在，跳过迁移")
            await conn.run_sync(check_and_add_users_column)
        
        # Migrate actors table
        from ..database import actors_engine
        async with actors_engine.begin() as conn:
            def check_and_add_actors_columns(sync_conn):
                inspector = inspect(sync_conn)
                columns = [col['name'] for col in inspector.get_columns('actors')]
                
                if 'profile_path' not in columns:
                    log_audit("系统", "创建", "添加 profile_path 列到 actors 表...")
                    sync_conn.execute(text("ALTER TABLE actors ADD COLUMN profile_path TEXT"))
                    sync_conn.commit()
                    log_audit("系统", "完成", "成功添加 profile_path 列")
                
                if 'metadata_json' not in columns:
                    log_audit("系统", "创建", "添加 metadata_json 列到 actors 表...")
                    sync_conn.execute(text("ALTER TABLE actors ADD COLUMN metadata_json TEXT"))
                    sync_conn.commit()
                    log_audit("系统", "完成", "成功添加 metadata_json 列")
            await conn.run_sync(check_and_add_actors_columns)
