import base64
from io import BytesIO
from typing import Union, Tuple, List
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from app.logger import log_audit


BASE_WIDTH = 1000
BASE_HEIGHT = 1500

def generate_style_streaming_hero(
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
    imgs = []
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
        
        # 1. 准备图片
        # 至少需要 1 张主图，和 3-4 张小图
        for p in image_paths:
            try: imgs.append(Image.open(p).convert("RGB"))
            except: pass
        if not imgs: return None
        
        # 补齐图片以便下方展示
        while len(imgs) < 4: imgs.extend(imgs)
        
        hero_img = imgs[0]
        thumbs = imgs[1:4] # 取接下来的3张
        
        # 2. 绘制 Hero 背景
        # 占据高度 70%
        hero_h = int(h * 0.75)
        bg = ImageOps.fit(hero_img, (w, hero_h), method=Image.LANCZOS)
        
        # 底部黑色底
        canvas = Image.new("RGB", (w, h), (15, 15, 15))
        canvas.paste(bg, (0, 0))
        
        # 3. 渐变过渡 (Fade to Black)
        gradient = Image.new('L', (w, hero_h), 0)
        dg = ImageDraw.Draw(gradient)
        # 从 50% 高度开始渐变
        start_fade = int(hero_h * 0.4)
        for y in range(start_fade, hero_h):
            alpha = int(255 * ((y - start_fade) / (hero_h - start_fade))**2) # 指数过渡更自然
            dg.line([(0, y), (w, y)], fill=alpha)
            
        black_overlay = Image.new("RGBA", (w, hero_h), (15, 15, 15, 255))
        black_overlay.putalpha(gradient)
        
        canvas = canvas.convert("RGBA")
        canvas.paste(black_overlay, (0, 0), black_overlay)
        
        # 4. 底部缩略图行
        # 放置在底部，留一点边距
        thumb_w = int(280 * scale)
        thumb_h = int(400 * scale)
        gap = int(30 * scale)
        
        # 计算起始 X (居中排列 3 张)
        total_w = 3 * thumb_w + 2 * gap
        start_x = (w - total_w) // 2
        start_y = h - thumb_h - int(80 * scale)
        
        for i, t_img in enumerate(thumbs[:3]):
            t_resized = ImageOps.fit(t_img, (thumb_w, thumb_h), method=Image.LANCZOS)
            canvas.paste(t_resized, (start_x + i*(thumb_w+gap), start_y))
            
        # 5. 文字层 (左侧对齐，或者中间对齐)
        # 这里采用左对齐，模仿网页版头
        text_layer = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(text_layer)
        
        # 文字位置：在缩略图上方
        text_bottom_y = start_y - int(60 * scale)
        left_margin = int(80 * scale) # 左边距
        
        # 中文
        h_z = 0
        if title_zh:
            fs = int(130 * scale * zh_font_size_ratio)
            try: fz = ImageFont.truetype(zh_font_path, fs)
            except: fz = ImageFont.load_default()
            
            bbox = draw.textbbox((0,0), title_zh, font=fz)
            th = bbox[3]-bbox[1]
            
            tx = left_margin + int(offset_x * scale)
            ty = text_bottom_y - th + int(offset_y * scale)
            
            draw.text((tx, ty), title_zh, font=fz, fill=(255,255,255,255))
            
            # 加一个小 LOGO 标记 "COLLECTION"
            tag_fs = int(30 * scale)
            try: ft = ImageFont.truetype(en_font_path, tag_fs)
            except: ft = ImageFont.load_default()
            draw.rectangle((tx, ty - tag_fs - 10, tx + 180*scale, ty - 10), fill=(229, 9, 20, 255)) # Netflix Red
            draw.text((tx + 10*scale, ty - tag_fs - 10), "COLLECTION", font=ft, fill=(255,255,255,255))
            
            last_y = ty + th
        else:
            last_y = text_bottom_y

        # 英文
        if title_en:
            fse = int(50 * scale * en_font_size_ratio)
            try: fe = ImageFont.truetype(en_font_path, fse)
            except: fe = ImageFont.load_default()
            
            txe = left_margin + int(offset_x * scale)
            tye = last_y + int(20*scale) + int(offset_y * scale)
            
            draw.text((txe, tye), title_en, font=fe, fill=(200,200,200,255))

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
        for im in imgs:
            try: im.close()
            except: pass
