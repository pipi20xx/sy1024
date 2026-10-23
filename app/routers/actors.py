from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from typing import Optional, List, Dict, Any
from .. import globals
from ..database import ActorsSessionLocal
from app.logger import logger, log_audit

router = APIRouter(prefix="/api/actors", tags=["actors"])

@router.get("", summary="获取所有演员")
async def get_actors(request: Request, search: Optional[str] = None, duplicate_type: Optional[str] = None, page: int = 1, page_size: int = 50):
    """分页获取演员列表，支持搜索和重复项查询。"""
    return await globals.service.actor_service.get_actors(search=search, duplicate_type=duplicate_type, page=page, page_size=page_size)

@router.post("/update-from-tmdb", summary="从 TMDB 更新演员信息")
async def update_actors_from_tmdb(actor_ids: List[int], background_tasks: BackgroundTasks):
    """批量或单个从 TMDB 更新演员的姓名和原名 (后台执行)。"""
    log_audit("演员", "更新", f"收到更新 {len(actor_ids)} 位演员的请求")
    background_tasks.add_task(globals.service.actor_service.update_actors_from_tmdb, actor_ids)
    return {"message": f"已启动 {len(actor_ids)} 位演员的更新任务", "success": True}

@router.post("/update-all-from-tmdb", summary="全量后台更新演员信息")
async def update_all_actors_from_tmdb(background_tasks: BackgroundTasks):
    """启动后台任务，更新数据库中所有演员。"""
    log_audit("演员", "更新", "收到全量更新所有演员的请求")
    background_tasks.add_task(globals.service.actor_service.update_all_actors_from_tmdb_task)
    return {"message": "全量更新任务已在后台启动", "success": True}

@router.get("/{actor_id}", summary="获取演员详情")
async def get_actor_detail(actor_id: int):
    """获取单个演员的完整信息（含元数据 JSON）。"""
    async with ActorsSessionLocal() as session:
        from sqlalchemy import select
        from ..models import Actor
        stmt = select(Actor).where(Actor.id == actor_id)
        result = await session.execute(stmt)
        actor = result.scalar_one_or_none()
        if not actor:
            raise HTTPException(status_code=404, detail="未找到该演员")
        return actor.to_dict()

@router.post("/{actor_id}/refresh-from-tmdb", summary="同步从 TMDB 刷新单个演员")
async def refresh_actor_from_tmdb(actor_id: int):
    """同步从 TMDB 获取演员信息并返回更新后的完整数据。"""
    from sqlalchemy import select
    from ..models import Actor
    # 先确认演员存在
    async with ActorsSessionLocal() as session:
        stmt = select(Actor).where(Actor.id == actor_id)
        result = await session.execute(stmt)
        actor = result.scalar_one_or_none()
        if not actor:
            raise HTTPException(status_code=404, detail="未找到该演员")

    log_audit("演员", "更新", f"同步刷新演员: ID {actor_id} (TMDB: {actor.tmdb_id})")
    # 同步调用更新逻辑（不通过 BackgroundTasks）
    success_count, fail_count = await globals.service.actor_service.update_actors_from_tmdb([actor_id])

    if fail_count > 0 and success_count == 0:
        raise HTTPException(status_code=500, detail="从 TMDB 获取失败")

    # 返回更新后的数据
    async with ActorsSessionLocal() as session:
        stmt = select(Actor).where(Actor.id == actor_id)
        result = await session.execute(stmt)
        actor = result.scalar_one_or_none()
        if not actor:
            raise HTTPException(status_code=404, detail="未找到该演员")
        return actor.to_dict()

@router.get("/tmdb/{tmdb_id}", summary="按 TMDB ID 获取演员详情")
async def get_actor_by_tmdb_id(tmdb_id: int):
    """按 TMDB ID 获取演员完整信息（含元数据 JSON）。"""
    async with ActorsSessionLocal() as session:
        from sqlalchemy import select
        from ..models import Actor
        stmt = select(Actor).where(Actor.tmdb_id == tmdb_id).order_by(Actor.id.asc())
        result = await session.execute(stmt)
        actor = result.scalars().first()
        if not actor:
            raise HTTPException(status_code=404, detail="未找到该演员")
        return actor.to_dict()

@router.post("/tmdb/{tmdb_id}", summary="按 TMDB ID 创建/获取演员")
async def create_or_get_actor_by_tmdb_id(tmdb_id: int):
    """如果演员不存在则从 TMDB 创建，然后同步拉取完整元数据并返回。"""
    from sqlalchemy import select
    from ..models import Actor
    import json as _json

    # 1. 检查是否已存在
    async with ActorsSessionLocal() as session:
        stmt = select(Actor).where(Actor.tmdb_id == tmdb_id).order_by(Actor.id.asc())
        result = await session.execute(stmt)
        actor = result.scalars().first()
        if actor:
            actor_id = actor.id
        else:
            # 2. 先从 TMDB 获取基本信息来创建记录
            log_audit("演员", "创建", f"从 TMDB 创建演员: TMDB ID {tmdb_id}")
            data = await globals.service.tmdb_metadata_service.fetch_tmdb_data("person", str(tmdb_id), "zh-CN")
            tmdb_main_name = data.get('name', '')
            origin_name = globals.service.actor_service.get_origin_name_smart(data)

            new_actor = Actor(
                tmdb_id=tmdb_id,
                name=tmdb_main_name,
                original_name=origin_name,
                profile_path=data.get('profile_path', ''),
                metadata_json=_json.dumps(data, ensure_ascii=False),
            )
            session.add(new_actor)
            await session.commit()
            await session.refresh(new_actor)
            actor_id = new_actor.id
            log_audit("演员", "创建", f"✅ 已创建演员: {tmdb_main_name} (ID: {actor_id})")

    # 3. 同步刷新（拉取 translations 等完整数据）
    success_count, fail_count = await globals.service.actor_service.update_actors_from_tmdb([actor_id])

    # 4. 返回最新数据
    async with ActorsSessionLocal() as session:
        stmt = select(Actor).where(Actor.id == actor_id)
        result = await session.execute(stmt)
        actor = result.scalar_one_or_none()
        if not actor:
            raise HTTPException(status_code=404, detail="未找到该演员")
        return actor.to_dict()

@router.delete("/{actor_id}", summary="删除演员条目")
async def delete_actor(actor_id: int):
    """从数据库中删除一个演员条目。"""
    log_audit("演员", "清理", f"收到删除演员请求: ID {actor_id}")
    await globals.service.actor_service.delete_actor(actor_id)
    return {"message": "Actor deleted successfully"}

@router.delete("", summary="删除所有演员")
async def delete_all_actors():
    """从数据库中删除所有演员条目。"""
    log_audit("演员", "处理", "收到清空所有演员数据的请求")
    await globals.service.actor_service.delete_all_actors()
    return {"message": "All actors deleted successfully"}

@router.put("/{actor_id}", summary="更新演员信息")
async def update_actor(actor_id: int, data: Dict[str, Any]):
    """更新数据库中的演员信息。"""
    log_audit("演员", "更新", f"收到更新演员请求: ID {actor_id}")
    success, result = await globals.service.actor_service.update_actor(actor_id, data)
    if not success:
        raise HTTPException(status_code=404, detail=str(result))
    return result

@router.get("/merge/preview", summary="获取合并预览")
async def merge_preview(type: str):
    """根据类型（tmdb_id, name, original_name）获取重复项及建议的合并方案。"""
    return await globals.service.actor_service.prepare_merge(type)

@router.post("/merge/execute", summary="执行合并")
async def merge_execute(plan: List[Dict[str, Any]]):
    """确认并执行合并方案。"""
    log_audit("演员", "处理", f"收到合并演员请求: 包含 {len(plan)} 个合并组")
    success, message = await globals.service.actor_service.execute_merge(plan)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"message": message}

@router.post("/import-from-override", summary="从覆盖缓存导入演员")
async def import_actors_from_override():
    """触发从覆盖缓存（override）批量导入演员到 actors.db 数据库的功能 (同步)。"""
    success, message = await globals.service.editor_service.import_actors_from_override_cache()
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"message": message}

@router.post("/import-from-override-bg", summary="后台导入演员")
async def import_actors_from_override_bg(background_tasks: BackgroundTasks):
    """触发从覆盖缓存（override）批量导入演员到 actors.db 数据库的功能 (后台任务)。"""
    background_tasks.add_task(globals.service.editor_service.import_actors_from_override_cache_task)
    return {"message": "Import task started in background", "success": True}

@router.post("/update-override", summary="一键更新 Override 文件")
async def update_actors_override(background_tasks: BackgroundTasks):
    """根据数据库中的标准，强制更新本地所有 JSON 文件中的演员信息。"""
    background_tasks.add_task(globals.service.editor_service.apply_actor_standards_to_overrides_task)
    return {"message": "Update task started in background", "success": True}
