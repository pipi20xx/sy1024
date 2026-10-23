import base64
import random
from io import BytesIO
from typing import List, Tuple, Union, Any, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance
from app.logger import logger, log_audit

# Standard Canvas Size (Basis for 1x)
BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def fit_text_to_width(draw, text, font_path, max_width, initial_size):
    current_size = int(initial_size)
    try:
        font = ImageFont.truetype(str(font_path), current_size)
    except:
        font = ImageFont.load_default()
        return font, 12, 100, 20

    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    
    if width > max_width:
        ratio = max_width / width
        new_size = int(current_size * ratio * 0.95)
        if new_size < 10: new_size = 10
        try:
            font = ImageFont.truetype(str(font_path), new_size)
        except:
            font = ImageFont.load_default()
            return font, 12, 100, 20
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return font, new_size, width, height
    return font, current_size, width, height

def generate_style_single(
    image_paths: list,
    title_zh: str,
    title_en: str,
    font_path: Any,
    zh_font_size_ratio: float = 1.0,
    en_font_size_ratio: float = 1.0,
    offset_x: int = 0,
    offset_y: int = 0,
    resolution_scale: float = 1.0,
    return_layers: bool = False,
    seed: Optional[int] = None,
    **kwargs
):
    img = None
    try:
        if isinstance(font_path, (list, tuple)):
            zh_font_path = font_path[0]
            en_font_path = font_path[1] if len(font_path) > 1 else font_path[0]
        else:
            zh_font_path = font_path
            en_font_path = font_path

        current_w = int(BASE_WIDTH * resolution_scale)
        current_h = int(BASE_HEIGHT * resolution_scale)
        canvas_size = (current_w, current_h)
        scale = resolution_scale

        if not image_paths: return None
        
        # 1. 随机选一张图直接作为底图 (列表已被 service 基于 seed 洗过牌了)
        chosen_path = image_paths[0]
        img = Image.open(chosen_path).convert("RGB")
        
        # 直接铺满画布，不进行任何滤镜处理
        canvas = ImageOps.fit(img, canvas_size, method=Image.LANCZOS).convert("RGBA")

        # 2. 文字层 (依然保留，因为生成器需要渲染标题)
        text_layer = Image.new('RGBA', canvas_size, (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        center_x = current_w // 2
        txt_y = int(1200 * scale) # 默认放在下方
        max_w = current_w - int(100 * scale)
        
        off_x = int(offset_x * scale)
        off_y = int(offset_y * scale)

        h_zh = 0
        if title_zh:
            init_zh = int(150 * scale * zh_font_size_ratio)
            font_zh, _, w_zh, h_zh = fit_text_to_width(draw, title_zh, zh_font_path, max_w, init_zh)
            
            draw_x = center_x - w_zh // 2
            final_x = draw_x if return_layers else draw_x + off_x
            final_y = txt_y if return_layers else txt_y + off_y
            
            # 简单的文字描边/阴影，防止背景太亮看不清字
            for ox, oy in [(-2,-2), (2,-2), (-2,2), (2,2)]:
                draw.text((final_x+ox, final_y+oy), title_zh, font=font_zh, fill=(0,0,0,180))
            draw.text((final_x, final_y), title_zh, font=font_zh, fill=(255,255,255,255))
            
        if title_en:
            init_en = int(60 * scale * en_font_size_ratio)
            font_en, _, w_en, h_en = fit_text_to_width(draw, title_en, en_font_path, max_w, init_en)
            
            draw_x = center_x - w_en // 2
            draw_y = txt_y + h_zh + int(10 * scale)
            final_x = draw_x if return_layers else draw_x + off_x
            final_y = draw_y if return_layers else draw_y + off_y
            
            for ox, oy in [(-1,-1), (1,-1), (-1,1), (1,1)]:
                draw.text((final_x+ox, final_y+oy), title_en, font=font_en, fill=(0,0,0,180))
            draw.text((final_x, final_y), title_en, font=font_en, fill=(230,230,230,255))

        if return_layers:
            buff_base = BytesIO()
            canvas.convert("RGB").save(buff_base, format="JPEG", quality=90)
            buff_text = BytesIO()
            text_layer.save(buff_text, format="PNG") 
            return {
                "base": base64.b64encode(buff_base.getvalue()).decode('utf-8'),
                "text": base64.b64encode(buff_text.getvalue()).decode('utf-8')
            }
        else:
            final_img = Image.alpha_composite(canvas, text_layer)
            buffer = BytesIO()
            final_img.convert("RGB").save(buffer, format="JPEG", quality=95)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        log_audit("封面", "处理", f"Single Style Error: {e}", level="ERROR")
        return None
    finally:
        if img is not None:
            try: img.close()
            except: pass