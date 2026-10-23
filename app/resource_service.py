import os
import json
from typing import Dict, Any, List, Tuple
from fastapi import UploadFile

from app.logger import log_audit

class ResourceService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def _get_attachment_dir(self, item_type: str, item_id: str, create: bool = False) -> Tuple[bool, str]:
        """获取附件目录路径，并可选择创建它。"""
        resource_path = self.config.get("resource_info_path")
        if not resource_path:
            return False, "“资源信息路径”未配置，请在设置中指定。"
        
        attachment_dir = os.path.join(resource_path, item_type, item_id, "attachments")
        if create:
            try:
                os.makedirs(attachment_dir, exist_ok=True)
            except OSError as e:
                log_audit("资源", "创建", f"创建附件目录失败 '{attachment_dir}': {e}", level="ERROR")
                return False, f"创建附件目录失败: {e}"
        return True, attachment_dir

    def get_resources(self, item_type: str, item_id: str) -> Tuple[bool, Any]:
        """获取指定影视项目的资源列表。"""
        resource_path = self.config.get("resource_info_path")
        if not resource_path:
            return False, "“资源信息路径”未配置，请在设置中指定。"

        json_path = os.path.join(resource_path, item_type, item_id, "resources.json")

        if not os.path.isfile(json_path):
            return True, []

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return True, data
        except (IOError, json.JSONDecodeError) as e:
            log_audit("资源", "读取", f"读取资源文件失败 '{json_path}': {e}", level="ERROR")
            return False, f"读取资源文件失败: {e}"

    def save_resources(self, item_type: str, item_id: str, data: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """保存指定影视项目的资源列表，并清理孤立的附件。"""
        success, json_path = self._get_attachment_dir(item_type, item_id, create=True)
        if not success:
            return False, json_path
        
        target_dir = os.path.dirname(json_path)
        json_path = os.path.join(target_dir, "resources.json")

        # 1. 获取旧的附件列表以进行比较
        old_attachments = set()
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                    for item in old_data:
                        attachments = item.get('attachment')
                        if attachments:
                            if isinstance(attachments, list):
                                old_attachments.update(attachments)
                            else:
                                old_attachments.add(attachments)
            except (IOError, json.JSONDecodeError):
                pass # 如果旧文件有问题，忽略

        # 2. 获取新的附件列表
        new_attachments = set()
        for item in data:
            attachments = item.attachment if hasattr(item, 'attachment') else item.get('attachment')
            if attachments:
                if isinstance(attachments, list):
                    new_attachments.update(attachments)
                else:
                    new_attachments.add(attachments)

        # 3. 找出需要删除的附件
        attachments_to_delete = old_attachments - new_attachments
        for filename in attachments_to_delete:
            self.delete_attachment(item_type, item_id, filename)

        # 4. 保存新的 resources.json
        try:
            dumpable_data = [item.model_dump() if hasattr(item, 'model_dump') else item for item in data]
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(dumpable_data, f, indent=4, ensure_ascii=False)
            return True, "资源信息已成功保存。"
        except IOError as e:
            log_audit("资源", "写入", f"写入资源文件失败 '{json_path}': {e}", level="ERROR")
            return False, f"写入资源文件失败: {e}"

    async def save_attachment(self, item_type: str, item_id: str, file: UploadFile) -> Tuple[bool, str]:
        """保存上传的附件。"""
        success, attachment_dir = self._get_attachment_dir(item_type, item_id, create=True)
        if not success:
            return False, attachment_dir

        file_path = os.path.join(attachment_dir, file.filename)
        
        # 防止目录遍历攻击
        if os.path.commonprefix((os.path.realpath(file_path), attachment_dir)) != attachment_dir:
            return False, "检测到无效的文件名。"

        try:
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            return True, file.filename
        except IOError as e:
            log_audit("资源", "保存", f"保存附件失败 '{file_path}': {e}", level="ERROR")
            return False, f"保存附件失败: {e}"

    def get_attachment_path(self, item_type: str, item_id: str, filename: str) -> Tuple[bool, str]:
        """获取附件的完整路径。"""
        success, attachment_dir = self._get_attachment_dir(item_type, item_id)
        if not success:
            return False, attachment_dir
        
        file_path = os.path.join(attachment_dir, filename)
        
        if os.path.commonprefix((os.path.realpath(file_path), attachment_dir)) != attachment_dir:
            return False, "检测到无效的文件名。"
            
        if os.path.isfile(file_path):
            return True, file_path
        else:
            return False, "附件未找到。"

    def delete_attachment(self, item_type: str, item_id: str, filename: str) -> bool:
        """删除指定的附件文件。"""
        success, file_path = self.get_attachment_path(item_type, item_id, filename)
        if success:
            try:
                os.remove(file_path)
                log_audit("资源", "删除", f"已删除附件: {file_path}", level="CLEAN")
                return True
            except OSError as e:
                log_audit("资源", "删除", f"删除附件失败 '{file_path}': {e}", level="ERROR")
        return False
