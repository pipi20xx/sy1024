import os
import json
import secrets
from typing import Dict, Any, Tuple, Optional
from ..common import get_config_path, APP_CONFIG_FILENAME
from ..logger import log_audit


class ConfigurationService:
    """
    Service responsible for loading, saving, and managing application configuration.
    """
    def __init__(self):
        self._config_path = get_config_path(APP_CONFIG_FILENAME)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        data_dir = os.path.dirname(self._config_path)
        
        default_config = {
            "primary_cache_path": None,
            "override_cache_path": None,
            "emby_collections_path": None,
            "resource_info_path": None,
            "backup_path": None,
            "emby_server_url": "",
            "emby_api_key": "",
            "emby_user_id": "",
            "emby_username": "",
            "emby_password": "",
            "last_emby_item_id": "",
            "fanart_api_key": "",
            "tmdb_api_key": "",
            "tmdb_proxy_fallback": True,  # 是否开启远程回退代理
            "tmdb_episode_group_mode": False,  # 是否开启剧集组模式
            "tmdb_preferred_language": "zh-CN",  # 元数据首选语言
            "tmdb_image_languages": "zh-CN,en,ja,ko,null",  # 图片回退语言列表
            "data_path": data_dir,
            "auto_backup_enabled": False,
            "auto_backup_interval_hours": 24,
            "auto_backup_mode": "snapshot",
            "auto_backup_include_override": True,
            "auto_backup_include_collections": True,
            "auto_backup_max_snapshots": 10,
            "emby_webhook_enabled": False,
            "webhook_secret_token": None,
            "webhook_action_script_enabled": True,
            "webhook_action_image_update_enabled": True,
            "webhook_action_collection_sync_enabled": True,
            "webhook_action_metadata_update_enabled": True,
            "webhook_action_storage_query_enabled": True,
            "external_control": {
                "api_token": None,
                "audit_log_enabled": True
            },
            "file_watcher_enabled": False,  # 是否启用实时文件监控
            "file_watcher_auto_lock_name": False,  # 文件变动时自动锁定名称
            "file_watcher_poll_interval": 5,  # 文件监控轮询间隔（秒），值越大CPU占用越低但响应越慢
            "show_library_status": False,  # 是否在首页卡片显示 Emby 入库状态
            "show_bgm_mapping_status": False,  # 是否在首页卡片显示 BGM 映射状态
            "permanent_login_enabled": False,  # 是否开启永久登录（关闭则为24小时过期）
            "jwt_secret_key": None,  # JWT密钥，持久化存储，重启后保持不变
            "network": {
                "proxy_url": "",
                "enable_global": False,
                "proxy_targets": {
                    "tmdb": False,
                    "bangumi": False,
                    "fanart": False,
                    "emby": False,
                    "ai": False
                }
            },
            "ai": {
                "enabled": False,
                "include_item_context": True,
                "provider": "openai",  # openai, azure, anthropic, ollama
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-3.5-turbo",
                "temperature": 0.3,
                "prompts": {
                    "movie_overview": "你是一个专业的影视翻译专家。请将以下【电影简介】翻译成中文。要求：风格宏大且自然，符合中文表达习惯，保持剧情张力。",
                    "series_overview": "你是一个专业的影视翻译专家。请将以下【剧集总介绍】翻译成中文。要求：概述清晰，吸引人，符合中文表达习惯。",
                    "season_overview": "你是一个专业的影视翻译专家。请将以下【剧集季度简介】翻译成中文。要求：简洁明了地描述本季的核心剧情。",
                    "episode_overview": "你是一个专业的影视翻译专家。请将以下【分集剧情简介】翻译成中文。要求：准确描述本集内容，用词精炼。",
                    "title": "你是一个影视翻译专家。请将以下【影视作品标题】翻译成中文。如果已有公认的官方中文译名，请优先使用；如果没有，请提供一个贴切的译名。直接返回标题，不要解释。",
                    "actor_name": "你是一个专业的影视库整理助手。请将以下【演员/制作人员名称】或【角色名】翻译成中文。如果是外文名，请提供通用的中文译名。直接返回结果，不要解释，不要标点符号。"
                }
            }
        }

        config_needs_saving = False
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
                    # 对嵌套字典做深度合并，避免新字段丢失
                    for key, default_val in default_config.items():
                        if isinstance(default_val, dict) and isinstance(loaded_config.get(key), dict):
                            merged = default_val.copy()
                            merged.update(loaded_config[key])
                            default_config[key] = merged
            except (json.JSONDecodeError, IOError) as e:
                log_audit("配置", "处理", f"加载配置文件 '{self._config_path}' 失败: {e}", level="ERROR")
        if not default_config.get("webhook_secret_token"):
            log_audit("配置", "开始", "配置文件中未找到 webhook_secret_token，正在生成新的安全密钥...")
            default_config["webhook_secret_token"] = secrets.token_hex(24)
            config_needs_saving = True

        # 迁移 Bangumi Token 从 bgm_manager.json 到应用配置
        if not default_config.get("github_token") or not default_config.get("bangumi_access_token"):
            bgm_config_path = get_config_path('bgm_manager.json')
            if os.path.exists(bgm_config_path):
                try:
                    with open(bgm_config_path, 'r', encoding='utf-8') as f:
                        bgm_cfg = json.load(f)
                    if not default_config.get("github_token") and bgm_cfg.get("github_token"):
                        default_config["github_token"] = bgm_cfg["github_token"]
                        config_needs_saving = True
                        log_audit("配置", "处理", "已从 bgm_manager.json 迁移 GitHub Token 到应用配置")
                    bgm_sync_config = bgm_cfg.get("sync_config", {})
                    if not default_config.get("bangumi_access_token") and bgm_sync_config.get("access_token"):
                        default_config["bangumi_access_token"] = bgm_sync_config["access_token"]
                        config_needs_saving = True
                        log_audit("配置", "处理", "已从 bgm_manager.json 迁移 Bangumi Access Token 到应用配置")
                except Exception as e:
                    log_audit("配置", "失败", f"迁移 Bangumi Token 时出错: {e}", level="WARN")
        if config_needs_saving:
            self._save_config_to_disk(default_config)

        return default_config

    def _save_config_to_disk(self, config_data: Dict[str, Any]) -> bool:
        try:
            config_to_save = config_data.copy()
            config_to_save.pop("data_path", None)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config_to_save, f, indent=2, ensure_ascii=False)
            return True
        except IOError as e:
             log_audit("配置", "失败", f"保存配置文件失败: {e}", level="ERROR")
             return False

    def get_config(self) -> Dict[str, Any]:
        return self.config

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def update_config(self, new_settings: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            # 使用深度合并，避免嵌套字典（如 external_control/network/ai）被整体覆盖
            from ..common import deep_merge_dict
            deep_merge_dict(self.config, new_settings)
            if self._save_config_to_disk(self.config):
                log_audit("配置", "更新", f"应用配置已更新并保存到 {self._config_path}")
                return True, "配置保存成功。"
            else:
                return False, "无法写入配置文件。"
        except Exception as e:
            log_audit("配置", "失败", f"保存配置时出错: {e}", level="ERROR")
            return False, f"保存配置时出错: {e}"

    def get_cache_path_for_source(self, source: str) -> Optional[str]:
        from ..common import SOURCE_PRIMARY, SOURCE_OVERRIDE
        if source == SOURCE_PRIMARY:
            return self.config.get("primary_cache_path")
        elif source == SOURCE_OVERRIDE:
            return self.config.get("override_cache_path")
        return None

    def save_last_emby_item_id(self, emby_item_id: str) -> Tuple[bool, str]:
        return self.update_config({"last_emby_item_id": emby_item_id})

    def get_proxy_url(self, target: str) -> Optional[str]:
        """
        Get proxy URL for a specific target service.
        Targets: 'tmdb', 'bangumi', 'fanart', 'emby'
        """
        network_config = self.config.get("network", {})
        enable_global = network_config.get("enable_global", False)
        proxy_url = network_config.get("proxy_url")
        
        if not enable_global or not proxy_url:
            return None
            
        targets = network_config.get("proxy_targets", {})
        if targets.get(target, False):
            return proxy_url
            
        return None
