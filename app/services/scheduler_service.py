import json
import asyncio
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.future import select
from app import globals
from app.database import TasksSessionLocal
from app.models import ScheduledTask
from app.logger import logger, log_audit

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    def start(self):
        if not self.is_running:
            self.scheduler.start()
            self.is_running = True
            log_audit("调度", "初始化", "APScheduler 已启动")
            # 启动后加载任务
            asyncio.create_task(self.initialize_scheduler())

    async def initialize_scheduler(self):
        """初始化调度器：迁移旧任务、创建默认任务并加载新任务"""
        await self.check_and_migrate_old_tasks()
        await self.ensure_default_tasks()
        await self.load_all_tasks()

    async def check_and_migrate_old_tasks(self):
        """从旧配置迁移自动备份和清理任务到数据库"""
        try:
            async with TasksSessionLocal() as session:
                # 检查是否已经迁移过（通过名称判断）
                result = await session.execute(select(ScheduledTask).where(ScheduledTask.task_type.in_(['backup', 'preview_cleanup'])))
                if result.scalars().first():
                    return # 已经有这些任务了，不再迁移

                config = globals.service.configuration_service.get_config()
                
                # 1. 迁移自动备份
                if config.get("auto_backup_enabled", False):
                    interval = config.get("auto_backup_interval_hours", 24)
                    # 简单转换间隔为 CRON (每 X 小时)
                    cron = f"0 */{int(interval)} * * *" if interval < 24 else "0 3 * * *"
                    
                    backup_task = ScheduledTask(
                        name="自动备份 (已迁移)",
                        task_type="backup",
                        cron_expression=cron,
                        enabled=True,
                        params=json.dumps({
                            "mode": config.get("auto_backup_mode", "snapshot"),
                            "include_override": config.get("auto_backup_include_override", True),
                            "include_collections": config.get("auto_backup_include_collections", True)
                        })
                    )
                    session.add(backup_task)
                    log_audit("调度", "处理", "已将旧的自动备份配置迁移为定时任务")
                # 2. 迁移预览图清理 (默认每天凌晨 4 点)
                cleanup_task = ScheduledTask(
                    name="预览图自动清理",
                    task_type="preview_cleanup",
                    cron_expression="0 4 * * *",
                    enabled=True,
                    params=json.dumps({"max_age_hours": 24})
                )
                session.add(cleanup_task)
                
                # 3. 迁移 Bangumi 自动同步到统一定时任务
                result_bgm = await session.execute(select(ScheduledTask).where(ScheduledTask.task_type == 'bangumi_data_sync'))
                if not result_bgm.scalars().first():
                    from ..common import get_config_path
                    bgm_config_path = get_config_path('bgm_manager.json')
                    bgm_enabled = False
                    bgm_interval_days = 7
                    bgm_hour = 3
                    bgm_minute = 0
                    if os.path.exists(bgm_config_path):
                        try:
                            with open(bgm_config_path, 'r', encoding='utf-8') as f:
                                bgm_cfg = json.load(f)
                            bgm_enabled = bgm_cfg.get('enabled', False)
                            bgm_interval_days = bgm_cfg.get('interval_days', 7)
                            bgm_hour = bgm_cfg.get('hour', 3)
                            bgm_minute = bgm_cfg.get('minute', 0)
                        except Exception:
                            pass
                    if bgm_enabled:
                        cron_expr = f"{bgm_minute} {bgm_hour} */{bgm_interval_days} * *"
                        bgm_sync_task = ScheduledTask(
                            name="Bangumi-Data 映射表自动同步 (已迁移)",
                            task_type="bangumi_data_sync",
                            cron_expression=cron_expr,
                            enabled=True,
                            params=json.dumps({})
                        )
                        session.add(bgm_sync_task)
                        log_audit("调度", "更新", "已将旧的 Bangumi 自动同步配置迁移为定时任务")
                await session.commit()
        except Exception as e:
            log_audit("调度", "失败", f"迁移旧任务时出错: {e}", level="ERROR")
    async def ensure_default_tasks(self):
        """确保系统有默认的定时任务（如果不存在则创建）"""
        try:
            async with TasksSessionLocal() as session:
                # 检查是否已有 bangumi_data_sync 任务
                result = await session.execute(
                    select(ScheduledTask).where(ScheduledTask.task_type == 'bangumi_data_sync')
                )
                if not result.scalars().first():
                    # 创建默认的 bangumi-data 同步任务（每周一凌晨 3 点）
                    default_task = ScheduledTask(
                        name="Bangumi-Data 映射表同步",
                        task_type="bangumi_data_sync",
                        cron_expression="0 3 * * 1",  # 每周一凌晨 3 点
                        enabled=True,
                        params=json.dumps({})
                    )
                    session.add(default_task)
                    await session.commit()
                    log_audit("调度", "更新", "已创建默认的 Bangumi-Data 映射表同步定时任务")
        except Exception as e:
            log_audit("调度", "失败", f"创建默认任务时出错: {e}", level="ERROR")
    def stop(self):
        if self.is_running:
            self.scheduler.shutdown()
            self.is_running = False
            log_audit("调度", "处理", "APScheduler 已停止")
    async def load_all_tasks(self):
        """从数据库加载并调度所有已启用的任务"""
        async with TasksSessionLocal() as session:
            result = await session.execute(select(ScheduledTask).where(ScheduledTask.enabled == True))
            tasks = result.scalars().all()
            
            # 先清除现有所有任务（防止重复）
            for job in self.scheduler.get_jobs():
                self.scheduler.remove_job(job.id)
            
            for task in tasks:
                self.schedule_task(task)
            
            log_audit("调度", "处理", f"已从数据库加载并调度 {len(tasks)} 个任务")
    def schedule_task(self, task: ScheduledTask):
        """根据 ScheduledTask 对象调度一个任务"""
        try:
            job_id = f"task_{task.id}"
            
            # 如果任务已存在，先移除
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            cron_expr = task.cron_expression.strip()
            log_audit("调度", "开始", f"正在调度任务 '{task.name}', 表达式: '{cron_expr}'")
            trigger = CronTrigger.from_crontab(cron_expr)
            
            self.scheduler.add_job(
                self.execute_task,
                trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=3600 # 允许 1 小时内的错峰执行
            )
            log_audit("调度", "处理", f"已调度任务: {task.name} ({task.task_type}), 规则: {task.cron_expression}")
        except Exception as e:
            log_audit("调度", "失败", f"调度任务 {task.name} 失败: {e}", level="ERROR")
    async def execute_task(self, task_id: int, force: bool = False):
        """执行任务的核心逻辑

        Args:
            task_id: 任务 ID
            force: 是否强制执行（忽略 enabled 状态，用于手动触发）
        """
        async with TasksSessionLocal() as session:
            task = await session.get(ScheduledTask, task_id)
            if not task:
                return
            if not task.enabled and not force:
                return

            log_audit("调度", "开始", f"正在开始执行定时任务: {task.name} (ID: {task.id})")
            try:
                # 更新最后运行时间
                task.last_run = datetime.now().isoformat()
                await session.commit()
                
                params = json.loads(task.params) if task.params else {}
                
                if task.task_type == 'cover':
                    await self._run_cover_task(params)
                elif task.task_type == 'collection_poster':
                    await self._run_collection_poster_task(params)
                elif task.task_type == 'bangumi_data_sync':
                    await self._run_bangumi_data_sync_task(params)
                elif task.task_type == 'backup':
                    await self._run_backup_task(params)
                elif task.task_type == 'preview_cleanup':
                    await self._run_preview_cleanup_task(params)
                elif task.task_type == 'scan_library':
                    await self._run_scan_library_task(params)
                elif task.task_type == 'bangumi_sync':
                    await self._run_bangumi_sync_task(params)
                elif task.task_type == 'workflow':
                    await self._run_workflow_task(params)
                else:
                    log_audit("调度", "处理", f"未知任务类型: {task.task_type}", level="WARN")
                log_audit("调度", "完成", f"定时任务执行成功: {task.name}")
            except Exception as e:
                log_audit("调度", "失败", f"执行定时任务 {task.name} 时出错: {e}", level="ERROR")
    async def _run_cover_task(self, params: Dict[str, Any]):
        """执行封面生成任务"""
        if not globals.service or not globals.service.emby_client:
            log_audit("调度", "失败", "封面任务失败：Emby 客户端未就绪", level="ERROR")
            return
            
        from app.services.cover_generator import cover_generator
        
        library_ids = params.get('library_ids', [])
        if not library_ids:
            log_audit("调度", "跳过", "封面任务未指定媒体库，跳过", level="WARN")
            return
            
        style_type = params.get('style_type', 'single_1')
        upload = params.get('upload', True)
        
        # 解析标题配置（如果有）
        title_config = params.get('title_config', "")
        title_map = cover_generator.parse_title_config(title_config)
        
        for lib_id in library_ids:
            try:
                # 获取媒体库名称
                lib_name = "Unknown"
                details, err = await globals.service.emby_client.get_item_details(lib_id)
                if details:
                    lib_name = details.get("Name", "Unknown")
                
                final_title_zh = lib_name
                final_title_en = ""
                
                if lib_name in title_map:
                    titles = title_map[lib_name]
                    if len(titles) > 0: final_title_zh = titles[0]
                    if len(titles) > 1: final_title_en = titles[1]

                log_audit("调度", "开始", f"定时任务: 正在为媒体库 '{lib_name}' 生成封面...")
                base64_img = await cover_generator.generate_cover(
                    library_id=lib_id,
                    style_type=style_type,
                    title_zh=final_title_zh,
                    title_en=final_title_en,
                    font_zh=params.get('font_zh', 'multi_1_zh.ttf'),
                    font_en=params.get('font_en', 'multi_1_en.otf'),
                    zh_scale=params.get('zh_font_size_ratio', 1.0),
                    en_scale=params.get('en_font_size_ratio', 1.0),
                    blur=params.get('blur_size', 50),
                    color_ratio=params.get('color_ratio', 0.8),
                    is_blur=params.get('is_blur', False),
                    sort_by=params.get('sort_by', 'Random'),
                    use_primary_first=params.get('use_primary_first', False),
                    animation_format=params.get('animation_format', 'gif')
                )
                
                if upload and base64_img:
                    await cover_generator.upload_cover(lib_id, base64_img)
                    log_audit("调度", "下载", f"定时任务: 已上传媒体库 '{lib_name}' 的封面")
            except Exception as e:
                log_audit("调度", "失败", f"媒体库 {lib_id} 生成封面失败: {e}", level="ERROR")
    async def _run_collection_poster_task(self, params: Dict[str, Any]):
        """执行合集海报生成任务"""
        if not globals.service or not globals.service.emby_client:
            log_audit("调度", "失败", "合集海报任务失败：Emby 客户端未就绪", level="ERROR")
            return
            
        from app.services.collection_poster_service import collection_poster_service
        from app.database import CollectionsSessionLocal
        from app.models import LocalCollection
        
        filenames = []
        
        # 1. 尝试从 collection_names_str 解析文件名 (优先级最高)
        collection_names_str = params.get('collection_names_str')
        if collection_names_str:
            names = [n.strip() for n in collection_names_str.replace("，", ",").split(",") if n.strip()]
            if names:
                async with CollectionsSessionLocal() as session:
                    stmt = select(LocalCollection.filename).where(LocalCollection.collection_name.in_(names))
                    result = await session.execute(stmt)
                    found = result.scalars().all()
                    filenames.extend(found)
                    log_audit("调度", "处理", f"定时任务: 根据名称 '{collection_names_str}' 找到了 {len(filenames)} 个合集")
        # 2. 如果没有手动指定名称，尝试直接获取 filenames
        if not filenames:
            filenames = params.get('collection_filenames', [])
            
        # 3. 如果还是为空，则默认为处理所有合集
        if not filenames and not collection_names_str:
            async with CollectionsSessionLocal() as session:
                result = await session.execute(select(LocalCollection.filename))
                filenames = [r[0] for r in result.all()]
        
        if not filenames:
            log_audit("调度", "处理", "没有找到需要处理的合集")
            return
            
        log_audit("调度", "开始", f"定时任务: 开始批量为 {len(filenames)} 个合集生成海报")
        # 构造批量生成参数
        batch_params = {
            "style_type": params.get('style_type', 'circle_focus'),
            "show_zh": params.get('show_zh', True),
            "show_en": params.get('show_en', True),
            "font_zh": params.get('font_zh', 'multi_1_zh.ttf'),
            "font_en": params.get('font_en', 'multi_1_en.otf'),
            "zh_font_size_ratio": params.get('zh_font_size_ratio', 1.0),
            "en_font_size_ratio": params.get('en_font_size_ratio', 1.0),
            "offset_x": params.get('offset_x', 0),
            "offset_y": params.get('offset_y', 0),
            "resolution_scale": params.get('resolution_scale', 1.0),
            "seed": params.get('seed')
        }
        
        # 调用现有的批量生成任务
        await collection_poster_service.batch_generate_posters_task(filenames, batch_params)
        
        # [新增] 批量生成海报后，执行“应用所有到 Emby”以完成海报上传
        if globals.collection_service:
            log_audit("调度", "开始", "定时任务: 正在将生成的合集海报应用到 Emby...")
            # 注意：这里调用的是 task 版本，它会静默运行（进度通过 WebSocket 广播）
            await globals.collection_service.apply_all_collections_to_emby_task(target_filenames=filenames)
            log_audit("调度", "完成", "定时任务: 合集海报应用完成")
    async def _run_bangumi_data_sync_task(self, params: Dict[str, Any]):
        """执行 bangumi-data 映射表同步任务"""
        if not globals.bangumi_data_sync_service:
            log_audit("调度", "初始化", "bangumi-data 同步任务失败：服务未初始化", level="ERROR")
            return
        
        # 从应用配置读取 GitHub Token
        github_token = None
        if globals.service and globals.service.configuration_service:
            github_token = globals.service.configuration_service.get_config().get("github_token")
        
        log_audit("调度", "开始", "定时任务: 开始同步 bangumi-data 映射表...")
        success = await globals.bangumi_data_sync_service.run_scheduled_sync(github_token)
        if success:
            log_audit("调度", "完成", "定时任务: bangumi-data 映射表同步完成")
        else:
            log_audit("调度", "失败", "定时任务: bangumi-data 映射表同步未执行或失败", level="WARN")
    async def _run_backup_task(self, params: Dict[str, Any]):
        """执行自动备份任务"""
        if not globals.backup_service:
            return
        
        log_audit("调度", "开始", "定时任务: 开始自动备份...")
        globals.backup_service.create_backup(
            mode=params.get("mode", "snapshot"),
            include_override=params.get("include_override", True),
            include_collections=params.get("include_collections", True),
            triggered_by='scheduled_task'
        )

    async def _run_preview_cleanup_task(self, params: Dict[str, Any]):
        """执行预览图清理任务"""
        from app.services.preview_generator import preview_service
        max_age_hours = params.get('max_age_hours', 24)
        log_audit("调度", "清理", f"定时任务: 清理 {max_age_hours} 小时前的预览图...")
        await preview_service.cleanup_old_previews(max_age_hours=max_age_hours)

    async def _run_scan_library_task(self, params: Dict[str, Any]):
        """执行扫描媒体库任务"""
        if not globals.service or not globals.service.scanner_service:
            log_audit("调度", "失败", "扫描任务失败：扫描服务未就绪", level="ERROR")
            return

        log_audit("调度", "开始", "定时任务: 开始扫描媒体库...")
        await globals.service.scanner_service.scan_all_data()
        log_audit("调度", "完成", "定时任务: 媒体库扫描完成")

    async def _run_bangumi_sync_task(self, params: Dict[str, Any]):
        """执行 Bangumi 映射同步到 Emby 的任务"""
        if not globals.emby_tag_writer_service:
            log_audit("调度", "失败", "Bangumi 同步任务失败：写入服务未初始化", level="ERROR")
            return

        log_audit("调度", "开始", "定时任务: 开始执行 Bangumi 映射同步到 Emby...")
        try:
            async for _ in globals.emby_tag_writer_service.sync_to_emby(params):
                pass  # Consume the SSE generator silently for scheduled execution
            log_audit("调度", "完成", "定时任务: Bangumi 映射同步完成")
        except Exception as e:
            log_audit("调度", "失败", f"定时任务: Bangumi 映射同步出错: {e}", level="ERROR")

    async def _run_workflow_task(self, params: Dict[str, Any]):
        """执行工作流任务"""
        import copy
        from app.routers.workflow import run_workflow_in_background

        item_type = params.get('item_type', 'tmdb-tv')
        tasks_list = copy.deepcopy(params.get('tasks', []))
        interval_seconds = params.get('interval_seconds', 2)
        item_ids = params.get('item_ids')
        filters = params.get('filters')

        if not tasks_list:
            log_audit("调度", "跳过", "工作流任务未配置任何步骤，跳过", level="WARN")
            return

        # 处理 child_fields 合并到 fields_to_update（前端保存的是原始结构，执行时需合并）
        for task in tasks_list:
            task_params = task.get('params', {})
            if task.get('type') == 'emby_update_metadata' and task_params.get('update_children') and task_params.get('child_fields'):
                task_params['fields_to_update'] = list(task_params.get('fields_to_update', [])) + list(task_params['child_fields'])
                del task_params['child_fields']
            if task.get('type') == 'tmdb_update_metadata' and task_params.get('update_season_episodes') and task_params.get('child_fields'):
                task_params['fields_to_update'] = list(task_params.get('fields_to_update', [])) + list(task_params['child_fields'])
                del task_params['child_fields']

        log_audit("调度", "开始", f"定时任务: 开始执行工作流 ({len(tasks_list)} 步)...")
        await run_workflow_in_background(
            item_type=item_type,
            tasks=tasks_list,
            interval_seconds=interval_seconds,
            item_ids=item_ids,
            filters=filters
        )
        log_audit("调度", "完成", "定时任务: 工作流执行完毕")

# 单例模式
scheduler_service = SchedulerService()
