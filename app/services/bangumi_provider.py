import json
import httpx
import os
import time
from collections import OrderedDict
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from ..common import get_config_path
from ..database import BangumiCacheSessionLocal, BangumiSessionLocal
from ..models import BangumiSubjectCache, BangumiTempCache, BangumiDataItem
from ..logger import log_audit


# 临时缓存默认有效期（天）
TEMP_CACHE_DAYS = 7
# L1 内存缓存有效期（秒）
L1_CACHE_TTL = 300  # 5 分钟
# L1 内存缓存最大条目数，防止无限增长
L1_CACHE_MAX_SIZE = 200
# 判断"已完结"的阈值（天）：end 日期距今超过此天数视为永久完结
LONG_ENDED_DAYS = 30

# 数据来源标签映射
SOURCE_LABELS: Dict[str, str] = {
    "l1": "L1内存缓存",
    "permanent": "永久缓存(完结)",
    "temp": "临时缓存(未完结)",
    "api": "API实时获取",
    "miss": "未获取到数据",
}


class BangumiProvider:
    """
    Bangumi API 统一入口，带分表缓存策略：
      - 完结番剧 → BangumiSubjectCache（永久缓存）
      - 未完结/未知 → BangumiTempCache（临时缓存，带 expire_at）
      - L1 内存缓存 → 5 分钟 TTL，减少 DB 查询

    所有公共方法返回 {"data": ..., "source": ...} 包装：
      - source 值: "l1" | "permanent" | "temp" | "api" | "miss"
      - 调用方可通过 SOURCE_LABELS 映射为中文标签
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BangumiProvider, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.config_path = get_config_path('bgm_manager.json')
        # L1 内存缓存: OrderedDict[bgm_id] = (timestamp, subject, episodes, characters)
        # 使用 OrderedDict 实现 LRU，限制最大条目数防止内存无限增长
        self._l1_cache: OrderedDict[int, Tuple[float, Optional[Dict], Optional[List], Optional[List]]] = OrderedDict()
        self._initialized = True

    # ============================== Token & Proxy ==============================

    def _load_token(self) -> Optional[str]:
        # 优先从系统设置读取
        try:
            from .. import globals
            if globals.service and globals.service.configuration_service:
                token = globals.service.configuration_service.get_config().get("bangumi_access_token")
                if token:
                    return token
        except Exception:
            pass
        # 兼容旧配置文件中的 token（迁移用）
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('sync_config', {}).get('access_token')
            except Exception:
                pass
        return None

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "Gemini-CLI/1.0 (contact@example.com)",
            "Accept": "application/json"
        }
        token = self._load_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get_proxy(self) -> Optional[str]:
        try:
            from .. import globals
            if globals.service:
                return globals.service.configuration_service.get_proxy_url('bangumi')
        except Exception:
            pass
        return None

    @staticmethod
    def get_source_label(source: str) -> str:
        """将 source 代码映射为中文标签"""
        return SOURCE_LABELS.get(source, source)

    # ============================== L1 Memory Cache ==============================

    def _l1_get(self, bgm_id: int) -> Tuple[Optional[Dict], Optional[List], Optional[List]]:
        """返回 (subject, episodes, characters)，如果 L1 未命中或过期则返回 (None, None, None)"""
        entry = self._l1_cache.get(bgm_id)
        if not entry:
            return None, None, None
        ts, subject, episodes, characters = entry
        if (time.time() - ts) > L1_CACHE_TTL:
            del self._l1_cache[bgm_id]
            return None, None, None
        # 命中时移到末尾，实现 LRU 顺序
        self._l1_cache.move_to_end(bgm_id)
        return subject, episodes, characters

    def _l1_set(self, bgm_id: int, subject: Optional[Dict], episodes: Optional[List], characters: Optional[List]):
        # 如果已存在，先删除再插入（更新位置到末尾）
        if bgm_id in self._l1_cache:
            del self._l1_cache[bgm_id]
        self._l1_cache[bgm_id] = (
            time.time(),
            subject, episodes, characters
        )
        # 超过最大容量时，淘汰最久未使用的条目
        while len(self._l1_cache) > L1_CACHE_MAX_SIZE:
            self._l1_cache.popitem(last=False)

    def _l1_invalidate(self, bgm_id: int):
        self._l1_cache.pop(bgm_id, None)

    # ============================== 完结判断 ==============================

    async def _is_long_ended(self, bgm_id: int) -> bool:
        """
        判断指定 BGM ID 是否已完结超过 LONG_ENDED_DAYS 天。
        依据 BangumiDataItem.end 字段。
        """
        try:
            async with BangumiSessionLocal() as session:
                result = await session.execute(
                    select(BangumiDataItem.end).where(BangumiDataItem.bgm_id == bgm_id)
                )
                end_str = result.scalar()
        except Exception as e:
            log_audit("Bangumi", "查询", f"查询 end 列异常 (bgm_id={bgm_id}): {e}", level="WARN")
            return False

        if not end_str:
            return False

        try:
            end_str = str(end_str).strip()
            if end_str.endswith("Z"):
                end_str = end_str[:-1] + "+00:00"
            end_dt = datetime.fromisoformat(end_str)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            return now_utc >= end_dt + timedelta(days=LONG_ENDED_DAYS)
        except Exception as e:
            log_audit("Bangumi", "失败", f"解析 end 时间失败 (bgm_id={bgm_id}, end='{end_str}'): {e}", level="WARN")
            return False

    # ============================== DB Cache Read ==============================

    async def _db_get(self, bgm_id: int) -> Tuple[Optional[Dict], Optional[List], Optional[List], bool]:
        """
        从数据库缓存中读取。
        返回 (subject, episodes, characters, is_permanent)。
        如果缓存未命中或临时缓存已过期，返回 (None, None, None, False)。
        """
        # 1. 先查永久缓存
        try:
            async with BangumiCacheSessionLocal() as session:
                result = await session.execute(
                    select(BangumiSubjectCache).where(BangumiSubjectCache.bgm_id == bgm_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    subject = json.loads(row.subject_json) if row.subject_json else None
                    episodes = json.loads(row.episodes_json) if row.episodes_json else None
                    characters = json.loads(row.characters_json) if row.characters_json else None
                    return subject, episodes, characters, True
        except Exception as e:
            log_audit("Bangumi", "失败", f"读取永久缓存失败 (bgm_id={bgm_id}): {e}", level="WARN")
        # 2. 再查临时缓存（检查过期）
        try:
            async with BangumiCacheSessionLocal() as session:
                result = await session.execute(
                    select(BangumiTempCache).where(BangumiTempCache.bgm_id == bgm_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    now_utc = datetime.now(timezone.utc)
                    expire_at = row.expire_at
                    if expire_at:
                        if expire_at.tzinfo is None:
                            expire_at = expire_at.replace(tzinfo=timezone.utc)
                        if now_utc > expire_at:
                            # 已过期，删除
                            await session.delete(row)
                            await session.commit()
                            return None, None, None, False
                    subject = json.loads(row.subject_json) if row.subject_json else None
                    episodes = json.loads(row.episodes_json) if row.episodes_json else None
                    characters = json.loads(row.characters_json) if row.characters_json else None
                    return subject, episodes, characters, False
        except Exception as e:
            log_audit("Bangumi", "失败", f"读取临时缓存失败 (bgm_id={bgm_id}): {e}", level="WARN")
        return None, None, None, False

    # ============================== DB Cache Write ==============================

    async def _db_save(self, bgm_id: int, subject: Optional[Dict], episodes: Optional[List], characters: Optional[List], is_permanent: bool):
        """保存到对应的缓存表"""
        now_utc = datetime.now(timezone.utc)
        subject_str = json.dumps(subject, ensure_ascii=False) if subject else None
        episodes_str = json.dumps(episodes, ensure_ascii=False) if episodes else None
        characters_str = json.dumps(characters, ensure_ascii=False) if characters else None

        if is_permanent:
            try:
                async with BangumiCacheSessionLocal() as session:
                    existing = await session.get(BangumiSubjectCache, bgm_id)
                    if existing:
                        existing.subject_json = subject_str
                        existing.episodes_json = episodes_str
                        existing.characters_json = characters_str
                        existing.fetched_at = now_utc
                    else:
                        session.add(BangumiSubjectCache(
                            bgm_id=bgm_id,
                            subject_json=subject_str,
                            episodes_json=episodes_str,
                            characters_json=characters_str,
                            fetched_at=now_utc
                        ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"写入永久缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")
        else:
            expire_at = now_utc + timedelta(days=TEMP_CACHE_DAYS)
            try:
                async with BangumiCacheSessionLocal() as session:
                    existing = await session.get(BangumiTempCache, bgm_id)
                    if existing:
                        existing.subject_json = subject_str
                        existing.episodes_json = episodes_str
                        existing.characters_json = characters_str
                        existing.fetched_at = now_utc
                        existing.expire_at = expire_at
                    else:
                        session.add(BangumiTempCache(
                            bgm_id=bgm_id,
                            subject_json=subject_str,
                            episodes_json=episodes_str,
                            characters_json=characters_str,
                            fetched_at=now_utc,
                            expire_at=expire_at
                        ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"写入临时缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")
    # ============================== API Fetch Methods ==============================

    async def _fetch_subject_api(self, subject_id: int) -> Optional[Dict[str, Any]]:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        headers = self._get_headers()
        proxy = self._get_proxy()

        try:
            async with httpx.AsyncClient(timeout=15.0, proxy=proxy) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    log_audit("Bangumi", "处理", f"Bangumi Subject {subject_id} not found.", level="WARN")
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            log_audit("Bangumi", "处理", f"Bangumi API error (subject {subject_id}): {e}", level="ERROR")
            return None

    async def _fetch_episodes_api(self, subject_id: int, ep_type: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取条目的剧集列表。ep_type: None=全部, 0=正片, 1=SP, 2=OP, 3=ED"""
        url = f"https://api.bgm.tv/v0/episodes?subject_id={subject_id}"
        if ep_type is not None:
            url += f"&type={ep_type}"
        # 限制最多 200 集（BGM API 单页上限）
        url += "&limit=200"
        headers = self._get_headers()
        proxy = self._get_proxy()

        try:
            async with httpx.AsyncClient(timeout=15.0, proxy=proxy) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 401:
                    # Retry without token
                    no_auth_headers = {"User-Agent": headers["User-Agent"], "Accept": "application/json"}
                    resp = await client.get(url, headers=no_auth_headers)
                resp.raise_for_status()
                return resp.json().get('data', [])
        except Exception as e:
            log_audit("Bangumi", "处理", f"Bangumi episodes API error (subject {subject_id}): {e}", level="ERROR")
            return []

    async def _fetch_characters_api(self, subject_id: int) -> List[Dict[str, Any]]:
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
        headers = self._get_headers()
        proxy = self._get_proxy()

        try:
            async with httpx.AsyncClient(timeout=15.0, proxy=proxy) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            log_audit("Bangumi", "处理", f"Bangumi characters API error (subject {subject_id}): {e}", level="ERROR")
            return []

    # ============================== Public API ==============================

    async def get_subject(self, subject_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取条目信息（统一入口）。
        缓存优先级: L1 内存 → DB 永久/临时缓存 → API。
        force_refresh=True 时跳过所有缓存，直接请求 API。

        返回: {"data": Optional[Dict], "source": str}
          source 值: "l1" | "permanent" | "temp" | "api" | "miss"
        """
        # 1. L1 内存缓存
        if not force_refresh:
            subject, _, _ = self._l1_get(subject_id)
            if subject is not None:
                log_audit("Bangumi", "处理", f"[BGM Provider] Subject {subject_id}: L1内存缓存命中")
                return {"data": subject, "source": "l1"}

        # 2. DB 缓存
        if not force_refresh:
            subject, episodes, characters, is_permanent = await self._db_get(subject_id)
            if subject is not None:
                source = "permanent" if is_permanent else "temp"
                label = "永久缓存" if is_permanent else "临时缓存"
                log_audit("Bangumi", "处理", f"[BGM Provider] Subject {subject_id}: {label}命中")
                self._l1_set(subject_id, subject, episodes, characters)
                return {"data": subject, "source": source}

        # 3. API
        log_audit("Bangumi", "处理", f"[BGM Provider] Subject {subject_id}: 缓存未命中，请求官方API...")
        subject_data = await self._fetch_subject_api(subject_id)
        if subject_data:
            # 判断完结状态决定缓存表
            is_ended = await self._is_long_ended(subject_id)
            # 保存到 DB（subject 有值，episodes/characters 暂为 None，由各自方法独立获取后更新）
            await self._db_save(subject_id, subject_data, None, None, is_ended)
            self._l1_set(subject_id, subject_data, None, None)
            cache_type = "永久缓存(完结)" if is_ended else "临时缓存(未完结)"
            log_audit("Bangumi", "完成", f"[BGM Provider] Subject {subject_id}: API获取成功，已写入{cache_type}")
            return {"data": subject_data, "source": "api"}

        log_audit("Bangumi", "处理", f"[BGM Provider] Subject {subject_id}: API返回空数据", level="WARN")
        return {"data": None, "source": "miss"}

    async def get_episodes(self, subject_id: int, force_refresh: bool = False, ep_type: Optional[int] = None) -> Dict[str, Any]:
        """
        获取条目剧集列表（统一入口）。
        如果缓存中有 episodes 则直接返回；否则从 API 获取并缓存。
        ep_type 仅在从 API 获取时生效（缓存中存的是全量 episodes）。

        返回: {"data": List[Dict], "source": str}
          source 值: "l1" | "permanent" | "temp" | "api" | "miss"
        """
        # 1. L1 内存缓存
        if not force_refresh:
            _, episodes, _ = self._l1_get(subject_id)
            if episodes is not None:
                log_audit("Bangumi", "处理", f"[BGM Provider] Episodes {subject_id}: L1内存缓存命中")
                data = [ep for ep in episodes if ep.get('type') == ep_type] if ep_type is not None else episodes
                return {"data": data, "source": "l1"}

        # 2. DB 缓存
        if not force_refresh:
            _, episodes, _, is_permanent = await self._db_get(subject_id)
            if episodes is not None:
                source = "permanent" if is_permanent else "temp"
                label = "永久缓存" if is_permanent else "临时缓存"
                log_audit("Bangumi", "处理", f"[BGM Provider] Episodes {subject_id}: {label}命中")
                self._l1_set(subject_id, None, episodes, None)
                data = [ep for ep in episodes if ep.get('type') == ep_type] if ep_type is not None else episodes
                return {"data": data, "source": source}

        # 3. API
        log_audit("Bangumi", "处理", f"[BGM Provider] Episodes {subject_id}: 缓存未命中，请求官方API...")
        episodes_data = await self._fetch_episodes_api(subject_id)
        if episodes_data:
            # 更新缓存：需要把 episodes 合并到现有缓存记录中
            await self._merge_episodes_to_cache(subject_id, episodes_data)
            self._l1_set(subject_id, None, episodes_data, None)
            log_audit("Bangumi", "完成", f"[BGM Provider] Episodes {subject_id}: API获取成功({len(episodes_data)}集)，已写入缓存")
            return {"data": episodes_data, "source": "api"}

        log_audit("Bangumi", "处理", f"[BGM Provider] Episodes {subject_id}: API返回空数据", level="WARN")
        return {"data": [], "source": "miss"}

    async def get_characters(self, subject_id: int, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取条目角色列表（统一入口）。

        返回: {"data": List[Dict], "source": str}
          source 值: "l1" | "permanent" | "temp" | "api" | "miss"
        """
        # 1. L1 内存缓存
        if not force_refresh:
            _, _, characters = self._l1_get(subject_id)
            if characters is not None:
                log_audit("Bangumi", "处理", f"[BGM Provider] Characters {subject_id}: L1内存缓存命中")
                return {"data": characters, "source": "l1"}

        # 2. DB 缓存
        if not force_refresh:
            _, _, characters, is_permanent = await self._db_get(subject_id)
            if characters is not None:
                source = "permanent" if is_permanent else "temp"
                label = "永久缓存" if is_permanent else "临时缓存"
                log_audit("Bangumi", "处理", f"[BGM Provider] Characters {subject_id}: {label}命中")
                self._l1_set(subject_id, None, None, characters)
                return {"data": characters, "source": source}

        # 3. API
        log_audit("Bangumi", "处理", f"[BGM Provider] Characters {subject_id}: 缓存未命中，请求官方API...")
        characters_data = await self._fetch_characters_api(subject_id)
        if characters_data:
            await self._merge_characters_to_cache(subject_id, characters_data)
            self._l1_set(subject_id, None, None, characters_data)
            log_audit("Bangumi", "完成", f"[BGM Provider] Characters {subject_id}: API获取成功({len(characters_data)}个角色)，已写入缓存")
            return {"data": characters_data, "source": "api"}

        log_audit("Bangumi", "处理", f"[BGM Provider] Characters {subject_id}: API返回空数据", level="WARN")
        return {"data": [], "source": "miss"}

    async def search_subjects(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        搜索 Bangumi 条目（无缓存，直接 API）。
        """
        url = "https://api.bgm.tv/v0/search/subjects"
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        payload = {
            "keyword": query,
            "filter": {
                "type": [2, 6]  # 2=Anime, 6=Real (TV/Movie)
            }
        }
        proxy = self._get_proxy()

        try:
            async with httpx.AsyncClient(timeout=15.0, proxy=proxy) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                results = []
                for item in data.get('data', [])[:limit]:
                    results.append({
                        'id': item.get('id'),
                        'name': item.get('name', ''),
                        'name_cn': item.get('name_cn', ''),
                        'date': item.get('date', ''),
                        'type': item.get('type', 0),
                        'platform': item.get('platform', ''),
                        'summary': item.get('summary', ''),
                        'tags': item.get('tags', []),
                        'score': item.get('score', 0),
                        'images': item.get('images', {})
                    })
                return results
        except Exception as e:
            log_audit("Bangumi", "处理", f"Bangumi search API error for '{query}': {e}", level="ERROR")
            return []

    def get_allowed_tags(self) -> List[str]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('sync_config', {}).get('allowed_tags', [])
            except Exception:
                pass
        return []

    # ============================== Cache Merge Helpers ==============================

    async def _merge_episodes_to_cache(self, bgm_id: int, episodes: List[Dict]):
        """将 episodes 数据合并到现有缓存记录中（不覆盖 subject/characters）"""
        episodes_str = json.dumps(episodes, ensure_ascii=False)
        is_ended = await self._is_long_ended(bgm_id)

        if is_ended:
            try:
                async with BangumiCacheSessionLocal() as session:
                    row = await session.get(BangumiSubjectCache, bgm_id)
                    if row:
                        row.episodes_json = episodes_str
                        row.fetched_at = datetime.now(timezone.utc)
                        await session.commit()
                        return
                    # 永久缓存中没有记录，创建一条（subject 为空）
                    session.add(BangumiSubjectCache(
                        bgm_id=bgm_id,
                        subject_json=None,
                        episodes_json=episodes_str,
                        characters_json=None,
                        fetched_at=datetime.now(timezone.utc)
                    ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"合并 episodes 到永久缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")
        else:
            try:
                async with BangumiCacheSessionLocal() as session:
                    row = await session.get(BangumiTempCache, bgm_id)
                    if row:
                        row.episodes_json = episodes_str
                        row.fetched_at = datetime.now(timezone.utc)
                        await session.commit()
                        return
                    session.add(BangumiTempCache(
                        bgm_id=bgm_id,
                        subject_json=None,
                        episodes_json=episodes_str,
                        characters_json=None,
                        fetched_at=datetime.now(timezone.utc),
                        expire_at=datetime.now(timezone.utc) + timedelta(days=TEMP_CACHE_DAYS)
                    ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"合并 episodes 到临时缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")
    async def _merge_characters_to_cache(self, bgm_id: int, characters: List[Dict]):
        """将 characters 数据合并到现有缓存记录中（不覆盖 subject/episodes）"""
        characters_str = json.dumps(characters, ensure_ascii=False)
        is_ended = await self._is_long_ended(bgm_id)

        if is_ended:
            try:
                async with BangumiCacheSessionLocal() as session:
                    row = await session.get(BangumiSubjectCache, bgm_id)
                    if row:
                        row.characters_json = characters_str
                        row.fetched_at = datetime.now(timezone.utc)
                        await session.commit()
                        return
                    session.add(BangumiSubjectCache(
                        bgm_id=bgm_id,
                        subject_json=None,
                        episodes_json=None,
                        characters_json=characters_str,
                        fetched_at=datetime.now(timezone.utc)
                    ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"合并 characters 到永久缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")
        else:
            try:
                async with BangumiCacheSessionLocal() as session:
                    row = await session.get(BangumiTempCache, bgm_id)
                    if row:
                        row.characters_json = characters_str
                        row.fetched_at = datetime.now(timezone.utc)
                        await session.commit()
                        return
                    session.add(BangumiTempCache(
                        bgm_id=bgm_id,
                        subject_json=None,
                        episodes_json=None,
                        characters_json=characters_str,
                        fetched_at=datetime.now(timezone.utc),
                        expire_at=datetime.now(timezone.utc) + timedelta(days=TEMP_CACHE_DAYS)
                    ))
                    await session.commit()
            except Exception as e:
                log_audit("Bangumi", "失败", f"合并 characters 到临时缓存失败 (bgm_id={bgm_id}): {e}", level="ERROR")