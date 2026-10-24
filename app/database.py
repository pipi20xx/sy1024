from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
import os

from .common import get_config_path, APP_DB_FILENAME

# Database Configuration
# 用户可以通过环境变量选择数据库类型: 'sqlite' 或 'postgresql'
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()

# PostgreSQL Configuration (如果使用 PostgreSQL)
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'sytmdb')

def get_db_url(db_name: str) -> str:
    """根据配置返回数据库连接 URL"""
    if DB_TYPE == 'postgresql':
        # PostgreSQL: 所有数据库使用同一个 PostgreSQL 实例，不同的 database 名称
        return f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{db_name}"
    else:
        # SQLite (默认)
        # items 使用 APP_DB_FILENAME (items_cache.db)，其他使用 db_name.db
        if db_name == 'items':
            db_path = get_config_path(APP_DB_FILENAME)
        else:
            db_path = get_config_path(f'{db_name}.db')
        return f"sqlite+aiosqlite:///{db_path}"

# Define database URLs
ITEMS_DB_URL = get_db_url('items')
ACTORS_DB_URL = get_db_url('actors')
COLLECTIONS_DB_URL = get_db_url('collections')
TASKS_DB_URL = get_db_url('tasks')
AUDIT_LOG_DB_URL = get_db_url('audit_logs')
USERS_DB_URL = get_db_url('users')
SESSIONS_DB_URL = get_db_url('sessions')
TMDB_CACHE_DB_URL = get_db_url('tmdb_api_cache')
BANGUMI_DB_URL = get_db_url('bangumi')
BANGUMI_CACHE_DB_URL = get_db_url('bangumi_cache')
MEDIA_RELATIONS_DB_URL = get_db_url('media_relations')
TMDB_BGM_MAPPING_DB_URL = get_db_url('tmdb_bgm_mapping')



# Create Async Engines

def create_engine_config(db_url: str):
    """根据数据库类型返回不同的引擎配置"""
    if DB_TYPE == 'postgresql':
        return {
            'echo': False,
            'pool_size': 10,
            'max_overflow': 20,
            # pre_ping + recycle：避免长连接被服务端/防火墙断开后出现僵死连接
            'pool_pre_ping': True,
            'pool_recycle': 1800,
        }
    else:
        # SQLite：使用默认的 AsyncAdaptedQueuePool 小连接池复用连接。
        # 之前用的 NullPool 每次开 session 都要重新打开数据库文件并执行 PRAGMA，
        # 而本项目大量采用"每个方法开自己的 session"的模式，连接重建开销被成倍放大。
        # SQLite 同一时刻只有一个写者，配合 busy_timeout 让写冲突等待而不是立即报
        # "database is locked"，池子保持很小以控制并发写压力。
        return {
            'echo': False,
            'pool_size': 5,
            'max_overflow': 3,
            'connect_args': {"check_same_thread": False}
        }

items_engine = create_async_engine(ITEMS_DB_URL, **create_engine_config(ITEMS_DB_URL))
actors_engine = create_async_engine(ACTORS_DB_URL, **create_engine_config(ACTORS_DB_URL))
collections_engine = create_async_engine(COLLECTIONS_DB_URL, **create_engine_config(COLLECTIONS_DB_URL))
tasks_engine = create_async_engine(TASKS_DB_URL, **create_engine_config(TASKS_DB_URL))
audit_log_engine = create_async_engine(AUDIT_LOG_DB_URL, **create_engine_config(AUDIT_LOG_DB_URL))
users_engine = create_async_engine(USERS_DB_URL, **create_engine_config(USERS_DB_URL))
sessions_engine = create_async_engine(SESSIONS_DB_URL, **create_engine_config(SESSIONS_DB_URL))
tmdb_cache_engine = create_async_engine(TMDB_CACHE_DB_URL, **create_engine_config(TMDB_CACHE_DB_URL))
bangumi_engine = create_async_engine(BANGUMI_DB_URL, **create_engine_config(BANGUMI_DB_URL))
bangumi_cache_engine = create_async_engine(BANGUMI_CACHE_DB_URL, **create_engine_config(BANGUMI_CACHE_DB_URL))
media_relations_engine = create_async_engine(MEDIA_RELATIONS_DB_URL, **create_engine_config(MEDIA_RELATIONS_DB_URL))
tmdb_bgm_mapping_engine = create_async_engine(TMDB_BGM_MAPPING_DB_URL, **create_engine_config(TMDB_BGM_MAPPING_DB_URL))



# Enable Write-Ahead Logging (WAL) mode for better concurrency (SQLite only)
# This allows readers to not block writers and vice versa
if DB_TYPE == 'sqlite':
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # 写锁冲突时等待 5 秒重试，而不是立即抛 "database is locked"
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    event.listen(items_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(actors_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(collections_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(tasks_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(audit_log_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(users_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(sessions_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(tmdb_cache_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(bangumi_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(bangumi_cache_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(media_relations_engine.sync_engine, "connect", _set_sqlite_pragma)
    event.listen(tmdb_bgm_mapping_engine.sync_engine, "connect", _set_sqlite_pragma)




# Create Session Factories

ItemsSessionLocal = sessionmaker(

    bind=items_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



ActorsSessionLocal = sessionmaker(

    bind=actors_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



CollectionsSessionLocal = sessionmaker(

    bind=collections_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



TasksSessionLocal = sessionmaker(

    bind=tasks_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



AuditLogSessionLocal = sessionmaker(

    bind=audit_log_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



UsersSessionLocal = sessionmaker(
    bind=users_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

SessionsSessionLocal = sessionmaker(
    bind=sessions_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)




TmdbCacheSessionLocal = sessionmaker(

    bind=tmdb_cache_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



BangumiSessionLocal = sessionmaker(

    bind=bangumi_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



BangumiCacheSessionLocal = sessionmaker(

    bind=bangumi_cache_engine,

    class_=AsyncSession,

    expire_on_commit=False,

    autocommit=False,

    autoflush=False,

)



MediaRelationsSessionLocal = sessionmaker(
    bind=media_relations_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

TmdbBgmMappingSessionLocal = sessionmaker(
    bind=tmdb_bgm_mapping_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)



async def get_items_db():

    async with ItemsSessionLocal() as session:

        yield session



async def get_actors_db():

    async with ActorsSessionLocal() as session:

        yield session



async def get_collections_db():

    async with CollectionsSessionLocal() as session:

        yield session



async def get_tasks_db():

    async with TasksSessionLocal() as session:

        yield session



async def get_users_db():
    async with UsersSessionLocal() as session:
        yield session

async def get_sessions_db():
    async with SessionsSessionLocal() as session:
        yield session




async def get_tmdb_cache_db():

    async with TmdbCacheSessionLocal() as session:

        yield session
