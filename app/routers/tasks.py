from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.future import select
from app import globals
from app.database import TasksSessionLocal
from app.models import ScheduledTask
from app.services.scheduler_service import scheduler_service
from app.logger import log_audit

router = APIRouter(prefix="/api/tasks", tags=["定时任务"])

class TaskCreate(BaseModel):
    name: str
    task_type: str
    cron_expression: str
    enabled: bool = True
    params: str = "{}"

class TaskUpdate(BaseModel):
    name: Optional[str] = None
    task_type: Optional[str] = None
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None
    params: Optional[str] = None

@router.get("", response_model=List[Dict[str, Any]])
async def get_tasks():
    async with TasksSessionLocal() as session:
        result = await session.execute(select(ScheduledTask))
        tasks = result.scalars().all()
        return [t.to_dict() for t in tasks]

@router.post("")
async def create_task(task_in: TaskCreate):
    async with TasksSessionLocal() as session:
        new_task = ScheduledTask(
            name=task_in.name,
            task_type=task_in.task_type,
            cron_expression=task_in.cron_expression,
            enabled=task_in.enabled,
            params=task_in.params
        )
        session.add(new_task)
        await session.commit()
        await session.refresh(new_task)
        
        if new_task.enabled:
            scheduler_service.schedule_task(new_task)

        log_audit("定时任务", "创建", f"任务: {task_in.name}, 类型: {task_in.task_type}, Cron: {task_in.cron_expression}", level="SUCCESS")
        return new_task.to_dict()

@router.patch("/{task_id}")
async def update_task(task_id: int, task_in: TaskUpdate):
    async with TasksSessionLocal() as session:
        task = await session.get(ScheduledTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="未找到任务")
        
        if task_in.name is not None: task.name = task_in.name
        if task_in.task_type is not None: task.task_type = task_in.task_type
        if task_in.cron_expression is not None: task.cron_expression = task_in.cron_expression
        if task_in.enabled is not None: task.enabled = task_in.enabled
        if task_in.params is not None: task.params = task_in.params
        
        await session.commit()
        await session.refresh(task)
        
        if task.enabled:
            scheduler_service.schedule_task(task)
        else:
            job_id = f"task_{task.id}"
            if scheduler_service.scheduler.get_job(job_id):
                scheduler_service.scheduler.remove_job(job_id)

        log_audit("定时任务", "更新", f"ID: {task_id}, 名称: {task.name}, 启用: {task.enabled}")
        return task.to_dict()

@router.delete("/{task_id}")
async def delete_task(task_id: int):
    async with TasksSessionLocal() as session:
        task = await session.get(ScheduledTask, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="未找到任务")
        
        task_name = task.name
        await session.delete(task)
        await session.commit()
        
        job_id = f"task_{task_id}"
        if scheduler_service.scheduler.get_job(job_id):
            scheduler_service.scheduler.remove_job(job_id)

        log_audit("定时任务", "删除", f"ID: {task_id}, 名称: {task_name}", level="CLEAN")
        return {"success": True}

@router.post("/{task_id}/run")
async def run_task_now(task_id: int):
    """立即执行一次任务（无论是否启用）"""
    import asyncio
    log_audit("定时任务", "手动执行", f"ID: {task_id}", level="START")
    asyncio.create_task(scheduler_service.execute_task(task_id, force=True))
    return {"message": "任务已在后台启动"}
