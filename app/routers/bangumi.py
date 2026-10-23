from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from .. import globals
from typing import Optional, List
import asyncio

from ..services.bangumi_provider import BangumiProvider
from ..logger import log_audit


router = APIRouter(prefix="/api/bangumi", tags=["Bangumi 管理"])

class SchedulerConfig(BaseModel):
    enabled: bool = True
    interval_days: int = 7
    hour: int = 3
    minute: int = 0
    github_token: Optional[str] = None
    class Config:
        extra = "allow"

@router.get("/config", summary="获取调度配置")
async def get_scheduler_config():
    """获取当前的 Bangumi 自动同步调度器配置。"""
    if not globals.bangumi_service:
        raise HTTPException(status_code=503, detail="Bangumi 服务未初始化")
    return await globals.bangumi_service.get_scheduler_config()

@router.post("/config", summary="更新调度配置")
async def update_scheduler_config(config: SchedulerConfig):
    """更新 Bangumi 自动同步调度器配置。"""
    if not globals.bangumi_service:
        raise HTTPException(status_code=503, detail="Bangumi 服务未初始化")
    globals.bangumi_service.update_scheduler_config(config.dict())
    return {"status": "success"}

@router.post("/batch-details", summary="批量获取 Bangumi 条目详情")
async def get_batch_bangumi_details(bgm_ids: List[int]):
    """
    批量获取 Bangumi 条目详情（走统一 BangumiProvider 入口，带缓存）。
    返回 [{id, name, name_cn, date, eps}, ...]
    """
    provider = BangumiProvider()
    results = []

    async def _fetch_one(bgm_id: int):
        try:
            resp = await provider.get_subject(bgm_id)
            subject = resp.get("data")
            if subject:
                return {
                    "id": bgm_id,
                    "name": subject.get("name", ""),
                    "name_cn": subject.get("name_cn", ""),
                    "date": subject.get("date", ""),
                    "eps": subject.get("eps"),
                }
        except Exception as e:
            log_audit("Bangumi", "失败", f"获取 BGM {bgm_id} 详情失败: {e}", level="WARN")
        return {"id": bgm_id, "name": "", "name_cn": "", "date": "", "eps": None}

    # 并发获取，限制 8 并发
    tasks = [_fetch_one(bid) for bid in bgm_ids]
    results = await asyncio.gather(*tasks)
    return list(results)
