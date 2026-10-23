import asyncio
import json
import httpx
from typing import AsyncGenerator, Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import MediaRelationsSessionLocal, BangumiSessionLocal
from ..models import TmdbBangumiMap, BangumiAppConfig, BangumiDataItem
from ..logger import log_audit


BANGUMI_DATA_URL = "https://unpkg.com/bangumi-data@0.3/dist/data.json"
LONG_ENDED_DAYS = 30


class BangumiDataSyncService:
    def __init__(self):
        self.sync_lock = asyncio.Lock()

    def _format_sse(self, data: Dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    async def sync_bangumi_data(
        self, 
        github_token: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        if self.sync_lock.locked():
            yield self._format_sse({"type": "error", "message": "同步任务正在进行中，请稍后再试。"})
            return

        async with self.sync_lock:
            try:
                yield self._format_sse({"type": "milestone", "message": "开始下载 bangumi-data...", "percentage": 0})
                
                from .. import globals
                timeout_config = httpx.Timeout(60.0, connect=120.0)
                proxy_url = globals.service.configuration_service.get_proxy_url('bangumi')
                
                headers = {'User-Agent': 'Bangumi-Data-Sync/1.0'}
                if github_token:
                    headers["Authorization"] = f"token {github_token}"

                yield self._format_sse({"type": "milestone", "message": "正在从 CDN 获取数据...", "percentage": 10})
                
                async with httpx.AsyncClient(
                    timeout=timeout_config, 
                    proxy=proxy_url,
                    follow_redirects=True
                ) as client:
                    response = await client.get(BANGUMI_DATA_URL, headers=headers)
                    response.raise_for_status()
                    data = response.json()

                total_items = len(data.get('items', []))
                yield self._format_sse({"type": "milestone", "message": f"数据下载完成，共 {total_items} 条记录", "percentage": 30})
                
                yield self._format_sse({"type": "log", "message": "开始解析数据..."})
                
                tmdb_mappings, bgm_items = self._parse_bangumi_data(data)
                
                yield self._format_sse({"type": "milestone", "message": f"解析完成: {len(tmdb_mappings)} 条 TMDB 映射, {len(bgm_items)} 条 BGM 条目", "percentage": 50})
                yield self._format_sse({"type": "log", "message": f"TMDB 映射: {len(tmdb_mappings)} | BGM 条目(含播出日期): {len(bgm_items)}"})
                
                yield self._format_sse({"type": "milestone", "message": "正在写入数据库...", "percentage": 60})
                
                await self._save_mappings_to_db(tmdb_mappings)
                await self._save_bgm_items_to_db(bgm_items)
                
                yield self._format_sse({"type": "milestone", "message": "正在更新版本信息...", "percentage": 90})
                
                await self._update_version_info()
                
                yield self._format_sse({"type": "finished", "message": "bangumi-data 同步完成！", "percentage": 100})
                
            except httpx.HTTPStatusError as e:
                log_audit("BangumiData", "HTTP错误", f"HTTP {e.response.status_code}", level="ERROR")
                yield self._format_sse({"type": "error", "message": f"下载失败: HTTP {e.response.status_code}"})
            except httpx.RequestError as e:
                log_audit("BangumiData", "网络错误", str(e), level="ERROR")
                yield self._format_sse({"type": "error", "message": f"网络错误: {str(e)}"})
            except json.JSONDecodeError as e:
                log_audit("BangumiData", "JSON解析错误", str(e), level="ERROR")
                yield self._format_sse({"type": "error", "message": f"数据解析失败: {str(e)}"})
            except Exception as e:
                log_audit("BangumiData", "同步失败", str(e), level="ERROR")
                yield self._format_sse({"type": "error", "message": f"同步失败: {str(e)}"})

    def _parse_bangumi_data(self, data: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        解析 bangumi-data JSON，返回两个列表:
        1. tmdb_mappings: TMDB-BGM ID 映射
        2. bgm_items: 所有 BGM 条目（含 begin/end/broadcast/title）
        """
        tmdb_mappings = {}
        bgm_items = []
        seen_bgm_ids = set()
        items = data.get('items', [])
        
        for item in items:
            sites = item.get('sites', [])
            
            bangumi_id = None
            tmdb_entries = []
            
            for site in sites:
                site_name = site.get('site', '')
                site_id = site.get('id', '')
                
                if site_name == 'bangumi' and site_id:
                    try:
                        bangumi_id = int(site_id)
                    except (ValueError, TypeError):
                        continue
                
                elif site_name == 'tmdb' and site_id:
                    tmdb_entries.append(site_id)
            
            # 提取 BGM 条目信息（只要有 BGM ID 就记录）
            if bangumi_id and bangumi_id not in seen_bgm_ids:
                seen_bgm_ids.add(bangumi_id)
                
                title = item.get('title', '')
                title_cn = ''
                title_translate = item.get('titleTranslate', {})
                if title_translate:
                    zh_hans = title_translate.get('zh-Hans', [])
                    if zh_hans:
                        title_cn = zh_hans[0]
                
                # 媒体类型
                item_type = item.get('type', 'tv')
                media_type = 'movie' if item_type == 'movie' else 'tv'
                
                # 找到 TMDB ID（如果有）
                tmdb_id_val = None
                for tmdb_id_str in tmdb_entries:
                    parsed = self._parse_tmdb_id(tmdb_id_str)
                    if parsed:
                        tmdb_id_val = parsed[0]
                        break
                
                bgm_items.append({
                    'bgm_id': bangumi_id,
                    'tmdb_id': tmdb_id_val,
                    'media_type': media_type,
                    'title': title,
                    'title_cn': title_cn,
                    'begin': item.get('begin', ''),
                    'end': item.get('end', ''),
                    'broadcast': item.get('broadcast', '')
                })
            
            # 提取 TMDB 映射
            if bangumi_id and tmdb_entries:
                for tmdb_id_str in tmdb_entries:
                    parsed = self._parse_tmdb_id(tmdb_id_str)
                    if parsed:
                        tmdb_id, tmdb_type, season_number = parsed
                        
                        key = (tmdb_id, tmdb_type)
                        if key not in tmdb_mappings:
                            tmdb_mappings[key] = {
                                'tmdb_id': tmdb_id,
                                'tmdb_type': tmdb_type,
                                'season_mappings': {}
                            }
                        
                        season_key = str(season_number) if season_number else '1'
                        if season_key not in tmdb_mappings[key]['season_mappings']:
                            tmdb_mappings[key]['season_mappings'][season_key] = []
                        
                        if bangumi_id not in tmdb_mappings[key]['season_mappings'][season_key]:
                            tmdb_mappings[key]['season_mappings'][season_key].append(bangumi_id)
        
        return list(tmdb_mappings.values()), bgm_items

    def _parse_tmdb_id(self, tmdb_id_str: str) -> Optional[tuple]:
        if not tmdb_id_str:
            return None
        
        tmdb_id_str = tmdb_id_str.strip()
        
        if tmdb_id_str.startswith('tv/'):
            remaining = tmdb_id_str[3:]
        elif tmdb_id_str.startswith('movie/'):
            remaining = tmdb_id_str[6:]
        else:
            return None
        
        parts = remaining.split('/')
        
        try:
            tmdb_id = int(parts[0])
        except (ValueError, TypeError):
            return None
        
        if tmdb_id_str.startswith('tv/'):
            tmdb_type = 'tv'
            season_number = None
            
            if len(parts) >= 3 and parts[1] == 'season':
                try:
                    season_number = int(parts[2])
                except (ValueError, TypeError):
                    season_number = None
            
            return (tmdb_id, tmdb_type, season_number)
        
        elif tmdb_id_str.startswith('movie/'):
            return (tmdb_id, 'movie', None)
        
        return None

    async def _save_mappings_to_db(self, mappings: List[Dict[str, Any]]):
        """保存 TMDB-BGM 映射到 media_relations.db"""
        async with MediaRelationsSessionLocal() as session:
            count = 0
            for mapping in mappings:
                tmdb_id = str(mapping['tmdb_id'])
                tmdb_type = mapping['tmdb_type']
                season_mappings = mapping['season_mappings']
                
                if not season_mappings:
                    continue
                
                for season_str, bgm_ids in season_mappings.items():
                    try:
                        season_number = int(season_str)
                    except (ValueError, TypeError):
                        season_number = 1
                    
                    for bgm_id in bgm_ids:
                        result = await session.execute(
                            select(TmdbBangumiMap).where(
                                TmdbBangumiMap.tmdb_id == tmdb_id,
                                TmdbBangumiMap.tmdb_type == tmdb_type,
                                TmdbBangumiMap.bangumi_id == bgm_id
                            )
                        )
                        existing = result.scalar_one_or_none()
                        
                        if existing:
                            existing.season_number = season_number
                            existing.updated_at = datetime.now()
                        else:
                            new_mapping = TmdbBangumiMap(
                                tmdb_id=tmdb_id,
                                tmdb_type=tmdb_type,
                                bangumi_id=bgm_id,
                                season_number=season_number,
                                status=0,
                                updated_at=datetime.now()
                            )
                            session.add(new_mapping)
                            count += 1
            
            await session.commit()
            log_audit("BangumiData", "保存映射", f"{count} 条新映射记录", level="SUCCESS")

    async def _save_bgm_items_to_db(self, bgm_items: List[Dict[str, Any]]):
        """保存 BGM 条目信息（含 begin/end/broadcast）到 bangumi.db，全量覆盖"""
        now = datetime.now()
        async with BangumiSessionLocal() as session:
            # 清空旧数据
            await session.execute(delete(BangumiDataItem))
            
            # 批量写入
            for item in bgm_items:
                record = BangumiDataItem(
                    bgm_id=item['bgm_id'],
                    tmdb_id=item['tmdb_id'],
                    media_type=item['media_type'],
                    title=item['title'],
                    title_cn=item['title_cn'],
                    begin=item['begin'] or None,
                    end=item['end'] or None,
                    broadcast=item['broadcast'] or None,
                    updated_at=now
                )
                session.add(record)
            
            await session.commit()
            log_audit("BangumiData", "保存条目", f"{len(bgm_items)} 条 BGM 条目", level="SUCCESS")

    async def _update_version_info(self):
        async with BangumiSessionLocal() as session:
            result = await session.execute(
                select(BangumiAppConfig).where(
                    BangumiAppConfig.key == "bangumi_data_sync_version"
                )
            )
            config = result.scalar_one_or_none()
            
            version_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if config:
                config.value = version_str
            else:
                new_config = BangumiAppConfig(
                    key="bangumi_data_sync_version",
                    value=version_str
                )
                session.add(new_config)
            
            await session.commit()

    async def get_sync_version(self) -> str:
        try:
            async with BangumiSessionLocal() as session:
                result = await session.execute(
                    select(BangumiAppConfig.value).where(
                        BangumiAppConfig.key == "bangumi_data_sync_version"
                    )
                )
                version = result.scalar_one_or_none()
                return version or "从未同步"
        except Exception as e:
            log_audit("Bangumi", "失败", f"获取同步版本失败: {e}", level="ERROR")
            return "未知"

    async def is_long_ended(self, bgm_id: int, days: int = LONG_ENDED_DAYS) -> bool:
        """
        判断指定 BGM ID 对应的番剧是否已完结超过指定天数。
        依据 bangumi_data_item.end 字段与当前时间比较。
        """
        try:
            async with BangumiSessionLocal() as session:
                result = await session.execute(
                    select(BangumiDataItem.end).where(BangumiDataItem.bgm_id == bgm_id)
                )
                end_str = result.scalar()
        except Exception as e:
            log_audit("Bangumi", "查询", f"查询 end 列异常: {e}", level="WARN")
            return False

        if not end_str:
            return False

        try:
            end_str = str(end_str).strip()
            if end_str.endswith("Z"):
                end_str = end_str[:-1] + "+00:00"
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                from datetime import timezone
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            from datetime import timezone
            now_utc = datetime.now(timezone.utc)
            return now_utc >= end_dt + timedelta(days=days)
        except Exception as e:
            log_audit("Bangumi", "失败", f"解析 end 时间失败 ({end_str}): {e}", level="WARN")
            return False

    async def run_scheduled_sync(self, github_token: Optional[str] = None) -> bool:
        """用于调度器调用的同步方法（非 SSE），返回是否成功"""
        if self.sync_lock.locked():
            log_audit("BangumiData", "跳过同步", "任务正在进行中", level="WARN")
            return False

        async with self.sync_lock:
            try:
                log_audit("BangumiData", "定时同步", "开始定时同步任务", level="START")
                
                from .. import globals
                timeout_config = httpx.Timeout(60.0, connect=120.0)
                proxy_url = globals.service.configuration_service.get_proxy_url('bangumi')
                
                headers = {'User-Agent': 'Bangumi-Data-Sync/1.0'}
                if github_token:
                    headers["Authorization"] = f"token {github_token}"

                async with httpx.AsyncClient(
                    timeout=timeout_config, 
                    proxy=proxy_url,
                    follow_redirects=True
                ) as client:
                    response = await client.get(BANGUMI_DATA_URL, headers=headers)
                    response.raise_for_status()
                    data = response.json()

                log_audit("Bangumi", "完成", f"数据下载完成，共 {len(data.get('items', []))} 条记录")
                tmdb_mappings, bgm_items = self._parse_bangumi_data(data)
                log_audit("Bangumi", "完成", f"解析完成: {len(tmdb_mappings)} 条 TMDB 映射, {len(bgm_items)} 条 BGM 条目")
                await self._save_mappings_to_db(tmdb_mappings)
                await self._save_bgm_items_to_db(bgm_items)
                await self._update_version_info()
                
                log_audit("BangumiData", "同步完成", "定时同步完成", level="DONE")
                return True
                
            except Exception as e:
                log_audit("BangumiData", "同步失败", str(e), level="ERROR")
                return False
