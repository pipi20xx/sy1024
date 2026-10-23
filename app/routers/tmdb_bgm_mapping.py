from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from .. import globals
from ..logger import log_audit
from ..schemas.tmdb_bgm_mapping import (
    TmdbBgmMappingItem,
    TmdbBgmMappingList,
    DiffItem,
    ImportDiffRequest,
    ImportDiffResponse,
    ApplyImportRequest,
    TmdbBgmMappingUpdate
)


router = APIRouter(prefix="/api/tmdb-bgm-mapping", tags=["TMDB-BGM映射管理"])


@router.get("/list", summary="获取所有映射")
async def get_mappings(
    search: Optional[str] = None,
    tmdb_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 60,
):
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")
    
    try:
        result = await globals.tmdb_bgm_mapping_service.load_mappings(
            search=search,
            tmdb_type=tmdb_type,
            page=page,
            page_size=page_size,
        )
        return result
    except Exception as e:
        log_audit("映射", "查询", f"获取映射列表失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="获取映射失败")


@router.get("/export", summary="导出映射")
async def export_mappings():
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")
    
    try:
        data = await globals.tmdb_bgm_mapping_service.export_mappings()
        log_audit("映射", "导出", f"已导出 {len(data)} 条映射数据", level="SUCCESS")
        return JSONResponse(content=data)
    except Exception as e:
        log_audit("映射", "导出", f"导出映射失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="导出映射失败")


@router.post("/import/diff", summary="导入并比对差异")
async def import_diff(request: ImportDiffRequest):
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")
    
    try:
        result = await globals.tmdb_bgm_mapping_service.import_and_diff(request.import_data)
        log_audit("映射", "导入", f"导入差异比对完成: 新增 {result.stats.get('new', 0)} / 修改 {result.stats.get('modified', 0)} / 删除 {result.stats.get('deleted', 0)} / 未变 {result.stats.get('unchanged', 0)}")
        return result
    except Exception as e:
        log_audit("映射", "导入", f"导入差异比对失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="导入差异比对失败")


@router.post("/import/apply", summary="应用导入")
async def apply_import(request: ApplyImportRequest):
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")
    
    try:
        success = await globals.tmdb_bgm_mapping_service.apply_import(request.selected_diff_items)
        if not success:
            log_audit("映射", "导入", "应用导入失败", level="ERROR")
            raise HTTPException(status_code=500, detail="应用导入失败")
        
        log_audit("映射", "导入", f"已应用 {len(request.selected_diff_items)} 条导入差异", level="SUCCESS")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        log_audit("映射", "导入", f"应用导入失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="应用导入失败")


@router.post("/update", summary="更新映射")
async def update_mapping(item: TmdbBgmMappingUpdate):
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")
    
    try:
        await globals.tmdb_bgm_mapping_service.update_mapping(item)
        log_audit("映射", "更新", f"已更新映射: TMDB {item.tmdb_id} ({item.tmdb_type})", level="SUCCESS")
        return {"message": "映射已成功保存"}
    except Exception as e:
        log_audit("映射", "更新", f"更新映射失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="更新映射失败")


@router.delete("/delete", summary="删除映射")
async def delete_mapping(tmdb_id: int, tmdb_type: str):
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")

    try:
        await globals.tmdb_bgm_mapping_service.delete_mapping(tmdb_id, tmdb_type)
        log_audit("映射", "删除", f"已删除映射: TMDB {tmdb_id} ({tmdb_type})", level="CLEAN")
        return {"message": "映射已成功删除"}
    except Exception as e:
        log_audit("映射", "删除", f"删除映射失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="删除映射失败")


@router.delete("/clear-all", summary="清除所有映射")
async def clear_all_mappings():
    if not globals.tmdb_bgm_mapping_service:
        raise HTTPException(status_code=503, detail="TMDB-BGM映射服务未初始化")

    try:
        await globals.tmdb_bgm_mapping_service.clear_all_mappings()
        log_audit("映射", "清除", "已清除所有映射", level="CLEAN")
        return {"message": "所有映射已成功清除"}
    except Exception as e:
        log_audit("映射", "清除", f"清除所有映射失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail="清除所有映射失败")
