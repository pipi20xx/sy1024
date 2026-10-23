import os
import asyncio
from typing import Dict, Any, Tuple, Optional, List, Union

from ...common import (
    SOURCE_OVERRIDE,
    SOURCE_PRIMARY,
    deep_merge_dict
)
from ...logger import log_audit
from .. import patches as patch_store


class EditorBaseMixin:
    """EditorService 的基础 mixin：初始化和通用辅助方法。"""

    def __init__(self, configuration_service, scanner_service, emby_integration_service, actor_service):
        self.configuration_service = configuration_service
        self.scanner_service = scanner_service
        self.actor_service = actor_service
        self.emby_integration_service = emby_integration_service
        self.emby_collection_service = None  # Injected later via main.py or setter

    def _get_cache_path_for_source(self, source: str) -> Optional[str]:
        return self.configuration_service.get_cache_path_for_source(source)

    def _merge_credits_lists(self, existing_list: List[Dict[str, Any]], new_list: List[Dict[str, Any]], key_type: str = "cast", label: str = "") -> List[Dict[str, Any]]:
        """
        通用演职员合并逻辑。
        判断依据：(TMDB ID, 角色名/职位)。
        """
        if not new_list:
            return existing_list

        # 统计信息
        new_count = 0
        merged_count = 0

        if not existing_list:
            # 如果现有列表为空，直接填充并返回，但也记录日志
            log_audit("编辑", "处理", f"  [载入演职员] 来源:{label} | 新增:{len(new_list)}人")
            return new_list

        merged_map = {}

        def get_key(p):
            pid = p.get("id")
            if key_type == "cast":
                char = p.get("character") or ""
                if pid: return (int(pid), str(char).strip())
                return (str(p.get("name")).strip(), str(char).strip())
            else:
                job = p.get("job") or ""
                if pid: return (int(pid), str(job).strip())
                return (str(p.get("name")).strip(), str(job).strip())

        # 填充现有数据
        for item in existing_list:
            key = get_key(item)
            merged_map[key] = item

        # 合并新数据
        for item in new_list:
            key = get_key(item)
            name = item.get("name")
            char = item.get("character") or item.get("job")
            tmdb_id = item.get("id")

            if key in merged_map:
                # 如果已存在
                existing = merged_map[key]
                if not existing.get("profile_path") and item.get("profile_path"):
                    existing["profile_path"] = item["profile_path"]

                merged_count += 1
                # 打印详细合并日志 (改为 INFO)
                log_audit("编辑", "处理", f"  [合并演职员] 来源:{label} | 已存在: ID={tmdb_id}, 姓名={name}, 角色/职位={char}")
            else:
                merged_map[key] = item
                new_count += 1

        if new_count > 0 or merged_count > 0:
            log_audit("编辑", "处理", f"  [合并统计] 来源:{label} | 新增:{new_count} | 重复:{merged_count}")
        return list(merged_map.values())

    def is_override_cache_configured(self) -> bool:
        return bool(self.configuration_service.get("override_cache_path"))

    def _get_actual_json_path(self, item_type: str, item_id: str, filename: str) -> Optional[str]:
        for source_type in [SOURCE_OVERRIDE, SOURCE_PRIMARY]:
            base_path = self._get_cache_path_for_source(source_type)
            if base_path:
                path = os.path.join(base_path, item_type, item_id, filename)
                if os.path.isfile(path):
                    return path
        return None

    def _is_primary_path(self, path: str) -> bool:
        """检查给定路径是否位于 Primary 缓存目录内。"""
        primary_base = self._get_cache_path_for_source(SOURCE_PRIMARY)
        if primary_base:
            return os.path.abspath(path).startswith(os.path.abspath(primary_base) + os.sep)
        return False

    def _sync_patches_if_exist(self, json_path: str, updated_data: Dict[str, Any]):
        """
        如果 patches 目录中存在同名的 patch 文件，同步更新已被 patch 的字段。
        确保用户通过编辑表单修改的值不会被 patches 中的旧值覆盖。

        只更新 patches 中已存在的 key（即「锁定」的字段），不会向 patches 中新增字段。
        实际读写在 app/services/patches.py，保证与模拟器的读取语义一致。
        """
        patch_filename = os.path.basename(json_path)
        try:
            if patch_store.sync_patch_fields(json_path, updated_data):
                log_audit("编辑", "更新", f"已同步更新 patches/{patch_filename} 中被 patch 的字段")
        except Exception as e:
            log_audit("编辑", "更新", f"同步更新 patches/{patch_filename} 失败: {e}", level="WARN")
