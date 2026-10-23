# app/globals.py
from typing import Optional
from .services import SystemService
from .tag_management.tag_service import TagService
from .emby_collection_service import EmbyCollectionService
from .backup_service import BackupService
from .resource_service import ResourceService
from .webhook_service import WebhookService
# app/services/bangumi is imported only for type hinting if needed, but to avoid circular imports we might skip it here or use TYPE_CHECKING
# For now, just adding the variable.

# 全局服务实例，将在 main.py 启动时初始化
service: Optional[SystemService] = None
tag_service: Optional[TagService] = None
collection_service: Optional[EmbyCollectionService] = None
backup_service: Optional[BackupService] = None
resource_service: Optional[ResourceService] = None
webhook_service: Optional[WebhookService] = None
bangumi_service = None # Type: Optional[BangumiService]
relation_service = None # Type: Optional[RelationService]
emby_tag_writer_service = None # Type: Optional[EmbyTagWriterService]
scheduler_service = None # Type: Optional[SchedulerService]
tmdb_bgm_mapping_service = None # Type: Optional[TmdbBgmMappingService]
bangumi_data_sync_service = None # Type: Optional[BangumiDataSyncService]
