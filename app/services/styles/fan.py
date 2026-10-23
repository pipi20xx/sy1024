
import base64
import random
import math
from io import BytesIO
from typing import List, Tuple, Union, Any, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance
from app.logger import log_audit


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

def generate_style_fan(
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
    images = []
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
        for p in image_paths:
            try:
                im = Image.open(p).convert("RGB")
                images.append(im)
            except: pass
        if not images: return None
        
        # 1. Background Layer
        # Use a random image from the pool for background (let's pick the last one)
        bg_src = images[-1]
        bg_base = ImageOps.fit(bg_src, canvas_size, method=Image.LANCZOS)
        bg_base = bg_base.filter(ImageFilter.GaussianBlur(50 * scale))
        bg_base = ImageEnhance.Brightness(bg_base).enhance(0.4) 
        
        canvas = bg_base.convert("RGBA")

        # 2. Fan Layout
        # Use first up to 7 images for the fan cards
        count = min(len(images), 7)
        fan_imgs = images[:count]
        
        pivot_x = current_w // 2
        pivot_y = current_h + int(500 * scale)
        radius = int(1250 * scale)
        
        total_angle = 60 
        start_angle = -total_angle / 2
        step = total_angle / (count - 1) if count > 1 else 0
        
        card_w = int(400 * scale)
        card_h = int(card_w * 1.5)
        border = int(10 * scale)
        
        for i, img in enumerate(fan_imgs):
            angle = start_angle + i * step if count > 1 else 0
            
            img_c = ImageOps.fit(img, (card_w, card_h), method=Image.LANCZOS)
            card = Image.new("RGBA", (card_w + border*2, card_h + border*2), (255,255,255,255))
            card.paste(img_c, (border, border))
            
            rot_card = card.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
            
            rad = math.radians(angle)
            x = pivot_x + radius * math.sin(rad)
            y = pivot_y - radius * math.cos(rad)
            
            paste_x = int(x - rot_card.width // 2)
            paste_y = int(y - rot_card.height // 2)
            
            # Simple shadow
            shadow_mask = rot_card.split()[3]
            canvas_shadow = Image.new("RGBA", canvas_size, (0,0,0,0))
            shadow_color = Image.new("RGBA", rot_card.size, (0,0,0,120))
            canvas_shadow.paste(shadow_color, (paste_x + int(10*scale), paste_y + int(10*scale)), shadow_mask)
            canvas_shadow = canvas_shadow.filter(ImageFilter.GaussianBlur(10 * scale))
            
            canvas.paste(canvas_shadow, (0,0), canvas_shadow)
            canvas.paste(rot_card, (paste_x, paste_y), rot_card)

        # 3. Text Layer
        text_layer = Image.new('RGBA', canvas_size, (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        center_x = current_w // 2
        txt_y = int(150 * scale)
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
            
            # Glow effect for text
            for ox, oy in [(-1,-1), (1,-1), (-1,1), (1,1)]:
                draw.text((final_x+ox, final_y+oy), title_zh, font=font_zh, fill=(0,0,0,150))
            draw.text((final_x, final_y), title_zh, font=font_zh, fill=(255,255,255,255))
            
        if title_en:
            init_en = int(60 * scale * en_font_size_ratio)
            font_en, _, w_en, h_en = fit_text_to_width(draw, title_en, en_font_path, max_w, init_en)
            
            draw_x = center_x - w_en // 2
            draw_y = txt_y + h_zh + int(15 * scale)
            final_x = draw_x if return_layers else draw_x + off_x
            final_y = draw_y if return_layers else draw_y + off_y
            
            draw.text((final_x, final_y), title_en, font=font_en, fill=(200,200,200,255))

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
        log_audit("封面", "处理", f"Fan Style Error: {e}", level="ERROR")
        return None
    finally:
        for im in images:
            try: im.close()
            except: pass
