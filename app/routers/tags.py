from fastapi import APIRouter, HTTPException
from .. import globals
from ..schemas import (
    TagRuleCreateUpdate, ItemTagRequest, ItemTagDeleteRequest, CustomTagPresets
)
from app.logger import log_audit

router = APIRouter(tags=["标签管理"])

@router.get("/api/tags/rules", summary="获取标签规则")
async def get_all_tag_rules():
    """获取所有自动打标签的规则配置。"""
    return globals.tag_service.get_all_rules()

@router.post("/api/tags/rules", summary="创建标签规则")
async def create_tag_rule(rule_data: TagRuleCreateUpdate):
    """新增一条自动打标签规则。"""
    result = globals.tag_service.create_rule(rule_data.dict())
    log_audit("标签", "创建规则", f"规则: {rule_data.dict().get('name', 'N/A')}", level="SUCCESS")
    return result

@router.put("/api/tags/rules/{rule_id}", summary="更新标签规则")
async def update_tag_rule(rule_id: str, rule_data: TagRuleCreateUpdate):
    """修改已有的自动打标签规则。"""
    updated_rule = globals.tag_service.update_rule(rule_id, rule_data.dict())
    if not updated_rule:
        raise HTTPException(status_code=404, detail="标签规则未找到。")
    log_audit("标签", "更新规则", f"ID: {rule_id}")
    return updated_rule

@router.delete("/api/tags/rules/{rule_id}", summary="删除标签规则")
async def delete_tag_rule(rule_id: str):
    """删除特定的自动打标签规则。"""
    if not globals.tag_service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="标签规则未找到。")
    log_audit("标签", "删除规则", f"ID: {rule_id}", level="CLEAN")
    return {"message": "标签规则已成功删除。"}

@router.get("/api/tags/editor-info/{item_type}/{item_id}", summary="获取标签编辑信息")
async def get_tag_editor_info(item_type: str, item_id: str):
    """获取指定项目的标签状态及可用预设标签。"""
    success, data_or_msg = await globals.tag_service.get_tag_editor_info(item_type, item_id)
    if not success:
        raise HTTPException(status_code=404, detail=data_or_msg)
    return data_or_msg

@router.post("/api/tags/item/{item_type}/{item_id}", summary="为项目添加标签")
async def add_item_tags(item_type: str, item_id: str, request: ItemTagRequest):
    """为指定项目手动添加标签。"""
    success, message = await globals.tag_service.add_tags_to_item(item_type, item_id, request.tags_to_add, request.mode)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    tag_desc = f"标签: {request.tags_to_add}" if request.tags_to_add else "自动生成标签"
    log_audit("标签", "添加", f"类型: {item_type}, ID: {item_id}, 模式: {request.mode}, {tag_desc}", level="SUCCESS")
    return {"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)}

@router.delete("/api/tags/item/{item_type}/{item_id}", summary="从项目删除标签")
async def delete_item_tags(item_type: str, item_id: str, request: ItemTagDeleteRequest):
    """从指定项目中移除特定的标签。"""
    success, message = await globals.tag_service.delete_tags_from_item(item_type, item_id, request.tags_to_delete)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    log_audit("标签", "移除", f"类型: {item_type}, ID: {item_id}, 标签: {request.tags_to_delete}")
    return {"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)}

@router.delete("/api/tags/item/{item_type}/{item_id}/all", summary="删除项目所有标签")
async def delete_all_item_tags(item_type: str, item_id: str):
    """清空指定项目关联的所有标签。"""
    success, message = await globals.tag_service.delete_item_tags(item_type, item_id)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    log_audit("标签", "清空", f"类型: {item_type}, ID: {item_id}", level="CLEAN")
    return {"message": message, "success": True, "updated_details": await globals.service.editor_service.get_item_full_details(item_type, item_id)}

@router.get("/api/tags/custom-presets", summary="获取自定义标签预设")
async def get_custom_tag_presets():
    """获取所有用户定义的自定义标签及其表情。"""
    return globals.tag_service._load_custom_tags()

@router.post("/api/tags/custom-presets", summary="保存自定义标签预设")
async def save_custom_tag_presets(presets: CustomTagPresets):
    """更新并保存自定义标签预设列表。"""
    success, message = globals.tag_service.save_custom_tags(presets.dict(__root__=True))
    if not success:
        raise HTTPException(status_code=500, detail=message)
    log_audit("标签", "更新预设", "自定义标签预设已保存")
    return {"message": message, "success": True}
