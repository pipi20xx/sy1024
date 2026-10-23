import os
import json
import re
import asyncio
from typing import Dict, Any, Tuple, Optional, List

from ...logger import log_audit


class AiTranslateMixin:
    """AI 翻译元数据的方法。"""

    async def ai_translate_item_metadata(self, item_type: str, item_id: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        使用 AI 翻译项目的特定字段。
        config: { 'title': bool, 'overview': bool, 'credits': bool, 'credits_options': dict }
        """
        log_audit("编辑", "开始", f"开始 AI 批量翻译项目: {item_type}/{item_id}")
        from ... import globals
        if not hasattr(globals, "llm_service") or globals.llm_service is None:
            from ..llm_service import LLMService
            globals.llm_service = LLMService(self.configuration_service)

        llm = globals.llm_service

        # 1. 获取全量详情
        details = await self.get_item_full_details(item_type, item_id)
        if not details:
            return False, "获取项目详情失败"

        full_metadata = details.get("full_metadata", {})
        changed = False

        # 2. 翻译标题
        if config.get("title"):
            title_field = "title" if item_type == "tmdb-movies2" else "name"
            original_title = full_metadata.get(title_field)
            if original_title:
                context = "movie_title" if item_type == "tmdb-movies2" else "series_title"
                try:
                    full_metadata[title_field] = await llm.translate(original_title, context=context)
                    changed = True
                except Exception as e:
                    log_audit("编辑", "失败", f"AI 翻译标题失败: {e}", level="ERROR")
        # 3. 翻译简介
        if config.get("overview"):
            original_overview = full_metadata.get("overview")
            if original_overview:
                context = "movie_overview" if item_type == "tmdb-movies2" else "series_overview"
                try:
                    full_metadata["overview"] = await llm.translate(original_overview, context=context)
                    changed = True
                except Exception as e:
                    log_audit("编辑", "失败", f"AI 翻译简介失败: {e}", level="ERROR")
        # 3.5 翻译季/集 (仅剧集)
        if item_type == "tmdb-tv" and details.get("seasons"):
            for season in details["seasons"]:
                s_num = season.get("season_number")
                s_changed = False

                # 翻译季标题
                if config.get("season_title") and season.get("metadata"):
                    orig_s_name = season["metadata"].get("name")
                    if orig_s_name:
                        try:
                            season["metadata"]["name"] = await llm.translate(orig_s_name, context="season_title")
                            s_changed = True
                        except: pass

                # 翻译季简介
                if config.get("season_overview") and season.get("metadata"):
                    orig_s_ov = season["metadata"].get("overview")
                    if orig_s_ov:
                        try:
                            season["metadata"]["overview"] = await llm.translate(orig_s_ov, context="season_overview")
                            s_changed = True
                        except: pass

                # 翻译集标题和简介
                if season.get("episodes"):
                    for episode in season["episodes"]:
                        e_num = episode.get("episode_number")
                        e_changed = False
                        if not episode.get("metadata"): continue

                        # 集标题
                        if config.get("episode_title"):
                            orig_e_title = episode["metadata"].get("name")
                            if orig_e_title:
                                try:
                                    episode["metadata"]["name"] = await llm.translate(orig_e_title, context="episode_title")
                                    e_changed = True
                                except: pass

                        # 集简介
                        if config.get("episode_overview"):
                            orig_e_ov = episode["metadata"].get("overview")
                            if orig_e_ov:
                                try:
                                    episode["metadata"]["overview"] = await llm.translate(orig_e_ov, context="episode_overview")
                                    e_changed = True
                                except: pass

                        if e_changed:
                            await self.update_episode_metadata(item_id, s_num, e_num, episode["metadata"])
                            s_changed = True  # 集变了，季也算变了（虽然季文件不一定变，但为了逻辑统一）

                if s_changed:
                    await self.update_season_metadata(item_id, s_num, season.get("metadata", {}), update_episodes=False)

        # 4. 翻译演职员 (批量)
        if config.get("credits"):
            opts = config.get("credits_options", {})
            unique_texts = {
                "cast_name": set(), "cast_character": set(),
                "crew_name": set(), "crew_job": set()
            }

            def collect(c):
                if not c: return
                actors = (c.get("cast") or []) + (c.get("guest_stars") or [])
                for p in actors:
                    if opts.get("cast_name") and p.get("name"): unique_texts["cast_name"].add(p.get("name"))
                    if opts.get("cast_character") and p.get("character"):
                        for char in str(p.get("character")).split('/'): unique_texts["cast_character"].add(char.strip())
                for p in (c.get("crew") or []):
                    if opts.get("crew_name") and p.get("name"): unique_texts["crew_name"].add(p.get("name"))
                    if opts.get("crew_job") and p.get("job"): unique_texts["crew_job"].add(p.get("job"))

            collect(full_metadata.get("credits") or full_metadata.get("casts"))
            if item_type == "tmdb-tv" and config.get("include_children_credits") and details.get("seasons"):
                for s in details["seasons"]:
                    for e in (s.get("episodes") or []):
                        collect(e.get("metadata", {}).get("credits") or e.get("metadata", {}).get("casts"))

            trans_map = {k: {} for k in unique_texts}
            for ctx, texts in unique_texts.items():
                if not texts: continue
                text_list = list(texts)
                for i in range(0, len(text_list), 20):
                    chunk = text_list[i:i + 20]
                    try:
                        res = await llm.chat([
                            {"role": "system", "content": f"你是一个翻译专家。请翻译以下影视相关的【{ctx}】列表为中文。每行一个结果，直接返回，不要编号，不要任何解释。"},
                            {"role": "user", "content": "\n".join(chunk)}
                        ])
                        translated_lines = res.split('\n')
                        for idx, line in enumerate(translated_lines):
                            if idx < len(chunk):
                                # 清洗：去掉开头的数字和标点 (e.g., "1. " 或 "1、")
                                clean_line = re.sub(r'^\d+[\.、\s]+', '', line.strip())
                                trans_map[ctx][chunk[idx]] = clean_line
                    except Exception as e:
                        log_audit("编辑", "失败", f"批量翻译 {ctx} 失败: {e}", level="ERROR")

            def apply(c):
                if not c: return False
                m = False
                # 同时处理 cast 和 guest_stars
                actors_keys = ["cast", "guest_stars"]
                for key in actors_keys:
                    actors = c.get(key) or []
                    if not isinstance(actors, list): continue
                    for p in actors:
                        aid = p.get("id")
                        char = p.get("character") or "未知角色"

                        # 翻译姓名
                        orig_name = p.get("name")
                        if orig_name in trans_map["cast_name"]:
                            p["name"] = trans_map["cast_name"][orig_name]
                            log_audit("编辑", "处理", f"  [翻译姓名] ID:{aid} | 角色:{char} | {orig_name} -> {p['name']}")
                            m = True

                        # 处理角色名翻译
                        if p.get("character"):
                            orig_char = p["character"]
                            # 处理多角色 (用 / 分隔)
                            new_chars = [trans_map["cast_character"].get(char_idx.strip(), char_idx.strip()) for char_idx in str(orig_char).split('/')]
                            new_val = " / ".join(new_chars)
                            if new_val != p["character"]:
                                log_audit("编辑", "处理", f"  [翻译角色] ID:{aid} | {p['name']} | {p['character']} -> {new_val}")
                                p["character"] = new_val
                                m = True

                # 处理幕后工作人员 (Crew)
                crew = c.get("crew") or []
                for p in crew:
                    orig_name = p.get("name")
                    if orig_name in trans_map["crew_name"]:
                        p["name"] = trans_map["crew_name"][orig_name]
                        m = True

                    if p.get("job"):
                        orig_job = p["job"]
                        if orig_job in trans_map["crew_job"]:
                            p["job"] = trans_map["crew_job"][orig_job]
                            m = True
                return m

            # 修改点：在处理 credits 翻译时，确保主元数据字段被正确识别
            credits_key = "credits" if "credits" in full_metadata else "casts"
            if apply(full_metadata.get(credits_key)):
                changed = True

            if item_type == "tmdb-tv" and config.get("include_children_credits") and details.get("seasons"):
                for s in details["seasons"]:
                    s_changed = False
                    s_num = s["season_number"]

                    # 翻译季级别的 credits (如果有)
                    if s.get("metadata"):
                        s_credits_key = "credits" if "credits" in s["metadata"] else "casts"
                        if apply(s["metadata"].get(s_credits_key)):
                            await self.update_season_metadata(item_id, s_num, s["metadata"], update_episodes=False)
                            # 注意：这里不需要设置 s_changed，因为 update_season_metadata 已经写入文件

                    for e in (s.get("episodes") or []):
                        if e.get("metadata"):
                            e_credits_key = "credits" if "credits" in e["metadata"] else "casts"
                            if apply(e["metadata"].get(e_credits_key)):
                                await self.update_episode_metadata(item_id, s_num, e["episode_number"], e["metadata"])
                                # 集的更新直接写入文件，不影响主 changed 状态

        # 5. 最后保存主条目
        if changed:
            success, msg, _ = await self.update_item_metadata(item_type, item_id, full_metadata)
            return success, msg

        return True, "完成"
