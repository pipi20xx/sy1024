import base64
import math
from io import BytesIO
from typing import Union, Tuple, List
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from app.logger import log_audit


BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_3d_float(
    image_paths: list,
    title_zh: str,
    title_en: str,
    font_path: Union[str, Tuple[str, str], List[str]],
    zh_font_size_ratio: float = 1.0,
    en_font_size_ratio: float = 1.0,
    offset_x: int = 0,
    offset_y: int = 0,
    resolution_scale: float = 1.0,
    return_layers: bool = False,
    seed: int = None,
    **kwargs
):
    img = None
    try:
        # Standardize font path handling
        if isinstance(font_path, (list, tuple)):
            zh_font_path = font_path[0]
            en_font_path = font_path[1] if len(font_path) > 1 else font_path[0]
        else:
            zh_font_path = font_path
            en_font_path = font_path

        w = int(BASE_WIDTH * resolution_scale)
        h = int(BASE_HEIGHT * resolution_scale)
        scale = resolution_scale
        
        if not image_paths: return None
        try: img = Image.open(image_paths[0]).convert("RGBA")
        except: return None
        
        # 1. 背景：模糊处理
        bg = ImageOps.fit(img, (w, h), method=Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(60 * scale))
        # 压暗
        overlay = Image.new("RGBA", (w, h), (0,0,0,100))
        bg.alpha_composite(overlay)
        canvas = bg
        
        # 2. 制作 3D 卡片
        # 使用 "旋转 + 阴影" 来模拟悬浮感
        
        # 缩小图片作为卡片
        card_w = int(w * 0.7)
        card_h = int(h * 0.7)
        card = ImageOps.fit(img, (card_w, card_h), method=Image.LANCZOS)
        
        # 加白边
        border_w = int(10 * scale)
        card_bordered = ImageOps.expand(card, border=border_w, fill=(255,255,255))
        
        # 旋转 (逆时针旋转一点，产生动感)
        angle = 8
        # expand=True 会扩大画布
        card_rot = card_bordered.rotate(angle, resample=Image.BICUBIC, expand=True)
        
        # 3. 制作投影
        # 投影应该是旋转后的形状，黑色，模糊，稍微错位
        shadow = Image.new("RGBA", card_rot.size, (0,0,0,0))
        # 提取旋转后非透明区域作为阴影
        shadow.paste((0,0,0,180), (0,0), card_rot) 
        shadow = shadow.filter(ImageFilter.GaussianBlur(20 * scale))
        
        # 4. 合成
        cx, cy = w // 2, h // 2
        
        # 投影位置 (向下向右偏移)
        shadow_x = cx - shadow.width // 2 + int(30 * scale)
        shadow_y = cy - shadow.height // 2 + int(50 * scale)
        
        # 卡片位置 (居中)
        card_x = cx - card_rot.width // 2
        card_y = cy - card_rot.height // 2
        
        # 先贴投影，再贴卡片
        canvas.paste(shadow, (shadow_x, shadow_y), shadow)
        canvas.paste(card_rot, (card_x, card_y), card_rot)
        
        # 5. 文字层
        text_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        # 文字放在底部，不旋转，保持可读性
        text_base_y = h - int(150 * scale)
        
        # 中文
        h_z = 0
        if title_zh:
            fs = int(130 * scale * zh_font_size_ratio)
            try: fz = ImageFont.truetype(zh_font_path, fs)
            except: fz = ImageFont.load_default()
            
            bbox = draw.textbbox((0,0), title_zh, font=fz)
            tw = bbox[2]-bbox[0]
            h_z = bbox[3]-bbox[1]
            
            tx = cx - tw // 2 + int(offset_x * scale)
            ty = text_base_y - h_z + int(offset_y * scale)
            
            # 立体文字效果 (多层堆叠)
            for i in range(4, 0, -1):
                draw.text((tx+i, ty+i), title_zh, font=fz, fill=(0,0,0,100))
            draw.text((tx, ty), title_zh, font=fz, fill=(255,255,255,255))
            
            last_y = ty + h_z
        else:
            last_y = text_base_y

        # 英文
        if title_en:
            fse = int(50 * scale * en_font_size_ratio)
            try: fe = ImageFont.truetype(en_font_path, fse)
            except: fe = ImageFont.load_default()
            
            bbox_e = draw.textbbox((0,0), title_en, font=fe)
            twe = bbox_e[2]-bbox_e[0]
            
            txe = cx - twe // 2 + int(offset_x * scale)
            tye = last_y + int(20*scale) + int(offset_y * scale)
            
            draw.text((txe, tye), title_en, font=fe, fill=(200,200,200,200))

        if return_layers:
            b_io = BytesIO(); canvas.convert("RGB").save(b_io, "JPEG", quality=90)
            t_io = BytesIO(); text_layer.save(t_io, "PNG")
            return {"base": base64.b64encode(b_io.getvalue()).decode(), "text": base64.b64encode(t_io.getvalue()).decode()}
        else:
            final = Image.alpha_composite(canvas, text_layer)
            out = BytesIO(); final.convert("RGB").save(out, "JPEG", quality=95)
            return base64.b64encode(out.getvalue()).decode()

    except Exception as e:
        log_audit("封面", "处理", f"Style Error: {e}", level="ERROR")
        return None
    finally:
        if img is not None:
            try: img.close()
            except: pass