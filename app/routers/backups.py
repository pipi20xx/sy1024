from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse
import asyncio
import os
import shutil
from .. import globals
from app.logger import log_audit

router = APIRouter(tags=["备份管理"])

@router.post("/api/backups/create", summary="创建系统备份")
async def create_backup(request: Request):
    """创建全量或快照备份，可包含覆盖数据和合集。"""
    params = request.query_params
    mode = params.get("mode", "snapshot")
    include_override = params.get("include_override", "true").lower() == 'true'
    include_collections = params.get("include_collections", "true").lower() == 'true'
    if not globals.backup_service.is_enabled: raise HTTPException(status_code=400, detail="备份服务未启用。")
    if mode not in ["snapshot", "zip"]: raise HTTPException(status_code=400, detail="mode 参数错误")
    # BackupService 全部是同步重 IO（copytree/压缩/解压），必须放线程池避免阻塞事件循环
    success, message = await asyncio.to_thread(globals.backup_service.create_backup, mode, include_override, include_collections)
    if not success:
        log_audit("备份", "创建失败", f"模式: {mode}, 错误: {message}", level="ERROR")
        raise HTTPException(status_code=500, detail=message)
    log_audit("备份", "创建", f"模式: {mode}, 覆盖: {include_override}, 合集: {include_collections}", level="SUCCESS")
    return {"message": message}

@router.get("/api/backups", summary="列出所有备份")
async def list_backups():
    """获取服务器上所有可用的备份文件列表。"""
    if not globals.backup_service.is_enabled: return []
    return await asyncio.to_thread(globals.backup_service.list_backups)

@router.post("/api/backups/restore/{filename}", summary="恢复系统备份")
async def restore_backup(filename: str, background_tasks: BackgroundTasks, request: Request):
    """从指定的备份文件恢复数据。支持合并或覆盖模式。"""
    mode = request.query_params.get("mode", "merge_add")
    if not globals.backup_service.is_enabled: raise HTTPException(status_code=400, detail="备份服务未启用。")
    if mode not in ["merge_add", "overwrite", "clean_restore"]: raise HTTPException(status_code=400, detail="mode 参数错误")
    success, message = await asyncio.to_thread(globals.backup_service.restore_backup, filename, mode)
    if not success:
        log_audit("备份", "恢复失败", f"文件: {filename}, 模式: {mode}, 错误: {message}", level="ERROR")
        raise HTTPException(status_code=500, detail=message)
    log_audit("备份", "恢复", f"文件: {filename}, 模式: {mode}", level="SUCCESS")
    background_tasks.add_task(globals.service.scanner_service.scan_all_data)
    return {"message": message}

@router.delete("/api/backups/{filename}", summary="删除备份文件")
async def delete_backup(filename: str):
    """从服务器删除指定的备份文件。"""
    success, message = await asyncio.to_thread(globals.backup_service.delete_backup, filename)
    if not success: raise HTTPException(status_code=404, detail=message)
    log_audit("备份", "删除", f"文件: {filename}", level="CLEAN")
    return {"message": message}

# Item-specific Backups

@router.get("/api/items/{item_type}/{item_id}/backups", summary="获取项目备份列表")
async def get_item_backups(item_type: str, item_id: str):
    """获取指定媒体项目的历史备份版本。"""
    if not globals.backup_service.is_enabled:
        return []
    backups = await asyncio.to_thread(globals.backup_service.list_item_backups, item_type, item_id)
    return backups

@router.post("/api/items/{item_type}/{item_id}/backups", summary="创建项目备份")
async def create_item_backup(item_type: str, item_id: str):
    """为指定媒体项目创建当前状态的即时备份。"""
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    success, message = await asyncio.to_thread(globals.backup_service.create_item_backup, item_type, item_id)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    log_audit("备份", "创建项目备份", f"类型: {item_type}, ID: {item_id}", level="SUCCESS")
    return {"message": message, "success": True}

@router.post("/api/items/{item_type}/{item_id}/backups/{backup_name}/restore", summary="恢复项目备份")
async def restore_item_backup(item_type: str, item_id: str, backup_name: str, background_tasks: BackgroundTasks):
    """从选定的历史版本恢复媒体项目的元数据。"""
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    success, message = await asyncio.to_thread(globals.backup_service.restore_item_backup, item_type, item_id, backup_name)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    log_audit("备份", "恢复项目备份", f"类型: {item_type}, ID: {item_id}, 备份: {backup_name}", level="SUCCESS")
    background_tasks.add_task(globals.service.scanner_service.refresh_item_cache, item_type, item_id)
    return {"message": message}

@router.delete("/api/items/{item_type}/{item_id}/backups/{backup_name}", summary="删除项目备份")
async def delete_item_backup(item_type: str, item_id: str, backup_name: str):
    """删除指定的媒体项目备份文件。"""
    success, message = await asyncio.to_thread(globals.backup_service.delete_item_backup, item_type, item_id, backup_name)
    if not success: raise HTTPException(status_code=404, detail=message)
    log_audit("备份", "删除项目备份", f"类型: {item_type}, ID: {item_id}, 备份: {backup_name}", level="CLEAN")
    return {"message": message}

# New Export/Import Endpoints

@router.get("/api/items/{item_type}/{item_id}/export_zip", summary="导出项目压缩包")
async def export_item_zip(item_type: str, item_id: str):
    """
    导出项目的覆盖数据（Override Data）为 ZIP 压缩包供下载。
    """
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    success, file_path, filename = await asyncio.to_thread(globals.backup_service.get_export_zip_path, item_type, item_id)
    
    if not success:
        raise HTTPException(status_code=400, detail=file_path) # file_path contains error message on failure

    log_audit("备份", "导出", f"类型: {item_type}, ID: {item_id}, 文件: {filename}")
    return FileResponse(file_path, filename=filename, media_type='application/zip')

@router.post("/api/backups/import_zip", summary="导入覆盖数据压缩包")
async def import_override_zip(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """
    上传并导入包含覆盖数据（Override Data）的 ZIP 压缩包。
    """
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    # Save uploaded file to temp
    temp_dir = "/tmp/gemini_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        def _save_upload():
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        await asyncio.to_thread(_save_upload)

        success, message = await asyncio.to_thread(globals.backup_service.process_import_zip, temp_file_path, file.filename)
        
        if success and background_tasks:
             background_tasks.add_task(globals.service.scanner_service.scan_all_data)

        if not success:
            log_audit("备份", "导入失败", f"文件: {file.filename}, 错误: {message}", level="ERROR")
            raise HTTPException(status_code=400, detail=message)

        log_audit("备份", "导入", f"文件: {file.filename}", level="SUCCESS")
        return {"message": message, "success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        log_audit("备份", "导入异常", f"文件: {file.filename}, 错误: {str(e)}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

# Collection Export/Import

@router.get("/api/collections/{filename}/export_zip", summary="导出合集压缩包")
async def export_collection_zip(filename: str):
    """
    导出特定的合集数据（包含 JSON 和封面图片）为 ZIP 压缩包。
    """
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    success, file_path, zip_filename = await asyncio.to_thread(globals.backup_service.get_collection_export_zip_path, filename)
    
    if not success:
        raise HTTPException(status_code=400, detail=file_path)

    log_audit("备份", "导出合集", f"文件: {zip_filename}")
    return FileResponse(file_path, filename=zip_filename, media_type='application/zip')

@router.post("/api/collections/import_zip", summary="导入合集压缩包")
async def import_collection_zip(file: UploadFile = File(...)):
    """
    上传并导入合集 ZIP 压缩包。
    """
    if not globals.backup_service.is_enabled:
        raise HTTPException(status_code=400, detail="备份服务未启用。")
    
    temp_dir = "/tmp/gemini_uploads_col"
    os.makedirs(temp_dir, exist_ok=True)
    temp_file_path = os.path.join(temp_dir, file.filename)
    
    try:
        def _save_upload():
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

        await asyncio.to_thread(_save_upload)

        success, message = await asyncio.to_thread(globals.backup_service.process_collection_import_zip, temp_file_path)
        
        if success:
             # Trigger DB sync immediately so frontend gets fresh data
             await globals.collection_service.sync_db_from_disk()

        if not success:
            log_audit("备份", "导入合集失败", f"文件: {file.filename}, 错误: {message}", level="ERROR")
            raise HTTPException(status_code=400, detail=message)

        log_audit("备份", "导入合集", f"文件: {file.filename}", level="SUCCESS")
        return {"message": message, "success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        log_audit("备份", "导入合集异常", f"文件: {file.filename}, 错误: {str(e)}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
