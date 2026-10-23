import base64
import random
from io import BytesIO
from typing import Union, Tuple, List
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from app.logger import log_audit


BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_ink_brush(
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
        try: img = Image.open(image_paths[0]).convert("RGB")
        except: return None
        
        # 1. 背景：宣纸色
        paper_color = (245, 242, 230)
        canvas = Image.new("RGBA", (w, h), (*paper_color, 255))
        
        # 2. 生成水墨蒙版 (Procedural Ink Blob)
        # 通过叠加多个随机大小的圆形来模拟不规则墨迹
        mask = Image.new("L", (w, h), 0)
        draw_m = ImageDraw.Draw(mask)
        
        cx, cy = w // 2, int(h * 0.45)
        
        # 主墨团
        blobs = 15
        for _ in range(blobs):
            r = random.randint(int(100*scale), int(350*scale))
            bx = cx + random.randint(int(-100*scale), int(100*scale))
            by = cy + random.randint(int(-150*scale), int(150*scale))
            draw_m.ellipse((bx-r, by-r, bx+r, by+r), fill=255)
            
        # 边缘模糊，模拟宣纸晕染
        mask = mask.filter(ImageFilter.GaussianBlur(15 * scale))
        
        # 3. 填充图片
        # 稍微调低饱和度，更有质感
        img_content = ImageOps.fit(img, (w, h), method=Image.LANCZOS)
        img_content.putalpha(mask)
        
        canvas.paste(img_content, (0, 0), img_content)
        
        # 4. 文字层 (竖排)
        text_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        # 竖排文字逻辑
        # 位于右侧或左侧，看空间。默认放右侧。
        start_x = w - int(150 * scale) + int(offset_x * scale)
        start_y = int(100 * scale) + int(offset_y * scale)
        
        # 中文 (黑色)
        if title_zh:
            fs = int(100 * scale * zh_font_size_ratio)
            try: fz = ImageFont.truetype(zh_font_path, fs)
            except: fz = ImageFont.load_default()
            
            curr_y = start_y
            for char in title_zh:
                # 标点符号旋转？这里简单处理
                bbox = draw.textbbox((0,0), char, font=fz)
                cw = bbox[2]-bbox[0]
                ch = bbox[3]-bbox[1]
                
                # 居中对齐这一列
                char_x = start_x - cw // 2
                draw.text((char_x, curr_y), char, font=fz, fill=(20, 20, 20, 255))
                curr_y += ch + int(10 * scale)
                
            # 红色印章 (Seal)
            seal_size = int(80 * scale)
            seal_y = curr_y + int(30 * scale)
            seal_x = start_x - seal_size // 2
            
            draw.rectangle((seal_x, seal_y, seal_x+seal_size, seal_y+seal_size), fill=(180, 20, 20, 200))
            # 印章里的字 "珍藏"
            try: f_seal = ImageFont.truetype(zh_font_path, int(30*scale))
            except: f_seal = ImageFont.load_default()
            draw.text((seal_x+10*scale, seal_y+10*scale), "珍\n藏", font=f_seal, fill=(255,255,255,200), spacing=4)

        # 英文 (横排，放在底部居中)
        if title_en:
            fse = int(40 * scale * en_font_size_ratio)
            try: fe = ImageFont.truetype(en_font_path, fse)
            except: fe = ImageFont.load_default()
            
            bbox_e = draw.textbbox((0,0), title_en, font=fe)
            twe = bbox_e[2]-bbox_e[0]
            
            txe = w // 2 - twe // 2
            tye = h - int(80 * scale)
            
            draw.text((txe, tye), title_en.upper(), font=fe, fill=(100, 100, 100, 255))

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
