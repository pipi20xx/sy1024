import json
import httpx
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator, Tuple, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..common import get_config_path
from .. import globals
from ..models import TmdbApiResponse
from ..database import TmdbCacheSessionLocal
from ..logger import log_audit


class TmdbCacheService:
    def __init__(self):
        self.db_path = get_config_path('tmdb_api_cache.db')

    async def save_entity(self, tmdb_id: str, tmdb_type: str, name_cn: str, original_json: Dict[str, Any]):
        """Save TMDB entity details to cache."""
        try:
            async with TmdbCacheSessionLocal() as session:
                entity = await session.get(TmdbApiResponse, (str(tmdb_id), tmdb_type))
                if entity:
                    entity.name_cn = name_cn
                    entity.original_json = json.dumps(original_json, ensure_ascii=False)
                    entity.updated_at = datetime.now()
                else:
                    entity = TmdbApiResponse(
                        tmdb_id=str(tmdb_id),
                        tmdb_type=tmdb_type,
                        name_cn=name_cn,
                        original_json=json.dumps(original_json, ensure_ascii=False),
                        updated_at=datetime.now()
                    )
                    session.add(entity)
                await session.commit()
        except Exception as e:
            log_audit("缓存", "失败", f"保存 TMDB 缓存失败: {e}", level="ERROR")
    async def get_entity(self, tmdb_id: str, tmdb_type: str) -> Optional[Dict[str, Any]]:
        """Retrieve TMDB entity details from cache."""
        try:
            async with TmdbCacheSessionLocal() as session:
                entity = await session.get(TmdbApiResponse, (str(tmdb_id), tmdb_type))
                if entity:
                    return {
                        "tmdb_id": entity.tmdb_id,
                        "tmdb_type": entity.tmdb_type,
                        "name_cn": entity.name_cn,
                        "original_json": json.loads(entity.original_json) if entity.original_json else None,
                        "updated_at": entity.updated_at
                    }
                return None
        except Exception as e:
            log_audit("缓存", "失败", f"获取 TMDB 缓存失败: {e}", level="ERROR")
            return None

    async def get_entities_batch(self, targets: List[Tuple[str, str]]) -> Dict[str, Dict[str, Any]]:
        """Batch retrieve entities. targets is list of (id, type). Returns dict key="id_type" -> entity"""
        if not targets:
            return {}
        
        try:
            async with TmdbCacheSessionLocal() as session:
                result = {}
                chunk_size = 900
                
                for i in range(0, len(targets), chunk_size):
                    chunk = targets[i:i+chunk_size]
                    tmdb_ids = [str(t[0]) for t in chunk]
                    tmdb_types = [t[1] for t in chunk]
                    
                    stmt = select(TmdbApiResponse).where(
                        TmdbApiResponse.tmdb_id.in_(tmdb_ids)
                    )
                    
                    db_result = await session.execute(stmt)
                    entities = db_result.scalars().all()
                    
                    for entity in entities:
                        key = f"{entity.tmdb_id}_{entity.tmdb_type}"
                        result[key] = {
                            "tmdb_id": entity.tmdb_id,
                            "tmdb_type": entity.tmdb_type,
                            "name_cn": entity.name_cn,
                            "original_json": json.loads(entity.original_json) if entity.original_json else None,
                            "updated_at": entity.updated_at
                        }
                
                return result
        except Exception as e:
            log_audit("缓存", "失败", f"批量获取缓存错误: {e}", level="ERROR")
            return {}

    async def exists(self, tmdb_id: str, tmdb_type: str) -> bool:
        """Check if entity exists in cache."""
        try:
            async with TmdbCacheSessionLocal() as session:
                entity = await session.get(TmdbApiResponse, (str(tmdb_id), tmdb_type))
                return entity is not None
        except Exception:
            return False

    async def search_by_name_cn(self, name_pattern: str, limit: int = 100) -> List[str]:
        """Search TMDB IDs by Chinese name pattern."""
        try:
            async with TmdbCacheSessionLocal() as session:
                stmt = select(TmdbApiResponse.tmdb_id).where(
                    TmdbApiResponse.name_cn.like(f"%{name_pattern}%")
                ).limit(limit)
                result = await session.execute(stmt)
                return [row[0] for row in result.scalars().all()]
        except Exception as e:
            log_audit("缓存", "失败", f"搜索 TMDB 缓存失败: {e}", level="ERROR")
            return []

    async def refresh_cache(self, mode: str = 'incremental') -> AsyncGenerator[Dict[str, Any], None]:
        """
        Refresh TMDB cache by fetching data from TMDB API.
        mode: 'incremental' (skip existing) or 'overwrite' (force update all)
        """
        # 1. Get TMDB API Key
        tmdb_key = globals.service.configuration_service.get_config().get("tmdb_api_key")
        if not tmdb_key:
            yield {"type": "error", "message": "未配置 TMDB API Key，无法刷新缓存"}
            return

        # 2. Get all distinct TMDB IDs from relation DB
        targets = [] # List of (id, type)
        try:
            from ..database import MediaRelationsSessionLocal
            from ..models import TmdbBangumiMap
            async with MediaRelationsSessionLocal() as session:
                stmt = select(TmdbBangumiMap.tmdb_id, TmdbBangumiMap.tmdb_type).distinct()
                result = await session.execute(stmt)
                targets = result.fetchall()
        except Exception as e:
            yield {"type": "error", "message": f"读取关联数据库失败: {e}"}
            return

        total = len(targets)
        updated = 0
        skipped = 0
        errors = 0
        processed = 0
        
        proxy_url = globals.service.configuration_service.get_proxy_url('tmdb')
        proxies = {"http://": proxy_url, "https://": proxy_url} if proxy_url else None
        if proxy_url:
            log_audit("缓存", "处理", f"[Proxy] TMDB 缓存刷新 (httpx) 将通过代理: {proxy_url}")
        async with httpx.AsyncClient(timeout=20.0, proxy=proxy_url) as client:
            for tmdb_id, tmdb_type in targets:
                processed += 1
                
                # Check cache existence for incremental mode
                if mode == 'incremental' and await self.exists(tmdb_id, tmdb_type):
                    skipped += 1
                    if processed % 10 == 0:
                        yield {"type": "progress", "processed": processed, "total": total, "updated": updated, "skipped": skipped}
                    continue

                # Fetch from TMDB API
                # Type mapping: 'tv' -> 'tv', 'movie' -> 'movie'
                # But relations DB might store 'tv' or 'movie' directly (from my prev update).
                # Just in case, ensure lower case.
                api_type = tmdb_type.lower()
                if api_type not in ['tv', 'movie']:
                    # Maybe legacy data? Skip.
                    continue

                url = f"https://api.themoviedb.org/3/{api_type}/{tmdb_id}"
                params = {"api_key": tmdb_key, "language": "zh-CN"}
                
                try:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get('title') or data.get('name')
                        await self.save_entity(tmdb_id, tmdb_type, title, data)
                        updated += 1
                        yield {"type": "log", "message": f"已缓存: {title} ({tmdb_type}/{tmdb_id})"}
                    elif resp.status_code == 404:
                        errors += 1
                        yield {"type": "log", "message": f"TMDB未找到: {tmdb_type}/{tmdb_id}"}
                    else:
                        errors += 1
                        yield {"type": "log", "message": f"API错误 {resp.status_code}: {tmdb_type}/{tmdb_id}"}
                except Exception as e:
                    errors += 1
                    log_audit("缓存", "失败", f"刷新 {tmdb_id} 缓存出错: {e}", level="ERROR")
                if processed % 5 == 0:
                    yield {"type": "progress", "processed": processed, "total": total, "updated": updated, "skipped": skipped, "errors": errors}
                
                # Rate limit
                await asyncio.sleep(0.2)

        yield {"type": "finished", "total": total, "updated": updated, "skipped": skipped, "errors": errors}
