
import base64
import random
import math
from io import BytesIO
from typing import List, Tuple, Union, Any, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageEnhance
from app.logger import logger, log_audit

# Standard Canvas Size
BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_circle_focus(
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
    """
    Standardized entry point for Circle Focus style.
    """
    images = []
    try:
        # Handle font path which might be passed as tuple/list for (zh, en) or single string
        if isinstance(font_path, (list, tuple)):
            zh_font_path = font_path[0]
            en_font_path = font_path[1] if len(font_path) > 1 else font_path[0]
        else:
            zh_font_path = font_path
            en_font_path = font_path

        # Calculate dimensions
        current_w = int(BASE_WIDTH * resolution_scale)
        current_h = int(BASE_HEIGHT * resolution_scale)
        canvas_size = (current_w, current_h)
        scale_factor = resolution_scale
        
        # Design constants (scaled)
        circle_dia = int(800 * scale_factor)
        base_font_size_zh = 120 * scale_factor
        base_font_size_en = 50 * scale_factor
        cy_offset = int(100 * scale_factor)
        line_width = max(1, int(1.5 * scale_factor))
        
        off_x = int(offset_x * scale_factor)
        off_y = int(offset_y * scale_factor)

        if not image_paths:
            return None
            
        for p in image_paths:
            try:
                im = Image.open(p).convert("RGB")
                images.append(im)
            except Exception:
                pass
        
        if not images:
            return None
        
        # === 1. Background Layer ===
        # Use a different image for background if available to increase randomness
        bg_img = images[1] if len(images) > 1 else images[0]
        bg = bg_img.copy()
        bg = ImageOps.fit(bg, canvas_size, method=Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(50 * scale_factor))
        bg = ImageEnhance.Brightness(bg).enhance(0.6)
        canvas = bg.convert("RGBA")

        # Main Circle Image
        main_img = images[0].copy()
        main_img = ImageOps.fit(main_img, (circle_dia, circle_dia), method=Image.LANCZOS)
        
        mask = Image.new('L', (circle_dia, circle_dia), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, circle_dia, circle_dia), fill=255)
        
        main_img = main_img.convert("RGBA")
        main_img.putalpha(mask)
        
        # Shadow
        shadow_size = circle_dia + int(50 * scale_factor)
        shadow = Image.new("RGBA", (shadow_size, shadow_size), (0,0,0,0))
        s_draw = Image.new("RGBA", (circle_dia, circle_dia), (0,0,0,0))
        s_d = ImageDraw.Draw(s_draw)
        s_d.ellipse((0,0,circle_dia,circle_dia), fill=(0,0,0,255))
        shadow.paste(s_draw, (int(25*scale_factor), int(25*scale_factor)), s_draw)
        shadow = shadow.filter(ImageFilter.GaussianBlur(20 * scale_factor))
        
        # Center coordinates
        cx, cy = current_w // 2, current_h // 2
        cy -= cy_offset 
        
        # Paste Background Elements
        canvas.paste(shadow, (cx - shadow.width//2, cy - shadow.height//2), shadow)
        canvas.paste(main_img, (cx - circle_dia//2, cy - circle_dia//2), main_img)
        
        # Decorative Ring
        ring = Image.new("RGBA", canvas_size, (0,0,0,0))
        draw_ring = ImageDraw.Draw(ring)
        ring_dia = circle_dia + int(50 * scale_factor)
        draw_ring.ellipse((cx - ring_dia//2, cy - ring_dia//2, cx + ring_dia//2, cy + ring_dia//2), 
                          outline=(255,255,255, 80), width=line_width)
        canvas = Image.alpha_composite(canvas, ring)

        # === 2. Text Layer ===
        text_layer = Image.new('RGBA', canvas_size, (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        # Base Text Position
        base_txt_y = cy + circle_dia // 2 + int(50 * scale_factor)
        h_zh = 0 # Height placeholder

        # Draw Chinese Title
        if title_zh:
            f_size = int(base_font_size_zh * float(zh_font_size_ratio))
            try:
                font = ImageFont.truetype(str(zh_font_path), f_size)
            except:
                font = ImageFont.load_default()

            # Auto-shrink if too wide
            while True:
                bbox = draw.textbbox((0,0), title_zh, font=font)
                w = bbox[2]-bbox[0]
                if w < current_w - int(50*scale_factor) or f_size < 10: 
                    break
                f_size = int(f_size * 0.9)
                try:
                    font = ImageFont.truetype(str(zh_font_path), f_size)
                except: break
            
            bbox = draw.textbbox((0,0), title_zh, font=font)
            w = bbox[2]-bbox[0]
            h_zh = bbox[3]-bbox[1]
            
            draw_x_zh = cx - w//2
            draw_y_zh = base_txt_y
            
            final_x = draw_x_zh if return_layers else draw_x_zh + off_x
            final_y = draw_y_zh if return_layers else draw_y_zh + off_y
            
            draw.text((final_x, final_y), title_zh, font=font, fill=(255,255,255,255))

        # Draw English Title
        if title_en:
            f_size_en = int(base_font_size_en * float(en_font_size_ratio))
            try:
                font_en = ImageFont.truetype(str(en_font_path), f_size_en)
            except:
                font_en = ImageFont.load_default()

            bbox_en = draw.textbbox((0,0), title_en, font=font_en)
            w_en = bbox_en[2]-bbox_en[0]
            
            gap = int(15 * scale_factor) if title_zh else 0
            draw_x_en = cx - w_en//2
            draw_y_en = base_txt_y + h_zh + gap
            
            final_x = draw_x_en if return_layers else draw_x_en + off_x
            final_y = draw_y_en if return_layers else draw_y_en + off_y
            
            draw.text((final_x, final_y), title_en, font=font_en, fill=(200,200,200,200))

        # === 3. Return Logic ===
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
        log_audit("封面", "处理", f"Style Error: {e}", level="ERROR")
        return None
    finally:
        for im in images:
            try: im.close()
            except: pass
