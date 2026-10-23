import asyncio
import httpx
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from .configuration import ConfigurationService
from ..logger import log_audit


class LLMService:
    def __init__(self, configuration_service: ConfigurationService):
        self.config_service = configuration_service
        self._client: Optional[AsyncOpenAI] = None
        self._current_proxy: Optional[str] = None
        self._last_config_ver = 0

    def _get_client(self) -> Optional[AsyncOpenAI]:
        ai_config = self.config_service.get("ai", {})
        if not ai_config.get("enabled"):
            return None
        
        api_key = ai_config.get("api_key")
        base_url = ai_config.get("base_url")
        provider = ai_config.get("provider", "openai")
        
        # Ollama 特殊处理：不需要强制 API Key
        if provider == "ollama" and not api_key:
            api_key = "ollama" # 占位符

        if not api_key:
            return None

        # 简单单例模式，如果配置没变就复用 client
        if self._client is None:
            # 检查代理设置
            proxy_url = self.config_service.get_proxy_url("ai")
            self._current_proxy = proxy_url
            
            http_client = None
            if proxy_url:
                log_audit("AI", "初始化", f"🔌 AI 服务初始化: 启用代理 {proxy_url}")
                http_client = httpx.AsyncClient(proxy=proxy_url)
            else:
                log_audit("AI", "初始化", "🔌 AI 服务初始化: 直连模式 (无代理)")
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                http_client=http_client
            )
        return self._client

    async def reload_client(self):
        """配置变更时清除 client 以便重新创建"""
        if self._client:
            await self._client.close()
        self._client = None
        self._current_proxy = None

    async def translate(self, text: str, target_lang: str = "中文", context: str = "movie_overview", extra_info: Optional[Dict[str, Any]] = None) -> str:
        """
        通用翻译接口
        context: 'movie_overview', 'actor_name', 'title' 等，用于优化 Prompt
        extra_info: 提供额外的上下文，如 {'item_name': '作品原名', 'item_type': 'movie'}
        """
        import time
        start_time = time.time()
        
        client = self._get_client()
        if not client:
            raise Exception("AI 服务未启用或配置不完整（缺少 API Key）")

        ai_config = self.config_service.get("ai", {})
        model = ai_config.get("model", "gpt-3.5-turbo")
        temp = ai_config.get("temperature", 0.3)
        user_prompts = ai_config.get("prompts", {})

        proxy_status = f" | 代理: {self._current_proxy}" if self._current_proxy else " | 代理: ❌ (直连)"
        log_audit("AI", "处理", f"🚀 AI 翻译请求: 场景={context}, 模型={model}{proxy_status}, 字符数={len(text)}")
        default_prompts = {
            "movie_title": f"你是一个影视翻译专家。请将以下【电影标题】翻译成{target_lang}。如果已有公认的官方中文译名，请优先使用；如果没有，请提供一个优美的译名。直接返回标题，不要解释。",
            "series_title": f"你是一个影视翻译专家。请将以下【剧集标题】翻译成{target_lang}。如果已有公认的官方中文译名，请优先使用；如果没有，请提供一个贴切的译名。直接返回标题，不要解释。",
            "season_title": f"你是一个影视翻译专家。请将以下【剧集季度标题】翻译成{target_lang}。要求：保持与主剧名风格一致，准确传达本季主题。直接返回标题，不要解释。",
            "movie_overview": f"你是一个专业的影视翻译专家。请将以下【电影简介】翻译成{target_lang}。要求：风格宏大且自然，符合中文表达习惯，保持剧情张力。",
            "series_overview": f"你是一个专业的影视翻译专家。请将以下【剧集简介】翻译成{target_lang}。要求：概述清晰，吸引人，符合中文表达习惯。",
            "season_overview": f"你是一个专业的影视翻译专家。请将以下【剧集季度简介】翻译成{target_lang}。要求：简洁明了地描述本季的核心剧情。",
            "episode_title": f"你是一个影视翻译专家。请将以下【分集标题】翻译成{target_lang}。要求：风格与整剧保持一致，准确传达本集主题。直接返回标题，不要解释。",
            "episode_overview": f"你是一个专业的影视翻译专家。请将以下【分集剧情简介】翻译成{target_lang}。要求：准确描述本集内容，用词精炼。",
            "cast_name": f"你是一个影视翻译助手。请将【演员姓名】翻译成{target_lang}。如果是日本名字，必须转为对应的汉字（如: Hanazawa Kana -> 花泽香菜），严禁音译。直接返回结果。",
            "cast_character": f"你是一个动漫翻译专家。请将【角色名称】翻译成{target_lang}。要求：必须对照 Wikipedia、Bangumi.tv 或官方汉化组的标准译名。如果是日本作品，必须提供公认的汉字全名，严禁中英混杂。示例：'Renako Amaori' 必须翻译为 '甘织玲奈子'。将 (voice) 统一译为 (配音)。直接返回结果，禁止解释。",
            "crew_name": f"你是一个专业的翻译助手。请将以下【制作人员姓名】翻译成{target_lang}。要求：遵循通用的影视译名惯例（音译），直接返回名字，不要解释。",
            "crew_job": f"你是一个影视行业术语专家。请将以下【制作职位/头衔】翻译成{target_lang}专业术语。要求：用词专业准确。直接返回翻译结果。",
            "default": f"请将以下内容翻译成{target_lang}。"
        }

        # 1. 基础提示词获取
        system_prompt = user_prompts.get(context) or default_prompts.get(context, default_prompts["default"])
        raw_template = system_prompt # 记录原始模板用于日志

        # 2. 构建背景上下文参考
        context_hint = ""
        include_context = ai_config.get("include_item_context", True)
        
        if include_context and extra_info:
            # --- 智能文化背景识别与注入 ---
            country_map = {
                "JP": "日本", "KR": "韩国", "US": "美国", "CN": "中国", 
                "HK": "香港", "TW": "台湾", "GB": "英国", "FR": "法国", 
                "DE": "德国", "TH": "泰国", "ES": "西班牙", "IT": "意大利"
            }
            lang_map = {
                "ja": "日语", "ko": "韩语", "en": "英语", "zh": "中文",
                "fr": "法语", "de": "德语", "th": "泰语", "es": "西班牙语"
            }

            item_name = extra_info.get("item_name", "未知作品")
            country_codes = extra_info.get("origin_country") or []
            countries = [country_map.get(c, c) for c in country_codes]
            orig_lang = extra_info.get("original_language")
            lang_name = lang_map.get(orig_lang, orig_lang)
            
            # 识别题材
            genres = extra_info.get("item_genres") or ""
            is_anime = "动画" in genres or "Animation" in genres
            
            # A. 构建背景描述并注入 System Prompt
            background_desc = f"影视作品《{item_name}》"
            if countries: background_desc += f"（产地: {'/'.join(countries)}"
            if lang_name: background_desc += f" | 语言: {lang_name}"
            if countries or lang_name: background_desc += "）"

            system_prompt = f"你正在为{background_desc}提供翻译服务。\n{system_prompt}"

            # B. 针对性指令补丁
            if "JP" in country_codes or orig_lang == "ja":
                if is_anime:
                    system_prompt += "\n强制规则：这是日本动画，禁止音译，必须使用汉字。示例: 'Mai Ouzuka' -> '王塚真唯'。"
                else:
                    system_prompt += "\n强制规则：这是日本作品，严禁音译，必须转为对应的汉字全名。"
            elif "KR" in country_codes or orig_lang == "ko":
                system_prompt += "\n强制规则：这是韩国作品，请使用汉字对齐或标准韩语译名。"
            elif "US" in country_codes or "GB" in country_codes or orig_lang == "en":
                system_prompt += "\n提示：英语作品，请遵循通用音译规范。"

            # C. 构建作品参考 (User Prompt)
            ref_parts = []
            ref_parts.append(f"作品标题: {item_name}")
            if extra_info.get("item_type"):
                readable_type = "电视剧 (TV Series)" if "tv" in extra_info["item_type"] else "电影 (Movie)"
                ref_parts.append(f"作品类型: {readable_type}")
            if extra_info.get("item_id"):
                tmdb_type = "tv" if "tv" in extra_info.get("item_type", "") else "movie"
                ref_parts.append(f"TMDB 链接: https://www.themoviedb.org/{tmdb_type}/{extra_info['item_id']}")
            if genres:
                ref_parts.append(f"题材类型: {genres}")
            
            context_hint = "### ⚠️ 重要背景参考 (仅用于专有名词和语境对齐，严禁将其翻译进结果中):\n" + "\n".join(ref_parts) + "\n\n"

        # 3. 针对翻译任务增加强约束
        system_prompt += "\n注意：请直接返回翻译后的文本，严禁添加任何开场白或解释说明。保持原有的信息密度和段落结构。"

        # 4. 组装最终的消息
        user_content = f"{context_hint}### 待翻译内容 (请仅翻译以下文本):\n{text}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # 日志记录
        log_output = [f"📡 [AI Request] 场景: {context} | 模型: {model}"]
        log_output.append(f"--- Raw Template ---\n{raw_template}")
        for msg in messages:
            role_label = f"--- {msg['role'].upper()} (Final) ---"
            log_output.append(f"{role_label}\n{msg['content']}")
        log_audit("AI", "处理", "\n".join(log_output))
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temp
            )
            result = response.choices[0].message.content.strip()
            duration = time.time() - start_time
            log_audit("AI", "完成", f"✅ AI 翻译成功! 耗时={duration:.2f}s, 结果长度={len(result)}\n--- RESULT ---\n{result}\n{'-'*40}")
            return result
        except Exception as e:
            duration = time.time() - start_time
            log_audit("AI", "失败", f"❌ AI 翻译失败! 耗时={duration:.2f}s, 错误: {e}", level="ERROR")
            raise Exception(f"AI 调用失败: {str(e)}")

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """通用的对话接口，用于测试台"""
        import time
        start_time = time.time()
        
        client = self._get_client()
        if not client:
            raise Exception("AI 服务未启用或配置不完整")

        ai_config = self.config_service.get("ai", {})
        model = ai_config.get("model", "gpt-3.5-turbo")

        proxy_status = f" | 代理: {self._current_proxy}" if self._current_proxy else " | 代理: ❌ (直连)"
        log_audit("AI", "处理", f"🚀 AI 对话请求: 模型={model}{proxy_status}")
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages
            )
            result = response.choices[0].message.content.strip()
            duration = time.time() - start_time
            log_audit("AI", "完成", f"✅ AI 对话成功! 耗时={duration:.2f}s")
            return result
        except Exception as e:
            duration = time.time() - start_time
            log_audit("AI", "失败", f"❌ AI 对话失败! 耗时={duration:.2f}s, 错误: {e}", level="ERROR")
            raise Exception(f"AI 调用失败: {str(e)}")