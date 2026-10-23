# app/main.py

import os
import sys
import traceback
import uvicorn
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from app.middleware import ExternalControlMiddleware

# 确保 app 目录保持在搜索路径中
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 1. 最优先加载基础配置和日志
try:
    from app.logger import logger, init_logging, log_audit
    # 显式初始化日志系统
    init_logging()
except Exception as e:
    print(f"FATAL ERROR: Failed to load logger: {e}", file=sys.stderr)
    raise

# 2. 导入核心组件
try:
    from app import globals
    from app.services import SystemService
    from app.websocket_manager import manager
    from app.routers.system import start_scheduler
    
    # 批量导入路由
    from app.routers import (
        actors, items, tags, emby, backups, system, 
        workflow, covers, previews, bangumi, 
        bangumi_sync, tmdb_metadata, collection_posters, tmdb_proxy,
        external_control, tasks, auth, ai, shenyi, tmdb_bgm_mapping,
        bangumi_data_sync, appearance
    )
except Exception as e:
    log_audit("系统", "导入", f"模块导入阶段发生错误: {e}", level="CRITICAL")
    raise

app = FastAPI(
    title="TMDB 媒体库管理系统 API",
    description="用于管理 Emby 媒体库、同步 Bangumi 数据、生成封面及合集海报的后端接口服务。",
    version="1.2.0",
    openapi_url=None,
    docs_url=None, 
    redoc_url=None, 
)

# --- Middleware ---
app.add_middleware(ExternalControlMiddleware)

# --- 全局异常处理器 ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    from app.logger import log_audit
    log_audit("请求", "校验", f"参数校验失败: {exc.errors()}", level="ERROR")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)

# --- Startup ---
async def log_cleanup_worker():
    """定期日志清理任务"""
    from app.logger import clean_old_logs
    while True:
        await clean_old_logs()
        await asyncio.sleep(12 * 3600)

@app.on_event("startup")
async def startup_event():
    try:
        # 启动后台任务
        asyncio.create_task(manager.log_broadcast_loop())
        asyncio.create_task(log_cleanup_worker())
        
        log_audit("系统", "启动", "正在初始化系统服务...", level="START")
        
        # 1. 基础系统服务
        service = SystemService()
        globals.service = service
        await service.init_databases()
        
        # 延迟导入以避免循环依赖
        from app.emby_collection_service import EmbyCollectionService
        from app.webhook_service import WebhookService
        from app.backup_service import BackupService
        from app.resource_service import ResourceService
        from app.tag_management.tag_service import TagService
        
        # 导入业务层服务
        from app.services.bangumi import BangumiService
        from app.services.relation import RelationService
        from app.services.emby_tag_writer import EmbyTagWriterService
        from app.services.scheduler_service import scheduler_service
        from app.services.tmdb_bgm_mapping_service import TmdbBgmMappingService
        from app.services.bangumi_data_sync import BangumiDataSyncService
        
        # 2. 核心模块初始化
        col_path = service.config.get("emby_collections_path")
        globals.collection_service = EmbyCollectionService(col_path, system_service=service)
        service.editor_service.emby_collection_service = globals.collection_service
        
        await globals.collection_service._initial_sync()
        
        globals.webhook_service = WebhookService(config=service.config, system_service=service)
        globals.backup_service = BackupService(service.config)
        globals.tag_service = TagService(system_service=service)
        globals.resource_service = ResourceService(service.config)
        
        # 3. 业务逻辑服务初始化 (严格校验构造函数参数)
        globals.bangumi_service = BangumiService()
        globals.relation_service = RelationService()
        
        globals.emby_tag_writer_service = EmbyTagWriterService()
        globals.scheduler_service = scheduler_service
        globals.tmdb_bgm_mapping_service = TmdbBgmMappingService()
        globals.bangumi_data_sync_service = BangumiDataSyncService()
        
        # 反向注册
        service.collection_service = globals.collection_service
        service.tag_service = globals.tag_service
        
        if start_scheduler:
            start_scheduler()

        # 启动文件监控（如果配置中已启用）
        if service.config.get("file_watcher_enabled", False):
            service.file_watcher_service.set_event_loop(asyncio.get_running_loop())
            service.file_watcher_service.start()

        log_audit("系统", "启动完成", "所有服务已初始化", level="DONE")
    except Exception as e:
        log_audit("系统", "启动", f"服务初始化失败: {e}", level="CRITICAL")
        os._exit(1)

# --- 注册路由 ---
app.include_router(actors.router)
app.include_router(items.router)
app.include_router(tags.router)
app.include_router(emby.router)
app.include_router(backups.router)
app.include_router(system.router)
app.include_router(workflow.router)
app.include_router(covers.router)
app.include_router(previews.router)
app.include_router(bangumi.router)
app.include_router(bangumi_sync.router)
app.include_router(tmdb_metadata.router)
app.include_router(collection_posters.router)
app.include_router(tasks.router)
app.include_router(tmdb_proxy.router)
app.include_router(external_control.router)
app.include_router(auth.router)
app.include_router(ai.router)
app.include_router(shenyi.router)
app.include_router(tmdb_bgm_mapping.router)
app.include_router(bangumi_data_sync.router)
app.include_router(appearance.router)

# --- OpenAPI ---
from fastapi.openapi.utils import get_openapi
@app.get("/api/openapi.json", include_in_schema=False)
async def get_open_api_endpoint():
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    
    # 强制统一所有接口的安全要求为 BearerAuth (参照 cs123 实现)
    if "components" not in schema:
        schema["components"] = {}
        
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    
    if "paths" in schema:
        for path in schema["paths"].values():
            for operation in path.values():
                operation["security"] = [{"BearerAuth": []}]
                
    schema["security"] = [{"BearerAuth": []}]
    
    return JSONResponse(schema)

# --- 静态文件 ---
static_path = os.path.join(current_dir, "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_root():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"detail": "Frontend not found"}, status_code=404)

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    if full_path.startswith(("api", "static", "media-content")):
        raise HTTPException(status_code=404)
    # 优先尝试从静态目录提供文件 (manifest.json, pwa-*.png, favicon 等)
    # 防止路径穿越攻击
    safe_path = os.path.normpath(os.path.join(static_path, full_path))
    if safe_path.startswith(static_path) and os.path.isfile(safe_path):
        return FileResponse(safe_path)
    # 未匹配到静态文件，回退到 index.html (SPA 路由)
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"detail": "Not found"}, status_code=404)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
