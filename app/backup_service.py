# app/backup_service.py [已实现备份来源标识]

import os
import shutil
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any

from app.logger import log_audit

class BackupService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.backup_path = self.config.get("backup_path")
        self.override_path = self.config.get("override_cache_path")
        self.collections_path = self.config.get("emby_collections_path")
        
        data_path = self.config.get("data_path")
        if data_path:
            self.config_file_path = os.path.join(data_path, "tmdb_browser_config.json")
        else:
            self.config_file_path = None

        self.is_enabled = bool(self.backup_path and os.path.isdir(self.backup_path))

        if self.is_enabled:
            log_audit("备份", "初始化", f"BackupService 初始化成功，使用目录: {self.backup_path}", level="SUCCESS")
        else:
            log_audit("备份", "初始化", f"备份目录 '{self.backup_path}' 未配置或无效，备份功能将不可用", level="WARN")
            
    def _cleanup_old_snapshots(self):
        max_snapshots = self.config.get("auto_backup_max_snapshots")
        if not isinstance(max_snapshots, int) or max_snapshots <= 0:
            return

        log_audit("备份", "清理", f"开始清理旧快照，将保留最新的 {max_snapshots} 个")
        try:
            # [修改] 只清理自动备份的快照，手动快照将被永久保留
            all_auto_snapshots = sorted([
                d for d in os.listdir(self.backup_path) 
                if os.path.isdir(os.path.join(self.backup_path, d)) and d.startswith("snapshot-") and d.endswith("_auto")
            ])
            
            if len(all_auto_snapshots) > max_snapshots:
                snapshots_to_delete = all_auto_snapshots[:-max_snapshots]
                log_audit("备份", "清理", f"找到 {len(snapshots_to_delete)} 个需要删除的旧自动快照")
                for snapshot_name in snapshots_to_delete:
                    path_to_delete = os.path.join(self.backup_path, snapshot_name)
                    try:
                        shutil.rmtree(path_to_delete)
                        log_audit("备份", "清理", f"已成功删除旧自动快照: {snapshot_name}", level="CLEAN")
                    except Exception as e:
                        log_audit("备份", "清理", f"删除旧自动快照 '{snapshot_name}' 时失败: {e}", level="ERROR")
        except Exception as e:
            log_audit("备份", "清理", f"清理旧快照时发生错误: {e}", level="ERROR")

    def _create_zip_backup(self, include_override: bool, include_collections: bool, triggered_by: str) -> Tuple[bool, str]:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # [核心修改] 根据触发方式添加文件名后缀
        suffix = "_auto" if triggered_by == 'auto' else ''
        backup_name = f"backup-{timestamp}{suffix}"
        
        backup_target_base = os.path.join(self.backup_path, backup_name)
        temp_backup_dir = f"/tmp/{backup_name}"
        os.makedirs(temp_backup_dir, exist_ok=True)
        
        backup_metadata = { "created_at": timestamp, "type": "zip", "contents": { "override_cache": include_override, "collections": include_collections } }
        with open(os.path.join(temp_backup_dir, "backup_meta.json"), 'w', encoding='utf-8') as f: json.dump(backup_metadata, f, indent=2)

        try:
            if include_override and self.override_path and os.path.isdir(self.override_path): shutil.copytree(self.override_path, os.path.join(temp_backup_dir, "override_cache"))
            if include_collections and self.collections_path and os.path.isdir(self.collections_path): shutil.copytree(self.collections_path, os.path.join(temp_backup_dir, "collections"))
            if self.config_file_path and os.path.isfile(self.config_file_path): shutil.copy2(self.config_file_path, os.path.join(temp_backup_dir, os.path.basename(self.config_file_path)))
            
            shutil.make_archive(backup_target_base, 'zip', temp_backup_dir)
            return True, f"成功创建压缩包备份: {backup_name}.zip"
        finally:
            if os.path.exists(temp_backup_dir): shutil.rmtree(temp_backup_dir)

    def _get_latest_snapshot_dir(self) -> Optional[str]:
        if not self.backup_path or not os.path.isdir(self.backup_path): return None
        all_snapshots = [d for d in os.listdir(self.backup_path) if os.path.isdir(os.path.join(self.backup_path, d)) and d.startswith("snapshot-")]
        if not all_snapshots: return None
        return os.path.join(self.backup_path, sorted(all_snapshots)[-1])

    def _create_snapshot_backup(self, include_override: bool, include_collections: bool, triggered_by: str) -> Tuple[bool, str]:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # [核心修改] 根据触发方式添加文件名后缀
        suffix = "_auto" if triggered_by == 'auto' else ''
        snapshot_name = f"snapshot-{timestamp}{suffix}"
        
        snapshot_path = os.path.join(self.backup_path, snapshot_name)
        os.makedirs(snapshot_path, exist_ok=True)
        
        latest_snapshot_path = self._get_latest_snapshot_dir()
        
        backup_metadata = { "created_at": timestamp, "type": "snapshot", "contents": { "override_cache": include_override, "collections": include_collections } }
        with open(os.path.join(snapshot_path, "backup_meta.json"), 'w', encoding='utf-8') as f: json.dump(backup_metadata, f, indent=2)

        sources_to_backup = {}
        if include_override and self.override_path: sources_to_backup['override_cache'] = self.override_path
        if include_collections and self.collections_path: sources_to_backup['collections'] = self.collections_path
            
        for name, source_path in sources_to_backup.items():
            target_path = os.path.join(snapshot_path, name)
            latest_backup_source_path = os.path.join(latest_snapshot_path, name) if latest_snapshot_path else None
            self._create_incremental_snapshot_dir(source_path, target_path, latest_backup_source_path)
            
        if triggered_by == 'auto':
            self._cleanup_old_snapshots()

        return True, f"成功创建快照备份: {snapshot_name}"

    def _create_incremental_snapshot_dir(self, source_dir: str, target_dir: str, latest_backup_dir: Optional[str]):
        os.makedirs(target_dir, exist_ok=True)
        for item_name in os.listdir(source_dir):
            source_item, target_item = os.path.join(source_dir, item_name), os.path.join(target_dir, item_name)
            latest_backup_item = os.path.join(latest_backup_dir, item_name) if latest_backup_dir and os.path.exists(latest_backup_dir) else None
            if os.path.isdir(source_item):
                self._create_incremental_snapshot_dir(source_item, target_item, latest_backup_item)
                continue
            file_unchanged = (latest_backup_item and os.path.isfile(latest_backup_item) and os.stat(source_item).st_mtime == os.stat(latest_backup_item).st_mtime and os.stat(source_item).st_size == os.stat(latest_backup_item).st_size)
            if file_unchanged:
                try: os.link(latest_backup_item, target_item)
                except OSError as e:
                    log_audit("备份", "快照", f"创建硬链接失败，回退到复制文件。错误: {e}", level="WARN"); shutil.copy2(source_item, target_item)
            else: shutil.copy2(source_item, target_item)
                
    def create_backup(self, mode: str, include_override: bool, include_collections: bool, triggered_by: str = 'manual') -> Tuple[bool, str]:
        if not self.is_enabled: return False, "备份服务未启用，请检查 backup_path 配置。"
        if not include_override and not include_collections: return False, "必须至少选择一项备份内容。"
        try:
            if mode == "zip":
                return self._create_zip_backup(include_override, include_collections, triggered_by)
            elif mode == "snapshot":
                return self._create_snapshot_backup(include_override, include_collections, triggered_by)
            else:
                return False, f"未知的备份模式: {mode}"
        except Exception as e:
            log_audit("备份", "创建", f"创建备份时发生错误: {e}", level="ERROR"); return False, f"创建备份时发生错误: {e}"

    def list_backups(self) -> List[Dict[str, str]]:
        if not self.is_enabled: return []
        backups = []
        try:
            for filename in os.listdir(self.backup_path):
                file_path = os.path.join(self.backup_path, filename)
                try:
                    is_auto = "_auto" in filename
                    if filename.startswith("backup-") and filename.endswith(".zip"):
                        ts_str = filename.replace("backup-", "").replace(".zip", "").replace("_auto", "")
                        dt_obj = datetime.strptime(ts_str, "%Y%m%d-%H%M%S")
                        file_size = os.path.getsize(file_path) / (1024 * 1024)
                        backups.append({ "filename": filename, "created_at": dt_obj.strftime("%Y-%m-%d %H:%M:%S"), "size_mb": f"{file_size:.2f} MB", "type": "zip", "triggered_by": "auto" if is_auto else "manual" })
                    elif filename.startswith("snapshot-") and os.path.isdir(file_path):
                        ts_str = filename.replace("snapshot-", "").replace("_auto", "")
                        dt_obj = datetime.strptime(ts_str, "%Y%m%d-%H%M%S")
                        backups.append({ "filename": filename, "created_at": dt_obj.strftime("%Y-%m-%d %H:%M:%S"), "size_mb": "N/A", "type": "snapshot", "triggered_by": "auto" if is_auto else "manual"})
                except (ValueError, OSError) as e: log_audit("备份", "列表", f"无法解析或读取备份文件/目录 '{filename}': {e}", level="WARN")
        except FileNotFoundError: log_audit("备份", "列表", f"备份目录不存在: {self.backup_path}", level="ERROR")
        return sorted(backups, key=lambda x: x["created_at"], reverse=True)

    def _recursive_merge_add(self, source_dir: str, target_dir: str):
        for item_name in os.listdir(source_dir):
            source_item_path, target_item_path = os.path.join(source_dir, item_name), os.path.join(target_dir, item_name)
            if os.path.isdir(source_item_path):
                if not os.path.exists(target_item_path): shutil.copytree(source_item_path, target_item_path)
                elif os.path.isdir(target_item_path): self._recursive_merge_add(source_item_path, target_item_path)
                else: log_audit("备份", "恢复", f"跳过目录复制，目标 '{target_item_path}' 已存在且不是目录", level="WARN")
            elif not os.path.exists(target_item_path): shutil.copy2(source_item_path, target_item_path)

    def _safe_restore_directory(self, source_dir: str, target_dir: str, mode: str):
        if not os.path.isdir(source_dir) or not target_dir: return
        os.makedirs(target_dir, exist_ok=True)
        log_audit("备份", "恢复", f"正在将 '{source_dir}' 的内容以 '{mode}' 模式恢复到 '{target_dir}'")
        if mode == "clean_restore":
            for item_name in os.listdir(target_dir):
                item_path = os.path.join(target_dir, item_name)
                try:
                    if os.path.isdir(item_path): shutil.rmtree(item_path)
                    else: os.remove(item_path)
                except Exception as e: log_audit("备份", "恢复", f"清空时无法删除旧项目 '{item_path}': {e}", level="ERROR"); raise
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        elif mode == "overwrite": shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
        elif mode == "merge_add": self._recursive_merge_add(source_dir, target_dir)
        log_audit("备份", "恢复", f"目录 '{target_dir}' 的恢复操作完成", level="SUCCESS")

    def restore_backup(self, filename: str, mode: str) -> Tuple[bool, str]:
        if not self.is_enabled: return False, "备份服务未启用。"
        backup_path = os.path.join(self.backup_path, filename); is_zip = backup_path.endswith(".zip")
        if ".." in filename or (is_zip and not os.path.isfile(backup_path)) or (not is_zip and not os.path.isdir(backup_path)): return False, "无效或不存在的备份文件。"
        temp_extract_dir = f"/tmp/restore-{os.path.splitext(filename)[0]}"
        if os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)
        try:
            if is_zip: shutil.unpack_archive(backup_path, temp_extract_dir)
            else: temp_extract_dir = backup_path
            backup_meta_path = os.path.join(temp_extract_dir, "backup_meta.json")
            if not os.path.isfile(backup_meta_path): return False, "备份文件/目录已损坏或格式不兼容。"
            with open(backup_meta_path, 'r', encoding='utf-8') as f: backup_meta = json.load(f)
            if backup_meta.get("contents", {}).get("override_cache"): self._safe_restore_directory(os.path.join(temp_extract_dir, "override_cache"), self.override_path, mode)
            if backup_meta.get("contents", {}).get("collections"): self._safe_restore_directory(os.path.join(temp_extract_dir, "collections"), self.collections_path, mode)
            if self.config_file_path:
                backup_config_file = os.path.join(temp_extract_dir, os.path.basename(self.config_file_path))
                if os.path.isfile(backup_config_file): shutil.copy2(backup_config_file, self.config_file_path)
            return True, "数据恢复成功！系统将自动在后台进行一次完整的重新扫描以同步状态。"
        except Exception as e:
            log_audit("备份", "恢复", f"从 '{filename}' 恢复数据时发生严重错误: {e}", level="ERROR"); return False, f"恢复失败: {e}"
        finally:
            if is_zip and os.path.exists(temp_extract_dir): shutil.rmtree(temp_extract_dir)

    def delete_backup(self, filename: str) -> Tuple[bool, str]:
        if not self.is_enabled: return False, "备份服务未启用。"
        path_to_delete = os.path.join(self.backup_path, filename)
        if ".." in filename: return False, "无效的备份文件名。"
        try:
            if path_to_delete.endswith(".zip") and os.path.isfile(path_to_delete): os.remove(path_to_delete)
            elif os.path.isdir(path_to_delete): shutil.rmtree(path_to_delete)
            else: return False, f"找不到要删除的备份: '{filename}'"
            return True, f"已成功删除备份 '{filename}'。"
        except OSError as e:
            log_audit("备份", "删除", f"删除备份 '{filename}' 失败: {e}", level="ERROR"); return False, f"删除时出错: {e}"

    # --- [新增] Item-specific Backup Methods ---

    def _get_item_backup_dir(self) -> str:
        item_backup_path = os.path.join(self.backup_path, "item_backups")
        os.makedirs(item_backup_path, exist_ok=True)
        return item_backup_path

    def list_item_backups(self, item_type: str, item_id: str) -> List[Dict[str, Any]]:
        if not self.is_enabled:
            return []
        
        item_backup_dir = self._get_item_backup_dir()
        prefix = f"{item_id}-{item_type}-"
        backups = []

        for filename in os.listdir(item_backup_dir):
            if filename.startswith(prefix) and filename.endswith(".zip"):
                file_path = os.path.join(item_backup_dir, filename)
                try:
                    stat = os.stat(file_path)
                    backups.append({
                        "name": filename,
                        "modified_time": stat.st_mtime,
                        "size": stat.st_size,
                    })
                except OSError as e:
                    log_audit("备份", "列表", f"无法读取备份文件 '{filename}': {e}", level="WARN")
        
        return sorted(backups, key=lambda x: x["modified_time"], reverse=True)

    def create_item_backup(self, item_type: str, item_id: str) -> Tuple[bool, str]:
        if not self.override_path or not os.path.isdir(self.override_path):
            return False, "Override cache path not configured."

        item_override_path = os.path.join(self.override_path, item_type, item_id)
        if not os.path.isdir(item_override_path):
            return False, "项目不在覆盖缓存中，无需备份。"

        item_backup_dir = self._get_item_backup_dir()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{item_id}-{item_type}-{timestamp}"
        backup_archive_base = os.path.join(item_backup_dir, backup_name)

        try:
            shutil.make_archive(backup_archive_base, 'zip', item_override_path)
            return True, f"成功创建项目备份: {backup_name}.zip"
        except Exception as e:
            log_audit("备份", "创建", f"创建项目备份时出错: {e}", level="ERROR")
            return False, f"创建项目备份失败: {e}"

    def restore_item_backup(self, item_type: str, item_id: str, backup_name: str) -> Tuple[bool, str]:
        if not self.override_path:
            return False, "Override cache path not configured."

        item_backup_dir = self._get_item_backup_dir()
        backup_path = os.path.join(item_backup_dir, backup_name)

        if ".." in backup_name or not os.path.isfile(backup_path):
            return False, "无效或不存在的备份文件。"

        item_override_path = os.path.join(self.override_path, item_type, item_id)
        
        try:
            # Clean restore: remove existing folder and unpack archive
            if os.path.exists(item_override_path):
                shutil.rmtree(item_override_path)
            
            os.makedirs(item_override_path, exist_ok=True)
            shutil.unpack_archive(backup_path, item_override_path)
            
            return True, "项目备份已成功恢复。"
        except Exception as e:
            log_audit("备份", "恢复", f"恢复项目备份时出错: {e}", level="ERROR")
            return False, f"恢复项目备份失败: {e}"

    def delete_item_backup(self, item_type: str, item_id: str, backup_name: str) -> Tuple[bool, str]:
        item_backup_dir = self._get_item_backup_dir()
        path_to_delete = os.path.join(item_backup_dir, backup_name)

        if ".." in backup_name or not os.path.isfile(path_to_delete):
            return False, f"找不到要删除的备份: '{backup_name}'"
        
        try:
            os.remove(path_to_delete)
            return True, f"已成功删除备份 '{backup_name}'。"
        except OSError as e:
            log_audit("备份", "删除", f"删除备份 '{backup_name}' 失败: {e}", level="ERROR")
            return False, f"删除时出错: {e}"

    # --- [新增] Export/Import Methods ---

    def get_export_zip_path(self, item_type: str, item_id: str) -> Tuple[bool, str, str]:
        """
        Creates a temporary zip file for export.
        Returns: (success, file_path, filename)
        """
        if not self.override_path or not os.path.isdir(self.override_path):
            return False, "Override cache path not configured.", ""

        item_override_path = os.path.join(self.override_path, item_type, item_id)
        if not os.path.isdir(item_override_path):
            return False, "项目不在覆盖缓存中，无法导出。", ""

        # Naming convention: tv-{tmdbid}.zip or movie-{tmdbid}.zip
        # Mapping item_type to prefix
        prefix_map = {
            "tmdb-tv": "tv",
            "tmdb-movies2": "movie"
        }
        prefix = prefix_map.get(item_type, item_type)
        filename = f"{prefix}-{item_id}.zip"
        
        # Use temp directory
        temp_dir = "/tmp/gemini_exports"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Clean up old exports in this temp dir (optional, simple cleanup)
        try:
            for f in os.listdir(temp_dir):
                fp = os.path.join(temp_dir, f)
                if os.path.isfile(fp) and (datetime.now().timestamp() - os.path.getmtime(fp) > 3600): # Delete older than 1 hour
                    os.remove(fp)
        except:
            pass

        target_zip_base = os.path.join(temp_dir, os.path.splitext(filename)[0])
        target_zip_file = target_zip_base + ".zip"

        try:
            # shutil.make_archive adds extension automatically
            shutil.make_archive(target_zip_base, 'zip', item_override_path)
            return True, target_zip_file, filename
        except Exception as e:
            log_audit("备份", "导出", f"导出项目失败: {e}", level="ERROR")
            return False, str(e), ""

    def process_import_zip(self, zip_file_path: str, original_filename: str) -> Tuple[bool, str]:
        """
        Processes an uploaded zip file. Infers item_type and item_id from filename.
        Filename format expected: tv-{id}.zip or movie-{id}.zip
        """
        if not self.override_path:
            return False, "Override cache path not configured."

        # Parse filename
        # Expected: tv-12345.zip or movie-12345.zip
        base_name = os.path.splitext(original_filename)[0]
        parts = base_name.split('-')
        
        if len(parts) < 2:
            return False, "文件名格式错误。必须是 'tv-{id}.zip' 或 'movie-{id}.zip'。"
        
        # Handle cases like "tv-12345-backup" just in case, but strict for now based on requirement
        # Requirement: "剧集就是tv-tmdbid 电影就是movie-tmdb这样子"
        
        type_prefix = parts[0]
        item_id = parts[1]
        
        # Map prefix to internal item_type
        if type_prefix == 'tv':
            item_type = 'tmdb-tv'
        elif type_prefix == 'movie':
            item_type = 'tmdb-movies2'
        else:
            return False, f"未知的类型前缀: {type_prefix}. 支持 'tv' 和 'movie'。"
            
        if not item_id.isdigit():
             return False, f"ID 无效: {item_id}"

        target_dir = os.path.join(self.override_path, item_type, item_id)
        
        try:
            os.makedirs(target_dir, exist_ok=True)
            # Use shutil.unpack_archive
            shutil.unpack_archive(zip_file_path, target_dir)
            return True, f"成功导入数据到 {item_type}/{item_id}"
        except Exception as e:
            log_audit("备份", "导入", f"导入压缩包失败: {e}", level="ERROR")
            return False, f"导入失败: {e}"

    # --- Collection Export/Import ---

    def get_collection_export_zip_path(self, collection_filename: str) -> Tuple[bool, str, str]:
        """
        Export a single collection (JSON + Images) to a zip.
        filename: e.g. "My Collection.json"
        """
        if not self.collections_path or not os.path.isdir(self.collections_path):
            return False, "Collections path not configured.", ""
            
        json_path = os.path.join(self.collections_path, collection_filename)
        if not os.path.isfile(json_path):
            return False, "Collection file not found.", ""

        # Load JSON to get clean name for zip
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                collection_name = data.get("collection_name", "Collection")
        except:
            collection_name = "Collection"

        # Safe filename for zip
        from .common import sanitize_filename
        safe_name = sanitize_filename(collection_name)
        zip_filename = f"{safe_name}.zip"

        # Temp dir
        temp_dir = "/tmp/gemini_collection_exports"
        os.makedirs(temp_dir, exist_ok=True)
        temp_stage_dir = os.path.join(temp_dir, safe_name)
        if os.path.exists(temp_stage_dir):
            shutil.rmtree(temp_stage_dir)
        os.makedirs(temp_stage_dir, exist_ok=True)

        try:
            # Copy JSON
            shutil.copy2(json_path, os.path.join(temp_stage_dir, collection_filename))
            
            # Copy Images
            base_name = os.path.splitext(collection_filename)[0]
            suffixes = ["_poster.jpg", "_fanart.jpg", "_logo.png"]
            for suffix in suffixes:
                img_name = f"{base_name}{suffix}"
                src = os.path.join(self.collections_path, img_name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(temp_stage_dir, img_name))
            
            # Zip it
            zip_base = os.path.join(temp_dir, safe_name) # make_archive adds .zip
            shutil.make_archive(zip_base, 'zip', temp_stage_dir)
            
            return True, f"{zip_base}.zip", zip_filename
        except Exception as e:
            log_audit("备份", "导出", f"导出合集失败: {e}", level="ERROR")
            return False, str(e), ""
        finally:
            if os.path.exists(temp_stage_dir):
                shutil.rmtree(temp_stage_dir)

    def process_collection_import_zip(self, zip_file_path: str) -> Tuple[bool, str]:
        """
        Unpacks a collection zip into the collections folder.
        Does NOT update DB. Caller must trigger DB sync.
        """
        if not self.collections_path:
            return False, "Collections path not configured."
            
        try:
            shutil.unpack_archive(zip_file_path, self.collections_path)
            return True, "Collection imported successfully."
        except Exception as e:
            log_audit("备份", "导入", f"导入合集压缩包失败: {e}", level="ERROR")
            return False, str(e)
