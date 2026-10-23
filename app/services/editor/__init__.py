"""
EditorService — 元数据编辑服务。

原 editor.py (2015 行) 拆分为以下 mixin 模块，通过多继承组合为统一的 EditorService 类。
对外接口完全不变，所有 `from .editor import EditorService` 引用均可正常工作。

模块结构：
  - base.py             基础 mixin：初始化 + 通用辅助方法
  - external_updates.py  从 Bangumi / Emby 更新元数据
  - actors.py            演员导入 & 标准化
  - details.py           读取详情、加载季/集、聚合演职员
  - crud.py              元数据 CRUD（项目/季/集）
  - file_ops.py          复制到 Override、锁定名称 (Patches)
  - ai_translate.py      AI 翻译
  - delete.py            所有删除操作
  - special_files.py     剧集组 / 排序 / 外部 ID
"""

from .base import EditorBaseMixin
from .external_updates import ExternalUpdatesMixin
from .actors import ActorsMixin
from .details import DetailsMixin
from .crud import MetadataCrudMixin
from .file_ops import FileOpsMixin
from .ai_translate import AiTranslateMixin
from .delete import DeleteMixin
from .special_files import SpecialFilesMixin


class EditorService(
    EditorBaseMixin,
    ExternalUpdatesMixin,
    ActorsMixin,
    DetailsMixin,
    MetadataCrudMixin,
    FileOpsMixin,
    AiTranslateMixin,
    DeleteMixin,
    SpecialFilesMixin,
):
    """元数据编辑服务（由多个 mixin 组合而成）。"""
    pass
