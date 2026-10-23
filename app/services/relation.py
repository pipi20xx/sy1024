import httpx
import re
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy import select, and_
from .. import globals
from .tmdb_cache import TmdbCacheService
from .metadata_definition import MetadataDefinitionService
from .bangumi_provider import BangumiProvider
from ..database import MediaRelationsSessionLocal, TmdbBgmMappingSessionLocal
from ..models import TmdbBangumiMap, TmdbBgmMapping
from ..logger import log_audit


# Logic ported from bangumi-box AutoMatcher
TRUNCATION_PATTERNS = [
    r"第\s*[一二三四五六七八九十零〇\dIVXLCDM]+.*(?:季|期|章|部|部分|幕|年|年目|クール|Stage|シリーズ|Series)",
    r"\s+[一二三四五六七八九十零〇\d]+\s*(?:季|期)\b",
    r"\s+(?:第)?\s*[一二三四五六七八九十零〇\d]+\s*丁目",
    r"\b(?:Season|Saison|시즌|S|Part|Cour|Stage)[\s.]*(?:[IVXLCDM]+|\d+)",
    r"\b\d+(?:st|nd|rd|th)\s*(?:Season|Stage|Part|Cour)?",
    r"\b(最终季|ファイナルシリーズ|Final Season|Final|最終章|完結編|完结篇)\b",
    r"[\(（【\[][^篇]*篇[)）】\]]",
    r"\b[上下左右前后终末始序中特新旧更真伪\w\s]{1,10}篇\b",
    r"\b[一二三四五六七八九十零〇\w]+之章\b",
    r'\bEpisode\s*[:：.]?\s*(?:[IVXLCDM]+|\d+|\u201c[^\u201d]+\u201d|"[^"]+")',
    r"\s+(?:[IVXLCDM一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾壱弐参ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d+)\s*[:：]\s+",
    r"[:：]\s+",
    r"(?:[\s～~]+)(?:Next|NEXT)(?:\s+(?:Season|Summit|Generation|Level|Stage)|$|[\s～~])",
    r"(?<=[\u4e00-\u9fff])(?:Next|NEXT)$",
    r"\s+([IVXLCDM一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾壱弐参ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|\d+)$",
    r"['']+$",
    r"\s+[^\w\s]+$",
    r"[♭ΔθδΨΩαβγζηικλμνξοπρστυφχψω]+$",
    r"\s+[\u4e00-\u9fff\u3040-\u30ff\u30a0-\u30ff]{1,2}$"
]

FORMAT_CLEAN_PATTERNS = [
    r"^[\u7eed\u7db2]\s*",
    r"\u5267\u573a\u7248",
    r"\u7535\u5f71\u7248",
    r"\u7535\u5f71",
    r"\u6620\u753b",
    r"\u5168\u5929\u57df",
    r"\u5929\u6587\u9986",
    r"\bThe Movie\b",
    r"\bMovie\b",
    r"\bFilm\b",
    r"\bTHE REAL 4D\b",
    r"\b4D\b",
    r"\b3D\b",
    r"\bOVA\b",
    r"\bOAD\b",
    r"\bOAV\b",
    r"\bWeb\b",
    r"[\(\uff08\u3010\[]\s*(?:OVA|OAD|OAV|Movie|\u5267\u573a\u7248|Web|4D|3D)\s*[\)\uff09\u3011\]]",
]

class RelationService:
    def __init__(self):
        self.tmdb_cache = TmdbCacheService()
        self.metadata_def = MetadataDefinitionService()
        self.provider = BangumiProvider()

    def init_db(self):
        pass

    async def batch_check_bangumi_mapping(self, item_type: str, tmdb_ids: List[str]) -> Dict[str, bool]:
        """
        批量查询 TMDB 条目是否有 Bangumi 映射。
        两级查询：TmdbBgmMapping（手动映射表）→ TmdbBangumiMap（自动化表）。
        只查本地 DB，不调外部 API，速度极快。
        
        :param item_type: 'tmdb-tv' 或 'tmdb-movies2'
        :param tmdb_ids: TMDB ID 列表
        :return: { tmdb_id_str: True/False, ... }
        """
        if not tmdb_ids:
            return {}

        # item_type 映射到 DB 中的 tmdb_type
        db_type = 'tv' if item_type == 'tmdb-tv' else 'movie'
        result_map = {str(tid): False for tid in tmdb_ids}
        
        # 转换为 int 用于查询 TmdbBgmMapping 表
        int_ids = []
        for tid in tmdb_ids:
            try:
                int_ids.append(int(tid))
            except (ValueError, TypeError):
                pass

        # 1. 查询手动映射表 TmdbBgmMapping
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                stmt = select(TmdbBgmMapping.tmdb_id).where(
                    TmdbBgmMapping.tmdb_type == db_type,
                    TmdbBgmMapping.tmdb_id.in_(int_ids)
                ).distinct()
                result = await session.execute(stmt)
                matched_ids = {str(row[0]) for row in result.fetchall()}
                for mid in matched_ids:
                    result_map[mid] = True
        except Exception as e:
            log_audit("关联", "失败", f"批量查询 TmdbBgmMapping 失败: {e}", level="ERROR")

        # 2. 查询自动化表 TmdbBangumiMap（仅查还未标记为 True 的）
        unmatched = [tid for tid, val in result_map.items() if not val]
        if unmatched:
            try:
                async with MediaRelationsSessionLocal() as session:
                    stmt = select(TmdbBangumiMap.tmdb_id).where(
                        TmdbBangumiMap.tmdb_type == db_type,
                        TmdbBangumiMap.tmdb_id.in_(unmatched)
                    ).distinct()
                    result = await session.execute(stmt)
                    matched_ids = {str(row[0]) for row in result.fetchall()}
                    for mid in matched_ids:
                        result_map[mid] = True
            except Exception as e:
                log_audit("关联", "失败", f"批量查询 TmdbBangumiMap 失败: {e}", level="ERROR")

        return result_map

    async def _enrich_relation_list(self, relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich relation list with actual names from Bangumi API (via BangumiProvider) and TMDB Cache DB.
        """
        if not relations:
            return []

        # 1. Fetch Bangumi Names & Dates via BangumiProvider (API + cache)
        bangumi_ids = list(set(r['bangumi_id'] for r in relations))
        bgm_map = {}
        for bgm_id in bangumi_ids:
            try:
                result = await self.provider.get_subject(bgm_id)
                subject = result.get("data")
                if subject:
                    bgm_map[bgm_id] = {
                        'name': subject.get('name', ''),
                        'name_cn': subject.get('name_cn', ''),
                        'date': subject.get('date', ''),
                        'type': subject.get('type', 0),
                        'platform': subject.get('platform', '')
                    }
            except Exception as e:
                log_audit("关联", "失败", f"获取 Bangumi {bgm_id} 信息错误: {e}", level="ERROR")
        # 2. Fetch TMDB Names & Dates (Batch)
        tmdb_targets = [(r['tmdb_id'], r['tmdb_type']) for r in relations]
        tmdb_map = await self.tmdb_cache.get_entities_batch(tmdb_targets)

        for r in relations:
            if r.get('season_number') is None:
                r['season_number'] = 1

            bgm_data = bgm_map.get(r['bangumi_id'])
            if bgm_data:
                r['bangumi_name'] = bgm_data['name']
                r['bangumi_name_cn'] = bgm_data['name_cn']
                r['bangumi_date'] = bgm_data['date']
                r['bangumi_type'] = bgm_data['type']

                try:
                    pid = bgm_data.get('platform')
                    tid = bgm_data.get('type')
                    if pid and tid:
                        if isinstance(pid, str) and pid.isdigit(): pid = int(pid)
                        if isinstance(tid, str) and tid.isdigit(): tid = int(tid)
                        p_info = self.metadata_def.get_platform_info(tid, pid)
                        r['bangumi_platform_cn'] = p_info.get('type_cn') or p_info.get('type') or ''
                    else:
                        r['bangumi_platform_cn'] = ''
                except:
                    r['bangumi_platform_cn'] = ''
            else:
                r['bangumi_name'] = 'Unknown ID'
                r['bangumi_name_cn'] = ''
                r['bangumi_date'] = ''
                r['bangumi_type'] = 0
                r['bangumi_platform_cn'] = ''

            tmdb_key = f"{r['tmdb_id']}_{r['tmdb_type']}"
            tmdb_data = tmdb_map.get(tmdb_key)

            if tmdb_data:
                r['tmdb_name_cn'] = tmdb_data['name_cn']
                orig = tmdb_data.get('original_json', {})
                r['tmdb_date'] = orig.get('release_date') or orig.get('first_air_date') or ''

                genres = orig.get('genres', [])
                r['is_animation'] = any(g.get('id') == 16 for g in genres)
            else:
                r['tmdb_name_cn'] = 'Unknown/Uncached'
                r['tmdb_date'] = ''
                r['is_animation'] = False

        return relations

    async def get_relation(self, tmdb_id: str, tmdb_type: str) -> List[Dict[str, Any]]:
        """Get all Bangumi relations for a TMDB ID. Two-level fallback: TmdbBgmMapping -> TmdbBangumiMap."""
        # 优先使用新表 TmdbBgmMapping（手动映射表）
        try:
            async with TmdbBgmMappingSessionLocal() as session:
                stmt = select(TmdbBgmMapping).where(
                    and_(
                        TmdbBgmMapping.tmdb_id == int(tmdb_id),
                        TmdbBgmMapping.tmdb_type == tmdb_type
                    )
                )
                result = await session.execute(stmt)
                mapping = result.scalar_one_or_none()

                if mapping:
                    import json
                    season_mappings = mapping.season_mappings
                    if season_mappings:
                        season_mappings_dict = json.loads(season_mappings)

                        all_bangumi_ids = []
                        for season_bgm_ids in season_mappings_dict.values():
                            all_bangumi_ids.extend(season_bgm_ids)

                        if len(all_bangumi_ids) > 1:
                            tmdb_year = await self._get_tmdb_year(tmdb_id, tmdb_type)
                            if tmdb_year:
                                best_bangumi_id = await self._find_closest_bangumi_by_year(all_bangumi_ids, tmdb_year)
                                if best_bangumi_id:
                                    log_audit("关联", "处理", f"从 TmdbBgmMapping 选择年份最相近的 Bangumi ID: {best_bangumi_id} (TMDB 年份: {tmdb_year})")
                                    result = [{
                                        'tmdb_id': str(tmdb_id),
                                        'tmdb_type': tmdb_type,
                                        'bangumi_id': best_bangumi_id,
                                        'note': '',
                                        'score': 1.0,
                                        'status': 1,
                                        'season_number': 1,
                                        'updated_at': None,
                                        'source': '手动映射表'
                                    }]
                                    return await self._enrich_relation_list(result)

                        if len(all_bangumi_ids) == 1:
                            log_audit("关联", "处理", f"从 TmdbBgmMapping 获取到 Bangumi ID: {all_bangumi_ids[0]}")
                            result = [{
                                'tmdb_id': str(tmdb_id),
                                'tmdb_type': tmdb_type,
                                'bangumi_id': all_bangumi_ids[0],
                                'note': '',
                                'score': 1.0,
                                'status': 1,
                                'season_number': 1,
                                'updated_at': None,
                                'source': '手动映射表'
                            }]
                            return await self._enrich_relation_list(result)
        except Exception as e:
            log_audit("关联", "失败", f"查询 TmdbBgmMapping 失败: {e}", level="ERROR")
        # 回退到旧表 TmdbBangumiMap（bangumi-data 自动化表）
        async with MediaRelationsSessionLocal() as session:
            stmt = select(TmdbBangumiMap).where(
                and_(
                    TmdbBangumiMap.tmdb_id == str(tmdb_id),
                    TmdbBangumiMap.tmdb_type == tmdb_type
                )
            )
            result = await session.execute(stmt)
            items = result.scalars().all()

            item_list = []
            for item in items:
                item_dict = {
                    'tmdb_id': item.tmdb_id,
                    'tmdb_type': item.tmdb_type,
                    'bangumi_id': item.bangumi_id,
                    'note': item.note,
                    'score': item.score,
                    'status': item.status,
                    'season_number': item.season_number,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None,
                    'source': '自动化表'
                }
                item_list.append(item_dict)

            return await self._enrich_relation_list(item_list)

    async def _get_tmdb_year(self, tmdb_id: str, tmdb_type: str) -> Optional[int]:
        """获取 TMDB 项目的年份"""
        try:
            cache_data = await self.tmdb_cache.get_entity(tmdb_id, tmdb_type)
            if cache_data:
                data = cache_data.get('original_json', {})
                year = data.get('release_date') or data.get('first_air_date')
                if year:
                    return int(year.split('-')[0])
        except Exception as e:
            log_audit("关联", "失败", f"获取 TMDB 年份失败: {e}", level="ERROR")
        return None

    async def _find_closest_bangumi_by_year(self, bangumi_ids: List[int], tmdb_year: int) -> Optional[int]:
        """根据年份找到最相近的 Bangumi ID（使用 BangumiProvider API）"""
        try:
            best_id = None
            min_diff = float('inf')

            for bgm_id in bangumi_ids:
                result = await self.provider.get_subject(bgm_id)
                subject = result.get("data")
                if subject:
                    bgm_date = subject.get('date')
                    if bgm_date:
                        try:
                            bgm_year = int(bgm_date.split('-')[0])
                            diff = abs(bgm_year - tmdb_year)
                            if diff < min_diff:
                                min_diff = diff
                                best_id = bgm_id
                        except (ValueError, IndexError):
                            pass

            return best_id
        except Exception as e:
            log_audit("关联", "失败", f"查找最相近 Bangumi ID 失败: {e}", level="ERROR")
            return None

    async def get_relation_by_bangumi(self, bangumi_id: int) -> List[Dict[str, Any]]:
        """Get relations by Bangumi ID."""
        async with MediaRelationsSessionLocal() as session:
            stmt = select(TmdbBangumiMap).where(TmdbBangumiMap.bangumi_id == bangumi_id)
            result = await session.execute(stmt)
            items = result.scalars().all()

            item_list = []
            for item in items:
                item_dict = {
                    'tmdb_id': item.tmdb_id,
                    'tmdb_type': item.tmdb_type,
                    'bangumi_id': item.bangumi_id,
                    'note': item.note,
                    'score': item.score,
                    'status': item.status,
                    'season_number': item.season_number,
                    'updated_at': item.updated_at.isoformat() if item.updated_at else None
                }
                item_list.append(item_dict)

            return await self._enrich_relation_list(item_list)

    async def update_relation(self, tmdb_id: str, tmdb_type: str, bangumi_id: int, note: str = "", score: float = 1.0, status: int = 1, season_number: int = 1):
        """Insert or Update a specific relation pair."""
        async with MediaRelationsSessionLocal() as session:
            try:
                existing = await session.get(TmdbBangumiMap, (str(tmdb_id), tmdb_type, bangumi_id))
                if existing:
                    existing.note = note
                    existing.score = score
                    existing.status = status
                    existing.updated_at = datetime.now()
                    existing.season_number = season_number
                else:
                    new_relation = TmdbBangumiMap(
                        tmdb_id=str(tmdb_id),
                        tmdb_type=tmdb_type,
                        bangumi_id=bangumi_id,
                        note=note,
                        score=score,
                        status=status,
                        updated_at=datetime.now(),
                        season_number=season_number
                    )
                    session.add(new_relation)
                await session.commit()
            except Exception as e:
                log_audit("关联", "处理", f"Error updating relation: {e}", level="ERROR")
                raise

    async def save_relation(self, tmdb_id: str, tmdb_type: str, bangumi_id: int):
        """Alias for update_relation to be semantic."""
        await self.update_relation(tmdb_id, tmdb_type, bangumi_id, note="Manual Update", score=10.0, status=1)

    async def get_single_recommendation(self, tmdb_id: str, tmdb_type: str) -> Dict[str, Any]:
        """
        Get a single recommendation for a TMDB item.
        1. Check/Fetch TMDB Cache.
        2. Search Bangumi via API (BangumiProvider).
        3. Return best match with score.
        """
        tmdb_key = globals.service.configuration_service.get_config().get("tmdb_api_key")
        if not tmdb_key:
             return {"error": "未配置 TMDB API Key"}

        # 1. Get TMDB Data (from Cache or API)
        tmdb_data = await self.tmdb_cache.get_entity(tmdb_id, tmdb_type)

        if not tmdb_data:
            # Fetch from API
            api_type = 'movie' if tmdb_type == 'movie' else 'tv'
            url = f"https://api.themoviedb.org/3/{api_type}/{tmdb_id}"
            params = {"api_key": tmdb_key, "language": "zh-CN"}

            try:
                proxy_url = globals.service.configuration_service.get_proxy_url('tmdb')
                async with httpx.AsyncClient(timeout=10.0, proxy=proxy_url) as client:
                    resp = await client.get(url, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get('title') or data.get('name')
                        await self.tmdb_cache.save_entity(tmdb_id, tmdb_type, title, data)
                        tmdb_data = {
                            "tmdb_id": tmdb_id,
                            "tmdb_type": tmdb_type,
                            "name_cn": title,
                            "original_json": data
                        }
                    else:
                        return {"error": f"TMDB API Error: {resp.status_code}"}
            except Exception as e:
                return {"error": f"Failed to fetch TMDB data: {e}"}

        # 2. Search Bangumi via BangumiProvider (API)
        full_tmdb = tmdb_data.get('original_json', {})
        name_cn = full_tmdb.get('title') or full_tmdb.get('name')
        name_orig = full_tmdb.get('original_title') or full_tmdb.get('original_name')

        date_str = full_tmdb.get('release_date') or full_tmdb.get('first_air_date')
        year = None
        if date_str:
            try:
                year = int(date_str.split('-')[0])
            except: pass

        queries = set()
        if name_cn: queries.add(name_cn)
        if name_orig: queries.add(name_orig)

        clean_queries = set()
        for q in queries:
            clean_queries.add(q)
            clean = self._clean_format_keywords(q)
            if clean != q: clean_queries.add(clean)
            base = self._extract_base_name(q)
            if base != q and base != clean: clean_queries.add(base)

        best_match = None
        highest_score = 0.0

        for query in clean_queries:
            if not query: continue

            # Search Bangumi via API
            results = await self.provider.search_subjects(query, limit=5)

            for res in results:
                bgm_type = res.get('type')
                if bgm_type not in [2, 6]:
                    continue

                score = 0.0
                bgm_name_cn = res.get('name_cn') or res.get('name')
                bgm_name = res.get('name')
                bgm_date = res.get('date')

                r1 = SequenceMatcher(None, name_cn, bgm_name_cn).ratio() if name_cn else 0
                r2 = SequenceMatcher(None, name_orig, bgm_name).ratio() if name_orig else 0
                r3 = SequenceMatcher(None, name_cn, bgm_name).ratio() if name_cn else 0

                ratio = max(r1, r2, r3)
                score = ratio * 10

                if year and bgm_date:
                    try:
                        bgm_year = int(bgm_date.split('-')[0])
                        diff = abs(year - bgm_year)
                        if diff == 0:
                            score += 2.0
                        elif diff <= 1:
                            score += 1.0
                        elif diff > 4:
                            score -= 5.0
                        else:
                            score -= 2.0
                    except: pass

                if score > highest_score:
                    highest_score = score
                    best_match = res

        if best_match:
            return {
                "found": True,
                "bangumi_id": best_match['id'],
                "bangumi_title": best_match.get('name_cn') or best_match.get('name'),
                "score": highest_score,
                "year": best_match.get('date'),
                "type": best_match.get('type'),
                "platform_cn": '',
                "tmdb_title": name_cn
            }
        else:
             return {"found": False, "message": "No match found"}

    # ========================== Auto Matcher Helpers ==========================

    def _clean_format_keywords(self, title: Optional[str]) -> str:
        if not title: return ""
        clean_title = title
        for pattern in FORMAT_CLEAN_PATTERNS:
            clean_title = re.sub(pattern, " ", clean_title, flags=re.IGNORECASE)
        return " ".join(clean_title.split()).strip()

    def _extract_base_name(self, title: Optional[str]) -> str:
        if not title: return ""
        earliest_pos = len(title)
        for pattern in TRUNCATION_PATTERNS:
            match = re.search(pattern, title, flags=re.IGNORECASE)
            if match:
                earliest_pos = min(earliest_pos, match.start())
        truncated = title[:earliest_pos].strip().rstrip(':-~－－—_ ')
        return self._clean_format_keywords(truncated)
