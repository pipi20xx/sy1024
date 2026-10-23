import json
import os
from typing import Dict, Any
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..common import get_config_path
from ..logger import log_audit



class BangumiService:
    """
    精简后的 Bangumi 服务。
    仅保留调度器配置管理（用于 bangumi-data 定时同步）。
    离线数据库下载/导入、搜索/过滤/详情查询已移除，
    详情查询请使用 BangumiProvider（调用 Bangumi API + 缓存）。
    """

    def __init__(self):
        self.config_path = get_config_path('bgm_manager.json')
        self.scheduler = AsyncIOScheduler()
        self.sync_lock = None  # 不再需要，保留属性以防外部引用

    def _load_manager_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log_audit("Bangumi", "失败", f"加载 Bangumi 管理器配置失败: {e}", level="ERROR")
            return {}

    def _save_manager_config(self, config: Dict[str, Any]):
        """Save configuration to JSON file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log_audit("Bangumi", "失败", f"保存 Bangumi 管理器配置失败: {e}", level="ERROR")
    async def start_scheduler(self):
        """Start the background scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            await self.reschedule_job()
            log_audit("Bangumi", "初始化", "Bangumi 自动同步调度器已启动。")
    async def get_scheduler_config(self) -> Dict[str, Any]:
        """Get current scheduler configuration, token, and sync_config."""
        config = {
            "enabled": True,
            "interval_days": 7,
            "hour": 3,
            "minute": 0,
            "github_token": "",
            "filters": {},
            "sync_config": {}
        }

        saved_config = self._load_manager_config()
        if saved_config:
            for k, v in saved_config.items():
                if k in config or k == "filters" or k == "sync_config":
                    config[k] = v

        config["current_version"] = "无记录"
        return config

    def update_scheduler_config(self, new_config: Dict[str, Any]):
        """Update scheduler configuration and restart job."""
        try:
            current_config = self._load_manager_config()

            if "enabled" in new_config:
                val = new_config["enabled"]
                if isinstance(val, str) and val.lower() == 'false':
                    current_config["enabled"] = False
                else:
                    current_config["enabled"] = bool(val)

            if "interval_days" in new_config: current_config["interval_days"] = max(1, int(new_config["interval_days"]))
            if "hour" in new_config: current_config["hour"] = max(0, min(23, int(new_config["hour"])))
            if "minute" in new_config: current_config["minute"] = max(0, min(59, int(new_config["minute"])))
            if "github_token" in new_config: current_config["github_token"] = str(new_config["github_token"]).strip()
            if "filters" in new_config: current_config["filters"] = new_config["filters"]
            if "sync_config" in new_config: current_config["sync_config"] = new_config["sync_config"]

            self._save_manager_config(current_config)

            self.reschedule_job()
            log_audit("Bangumi", "完成", "调度器配置更新成功。")
        except Exception as e:
            log_audit("Bangumi", "失败", f"更新调度器配置失败: {e}", level="ERROR")
            raise

    async def reschedule_job(self):
        """Reschedule the sync job based on current config."""
        config = await self.get_scheduler_config()
        job_id = 'bangumi_auto_sync'

        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        if config.get("enabled"):
            now = datetime.now()
            target_time = now.replace(hour=config["hour"], minute=config["minute"], second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)

            self.scheduler.add_job(
                self._run_scheduled_sync,
                'interval',
                days=config["interval_days"],
                start_date=target_time,
                id=job_id
            )
            log_audit("Bangumi", "更新", f"已调度 Bangumi 同步: 每 {config['interval_days']} 天于 {config['hour']}:{config['minute']:02d} 执行，下次开始时间: {target_time}")
        else:
            log_audit("Bangumi", "更新", "Bangumi 自动同步已禁用。")
    async def _run_scheduled_sync(self):
        """Internal method to run sync from scheduler. 仅同步 bangumi-data 映射表"""
        log_audit("Bangumi", "开始", "正在开始执行定时 Bangumi 同步任务...")
        try:
            # 优先从系统设置读取 GitHub Token
            github_token = None
            from .. import globals
            if globals.service and globals.service.configuration_service:
                github_token = globals.service.configuration_service.get_config().get("github_token")
            # 兼容旧配置文件中的 token
            if not github_token:
                config = self._load_manager_config()
                github_token = config.get("github_token")

            if globals.bangumi_data_sync_service:
                log_audit("Bangumi", "开始", "正在同步 bangumi-data 映射表...")
                success = await globals.bangumi_data_sync_service.run_scheduled_sync(github_token)
                if success:
                    log_audit("Bangumi", "完成", "[AutoSync] bangumi-data 映射表同步完成")
                else:
                    log_audit("Bangumi", "失败", "[AutoSync] bangumi-data 映射表同步未执行或失败", level="WARN")
        except Exception as e:
            log_audit("Bangumi", "失败", f"定时同步失败: {e}", level="ERROR")