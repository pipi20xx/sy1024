import base64
import random
from io import BytesIO
from typing import Union, Tuple, List
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from app.logger import log_audit


BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_torn_paper(
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
        
        # 1. 准备上下两部分
        # 上半部分：图片
        top_img = ImageOps.fit(img, (w, h), method=Image.LANCZOS)
        
        # 下半部分：深色纸纹 (这里用深灰杂色模拟)
        bottom_bg = Image.new("RGB", (w, h), (20, 20, 20))
        noise = Image.effect_noise((w, h), 10).convert("RGB")
        bottom_bg = Image.blend(bottom_bg, noise, 0.05)
        
        # 2. 生成撕裂边缘 (ZigZag Polygon)
        # 撕裂线位置：大概在 60% 高度
        split_y = int(h * 0.65)
        
        # 生成锯齿点
        points = []
        points.append((0, h)) # 左下
        points.append((0, split_y)) # 左上起点
        
        # 横向每隔 10-30px 生成一个点，Y轴随机波动
        curr_x = 0
        while curr_x < w:
            step = random.randint(int(10*scale), int(30*scale))
            curr_x += step
            if curr_x > w: curr_x = w
            
            # Y 轴波动范围 +/- 15px
            y_vary = random.randint(int(-15*scale), int(15*scale))
            points.append((curr_x, split_y + y_vary))
            
        points.append((w, h)) # 右下
        
        # 创建蒙版：白色为保留区域 (下半部分)
        mask = Image.new("L", (w, h), 0)
        draw_m = ImageDraw.Draw(mask)
        draw_m.polygon(points, fill=255)
        
        # 3. 合成
        # 底层是图片，上层是深色纸，通过蒙版盖上去
        canvas = top_img.convert("RGBA")
        paper_layer = bottom_bg.convert("RGBA")
        
        # 投影层
        shadow = Image.new("RGBA", (w, h), (0,0,0,0))
        draw_s = ImageDraw.Draw(shadow)
        draw_s.polygon(points, fill=(0,0,0,180)) # 黑色投影
        shadow = shadow.filter(ImageFilter.GaussianBlur(10 * scale))
        
        canvas.alpha_composite(shadow)
        
        # 纸层 (带蒙版)
        paper_layer.putalpha(mask)
        canvas.alpha_composite(paper_layer)
        
        # 4. 文字层 (在下半部分深色纸上)
        text_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        cx = w // 2
        # 文字中心
        text_cy = split_y + (h - split_y) // 2
        
        # 中文
        h_z = 0
        if title_zh:
            fs = int(120 * scale * zh_font_size_ratio)
            try: fz = ImageFont.truetype(zh_font_path, fs)
            except: fz = ImageFont.load_default()
            
            bbox = draw.textbbox((0,0), title_zh, font=fz)
            tw = bbox[2]-bbox[0]
            h_z = bbox[3]-bbox[1]
            
            tx = cx - tw // 2 + int(offset_x * scale)
            ty = text_cy - h_z // 2 - int(20*scale) + int(offset_y * scale)
            
            draw.text((tx, ty), title_zh, font=fz, fill=(230,230,230,255))
            last_y = ty + h_z
        else:
            last_y = text_cy

        # 英文
        if title_en:
            fse = int(50 * scale * en_font_size_ratio)
            try: fe = ImageFont.truetype(en_font_path, fse)
            except: fe = ImageFont.load_default()
            
            bbox_e = draw.textbbox((0,0), title_en, font=fe)
            twe = bbox_e[2]-bbox_e[0]
            
            txe = cx - twe // 2 + int(offset_x * scale)
            tye = last_y + int(20*scale) + int(offset_y * scale)
            
            draw.text((txe, tye), title_en.upper(), font=fe, fill=(150,150,150,255))

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