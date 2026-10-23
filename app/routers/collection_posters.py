
from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Union, Dict
from sqlalchemy.future import select
from app.services.collection_poster_service import collection_poster_service
from app.database import CollectionsSessionLocal
from app.models import LocalCollection
from app import globals
from app.logger import log_audit

router = APIRouter(prefix="/api/collection-posters", tags=["合集海报生成"])

class GeneratePosterRequest(BaseModel):
    collection_id: Optional[str] = None
    item_ids: Optional[List[str]] = None
    movie_ids: Optional[List[str]] = None
    series_ids: Optional[List[str]] = None
    titles_map: Optional[Dict[str, List[str]]] = None
    style_type: str
    title_zh: Optional[str] = ""
    title_en: Optional[str] = ""
    show_zh: bool = True
    show_en: bool = True
    font_zh: str
    font_en: str
    zh_font_size_ratio: float = 1.0
    en_font_size_ratio: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    resolution_scale: float = 1.0
    seed: Optional[int] = None
    return_layers: bool = False

@router.post("/generate", summary="生成合集海报")
async def generate_poster(req: GeneratePosterRequest):
    """
    为合集生成海报。支持分层返回或合并返回 Base64 图像。
    """
    final_zh = req.title_zh if req.show_zh else ""
    final_en = req.title_en if req.show_en else ""
    
    result = await collection_poster_service.generate_poster(
        collection_id=req.collection_id,
        item_ids=req.item_ids,
        movie_ids=req.movie_ids,
        series_ids=req.series_ids,
        titles_map=req.titles_map,
        style_type=req.style_type,
        title_zh=final_zh,
        title_en=final_en,
        font_zh=req.font_zh,
        font_en=req.font_en,
        zh_font_size_ratio=req.zh_font_size_ratio,
        en_font_size_ratio=req.en_font_size_ratio,
        offset_x=req.offset_x,
        offset_y=req.offset_y,
        resolution_scale=req.resolution_scale,
        return_layers=req.return_layers,
        seed=req.seed
    )
    
    if not result:
        log_audit("海报", "生成失败", f"合集: {req.collection_id}, 样式: {req.style_type}", level="ERROR")
        raise HTTPException(status_code=500, detail="生成失败，请检查服务器日志。")

    log_audit("海报", "生成", f"合集: {req.collection_id or '自定义'}, 样式: {req.style_type}", level="SUCCESS")
    return result

class BatchGenerateRequest(BaseModel):
    collection_filenames: List[str] = []
    collection_names_str: Optional[str] = None
    style_type: str
    show_zh: bool = True
    show_en: bool = True
    font_zh: str
    font_en: str
    zh_font_size_ratio: float = 1.0
    en_font_size_ratio: float = 1.0
    offset_x: int = 0
    offset_y: int = 0
    resolution_scale: float = 1.0
    seed: Optional[int] = None

@router.post("/batch-generate-bg", summary="批量生成海报 (后台)")
async def batch_generate_poster(req: BatchGenerateRequest, background_tasks: BackgroundTasks):
    """
    在后台触发批量合集海报生成任务。
    支持传入合集文件名列表或合集名称字符串（逗号分隔）。
    """
    target_filenames = list(req.collection_filenames)
    
    if req.collection_names_str:
        names = [n.strip() for n in req.collection_names_str.replace("，", ",").split(",") if n.strip()]
        if names:
            async with CollectionsSessionLocal() as session:
                stmt = select(LocalCollection.filename).where(LocalCollection.collection_name.in_(names))
                result = await session.execute(stmt)
                found = result.scalars().all()
                target_filenames.extend(found)
                
    target_filenames = list(set(target_filenames))
    
    if not target_filenames:
         raise HTTPException(status_code=400, detail="未指定任何合集（请提供文件名列表或合集名称）。")

    log_audit("海报", "批量生成", f"共 {len(target_filenames)} 个合集, 样式: {req.style_type}", level="START")
    params = req.dict(exclude={"collection_filenames", "collection_names_str"})
    background_tasks.add_task(collection_poster_service.batch_generate_posters_task, target_filenames, params)
    return {"message": f"已启动 {len(target_filenames)} 个合集的海报生成任务", "success": True}
