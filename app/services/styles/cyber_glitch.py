import base64
import random
from io import BytesIO
from typing import Union, Tuple, List
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageChops
from app.logger import log_audit


BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_cyber_glitch(
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
        
        # 1. 预处理：铺满背景并变暗
        img_content = ImageOps.fit(img, (w, h), method=Image.LANCZOS)
        
        # 2. RGB 分离 (Chromatic Aberration)
        r, g, b = img_content.split()
        
        # 随机位移量
        shift = int(10 * scale)
        
        # 偏移 R 和 B 通道
        r_offset = ImageChops.offset(r, shift, 0)
        b_offset = ImageChops.offset(b, -shift, 0)
        
        # 合并回 RGB
        img_glitch = Image.merge("RGB", (r_offset, g, b_offset))
        
        # 3. 添加扫描线切片 (Scanline Slicing)
        # 随机选取几行进行水平错位
        canvas = img_glitch.convert("RGBA")
        
        num_slices = 10
        for _ in range(num_slices):
            slice_h = random.randint(int(5*scale), int(30*scale))
            slice_y = random.randint(0, h - slice_h)
            offset_x_slice = random.randint(int(-30*scale), int(30*scale))
            
            # 裁剪切片
            box = (0, slice_y, w, slice_y + slice_h)
            region = canvas.crop(box)
            
            # 粘贴回错位位置
            canvas.paste(region, (offset_x_slice, slice_y))
            
        # 4. 扫描线纹理 (Scanlines)
        scanlines = Image.new("RGBA", (w, h), (0,0,0,0))
        d_scan = ImageDraw.Draw(scanlines)
        for y in range(0, h, int(4*scale)):
            d_scan.line([(0, y), (w, y)], fill=(0, 0, 0, 50), width=1)
            
        canvas = Image.alpha_composite(canvas, scanlines)
        
        # 5. 文字层 (Cyberpunk 风格)
        text_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        # 布局：文字在中间，带有发光
        center_x = w // 2 + int(offset_x * scale)
        center_y = h // 2 + int(offset_y * scale)
        
        # 霓虹青色
        neon_cyan = (0, 255, 255)
        
        if title_en:
            fse = int(100 * scale * en_font_size_ratio)
            try: fe = ImageFont.truetype(en_font_path, fse)
            except: fe = ImageFont.load_default()
            
            # 绘制多次产生模糊发光
            text_str = title_en.upper()
            
            # 阴影
            draw.text((center_x+5*scale, center_y+5*scale), text_str, font=fe, fill=(255, 0, 255, 200), anchor="mm")
            # 主体
            draw.text((center_x, center_y), text_str, font=fe, fill=(255, 255, 255, 255), anchor="mm")
            # 描边
            draw.text((center_x, center_y), text_str, font=fe, fill=None, stroke_width=2, stroke_fill=neon_cyan, anchor="mm")

        if title_zh:
            fs = int(50 * scale * zh_font_size_ratio)
            try: fz = ImageFont.truetype(zh_font_path, fs)
            except: fz = ImageFont.load_default()
            
            sub_y = center_y + int(80 * scale)
            # 背景条
            text_w = draw.textlength(title_zh, font=fz)
            draw.rectangle(
                (center_x - text_w//2 - 10, sub_y - fs//2, center_x + text_w//2 + 10, sub_y + fs//2 + 10),
                fill=(0, 0, 0, 180)
            )
            draw.text((center_x, sub_y), title_zh, font=fz, fill=neon_cyan, anchor="mm")

        if return_layers:
            b_io = BytesIO(); canvas.convert("RGB").save(b_io, "JPEG", quality=90)
            t_io = BytesIO(); text_layer.save(t_io, "PNG")
            return {"base": base64.b64encode(b_io.getvalue()).decode(), "text": base64.b64encode(t_io.getvalue()).decode()}
        else:
            final = Image.alpha_composite(canvas, text_layer)
            out = BytesIO(); final.convert("RGB").save(out, "JPEG", quality=95)
            return base64.b64encode(out.getvalue()).decode()

    except Exception as e:
        log_audit("封面", "处理", f"Cyber Glitch Style Error: {e}", level="ERROR")
        return None
    finally:
        if img is not None:
            try: img.close()
            except: pass