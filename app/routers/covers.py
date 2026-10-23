from fastapi import APIRouter, Form, HTTPException, Body
from typing import List, Optional, Dict
from pydantic import BaseModel
from app.services.cover_generator import cover_generator
from app.services.cover_config_manager import load_config, save_config
from app.logger import logger, log_audit
from app import globals

router = APIRouter(prefix="/api/covers", tags=["封面生成"])

class GenerateRequest(BaseModel):
    library_ids: List[str]
    style_type: str
    title_zh: Optional[str] = ""
    title_en: Optional[str] = ""
    font_zh: str
    font_en: str
    zh_font_size_ratio: float = 1.0
    en_font_size_ratio: float = 1.0
    blur_size: int = 50
    color_ratio: float = 0.8
    sort_by: str = "Random"
    is_blur: bool = False
    upload: bool = False
    title_config: Optional[str] = "" 
    use_primary_first: bool = False
    animation_format: Optional[str] = "gif"

class UploadRequest(BaseModel):
    library_id: str
    image: str

@router.get("/config", summary="获取封面配置")
async def get_config_endpoint():
    """获取保存的封面生成器配置。"""
    return load_config()

@router.post("/config", summary="保存封面配置")
async def save_config_endpoint(config: dict):
    """保存封面生成器的配置。"""
    save_config(config)
    log_audit("封面", "保存配置", f"样式: {config.get('style_type', '-')}, 字体: {config.get('font_zh', '-')}/{config.get('font_en', '-')}")
    return {"success": True}

@router.get("/fonts", summary="获取可用字体")
async def get_fonts():
    """获取服务器上可用的中英文字体列表。"""
    return {"fonts": cover_generator.get_available_fonts()}

@router.get("/libraries", summary="获取媒体库列表")
async def get_libraries():
    """获取 Emby 服务器的媒体库视图列表。"""
    if not globals.service or not globals.service.emby_client:
        raise HTTPException(status_code=503, detail="Emby 客户端未连接")
    
    try:
        await globals.service.emby_client._ensure_user_id()
        uid = globals.service.emby_client.user_id
        data, err = await globals.service.emby_client._make_request("GET", f"/Users/{uid}/Views")
        if not err and data and data.get("Items"):
            return {"libraries": [{"Id": i["Id"], "Name": i["Name"], "Type": i.get("CollectionType", "mixed")} for i in data["Items"]]}
        return {"libraries": []}
    except Exception as e:
        log_audit("封面", "失败", f"获取媒体库失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload", summary="上传封面图片")
async def upload_cover_endpoint(req: UploadRequest):
    """
    手动上传一个 Base64 格式的封面图片到指定的 Emby 媒体库。
    """
    try:
        log_audit("封面", "开始", f"正在上传手动封面到 {req.library_id}")
        await cover_generator.upload_cover(req.library_id, req.image)
        return {"success": True, "message": "上传成功"}
    except Exception as e:
        log_audit("封面", "失败", f"上传失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", summary="生成封面图片")
async def generate_cover(req: GenerateRequest):
    """
    根据配置生成封面图片。支持多媒体库批量处理和自动上传。
    """
    if not req.library_ids:
        raise HTTPException(status_code=400, detail="未选择任何媒体库")

    if not globals.service or not globals.service.emby_client:
        raise HTTPException(status_code=503, detail="Emby 客户端未连接")

    try:
        # Save config on generate (auto-save preference)
        save_data = req.dict()
        save_data.pop('library_ids', None)
        save_data.pop('upload', None)
        save_config(save_data)

        # Parse title config map
        title_map = cover_generator.parse_title_config(req.title_config)
        
        last_image = None
        processed_count = 0
        
        for lib_id in req.library_ids:
            # 1. Get Library Name
            lib_name = "Unknown"
            details, err = await globals.service.emby_client.get_item_details(lib_id)
            if details:
                lib_name = details.get("Name", "Unknown")
            
            # 2. Determine Titles
            # Priority: Config Map > Manual Input (if single lib selected) > Library Name
            
            final_title_zh = lib_name
            final_title_en = ""
            
            if lib_name in title_map:
                titles = title_map[lib_name]
                if len(titles) > 0: final_title_zh = titles[0]
                if len(titles) > 1: final_title_en = titles[1]
                log_audit("封面", "处理", f"已应用 '{lib_name}' 的标题配置: {final_title_zh} / {final_title_en}")
            elif len(req.library_ids) == 1 and req.title_zh:
                # Fallback to manual input only if no map entry exists
                final_title_zh = req.title_zh
                final_title_en = req.title_en
                log_audit("封面", "处理", f"使用手动输入标题 '{lib_name}': {final_title_zh}")
            else:
                log_audit("封面", "处理", f"使用默认媒体库名称 '{lib_name}'")
            # 3. Generate
            log_audit("封面", "开始", f"正在为媒体库 '{lib_name}' (ID: {lib_id}) 生成封面")
            base64_img = await cover_generator.generate_cover(
                library_id=lib_id,
                style_type=req.style_type,
                title_zh=final_title_zh,
                title_en=final_title_en,
                font_zh=req.font_zh,
                font_en=req.font_en,
                zh_scale=req.zh_font_size_ratio,
                en_scale=req.en_font_size_ratio,
                blur=req.blur_size,
                color_ratio=req.color_ratio,
                is_blur=req.is_blur,
                sort_by=req.sort_by,
                use_primary_first=req.use_primary_first,
                animation_format=req.animation_format
            )
            
            last_image = base64_img
            
            # 4. Upload if requested
            if req.upload:
                await cover_generator.upload_cover(lib_id, base64_img)
                log_audit("封面", "下载", f"已上传 '{lib_name}' 的封面")
            processed_count += 1

        msg = "生成预览成功" if not req.upload else f"成功处理 {processed_count} 个媒体库"
        
        image_data = None
        if last_image:
            # Simple detection of image type from base64
            mime = "image/png"
            if last_image.startswith("R0lGOD"):
                mime = "image/gif"
            elif last_image.startswith("UklGR"):
                mime = "image/webp"
            image_data = f"data:{mime};base64,{last_image}"

        return {
            "image": image_data,
            "message": msg
        }

    except Exception as e:
        log_audit("封面", "失败", f"生成封面失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
