import base64
import random
import colorsys
import os
import shutil
import math
import uuid
import asyncio
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, Union, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.logger import logger, log_audit
from app import globals

# ========== Configuration ========== 
CANVAS_SIZE = (1920, 1080)

# Multi-style config
POSTER_GEN_CONFIG = {
    "ROWS": 3,
    "COLS": 3,
    "MARGIN": 22,
    "CORNER_RADIUS": 46.1,
    "ROTATION_ANGLE": -15.8,
    "START_X": 835,
    "START_Y": -362,
    "COLUMN_SPACING": 100,
    "SAVE_COLUMNS": False,
    "CELL_WIDTH": 410,
    "CELL_HEIGHT": 610,
    "CANVAS_WIDTH": 1920,
    "CANVAS_HEIGHT": 1080,
}

class CoverGeneratorService:
    def __init__(self):
        self.fonts_dir = Path("app/static/fonts")
        self.temp_dir = Path("app/static/temp_covers")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_font_path(self, font_name: str) -> str:
        if not font_name: return None
        if os.path.exists(font_name): return font_name
        font_path = self.fonts_dir / font_name
        if font_path.exists(): return str(font_path)
        for file in self.fonts_dir.iterdir():
            if file.name.lower() == font_name.lower(): return str(file)
        log_audit("封面", "处理", f"未找到字体: {font_name}", level="WARN")
        return str(font_path)

    def get_available_fonts(self) -> List[str]:
        if not self.fonts_dir.exists(): return []
        extensions = {'.ttf', '.otf', '.woff', '.woff2'}
        return [f.name for f in self.fonts_dir.iterdir() if f.suffix.lower() in extensions]

    # ================= Helper Functions =================
    
    def _is_not_black_white_gray_near(self, color, threshold=20):
        r, g, b = color
        if (r < threshold and g < threshold and b < threshold) or \
           (r > 255 - threshold and g > 255 - threshold and b > 255 - threshold): return False
        gray_diff_threshold = 10
        if abs(r - g) < gray_diff_threshold and abs(g - b) < gray_diff_threshold and abs(r - b) < gray_diff_threshold: return False
        return True

    def _rgb_to_hsv(self, color):
        r, g, b = [x / 255.0 for x in color]
        return colorsys.rgb_to_hsv(r, g, b)

    def _hsv_to_rgb(self, h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return (int(r * 255), int(g * 255), int(b * 255))

    def _adjust_color_macaron(self, color):
        h, s, v = self._rgb_to_hsv(color)
        target_saturation_range = (0.3, 0.7)
        target_value_range = (0.6, 0.85)
        if s < target_saturation_range[0]: s = target_saturation_range[0]
        elif s > target_saturation_range[1]: s = target_saturation_range[1]
        if v < target_value_range[0]: v = target_value_range[0]
        elif v > target_value_range[1]: v = target_value_range[1]
        return self._hsv_to_rgb(h, s, v)
        
    def _adjust_to_macaron_hsv(self, h, s, v, target_saturation_range=(0.2, 0.7), target_value_range=(0.55, 0.85)):
        adjusted_s = min(max(s, target_saturation_range[0]), target_saturation_range[1])
        adjusted_v = min(max(v, target_value_range[0]), target_value_range[1])
        return adjusted_s, adjusted_v

    def _color_distance(self, color1, color2):
        h1, s1, v1 = self._rgb_to_hsv(color1)
        h2, s2, v2 = self._rgb_to_hsv(color2)
        h_dist = min(abs(h1 - h2), 1 - abs(h1 - h2))
        return h_dist * 5 + abs(s1 - s2) + abs(v1 - v2)

    def _find_dominant_macaron_colors(self, image, num_colors=5):
        img = image.copy()
        img.thumbnail((150, 150))
        img = img.convert('RGB')
        pixels = list(img.getdata())
        filtered_pixels = [p for p in pixels if self._is_not_black_white_gray_near(p)]
        if not filtered_pixels: return []
        color_counter = Counter(filtered_pixels)
        candidate_colors = color_counter.most_common(num_colors * 5)
        macaron_colors = []
        min_color_distance = 0.15
        for color, _ in candidate_colors:
            adjusted_color = self._adjust_color_macaron(color)
            if not any(self._color_distance(adjusted_color, existing) < min_color_distance for existing in macaron_colors):
                macaron_colors.append(adjusted_color)
                if len(macaron_colors) >= num_colors: break
        return macaron_colors
        
    def _find_dominant_vibrant_colors(self, image, num_colors=5):
        img = image.copy()  
        img.thumbnail((100, 100))
        img = img.convert('RGB')
        pixels = list(img.getdata())
        filtered_pixels = [p for p in pixels if self._is_not_black_white_gray_near(p)]
        if not filtered_pixels: return []
        color_counter = Counter(filtered_pixels)
        dominant_colors = color_counter.most_common(num_colors * 3)
        macaron_colors = []
        seen_hues = set()
        for color, count in dominant_colors:
            h, s, v = self._rgb_to_hsv(color)
            adjusted_s, adjusted_v = self._adjust_to_macaron_hsv(h, s, v)
            adjusted_rgb = self._hsv_to_rgb(h, adjusted_s, adjusted_v)
            hue_degree = int(h * 360)
            is_similar_hue = any(abs(hue_degree - seen) < 15 for seen in seen_hues)
            if not is_similar_hue and adjusted_rgb not in macaron_colors:
                macaron_colors.append(adjusted_rgb)
                seen_hues.add(hue_degree)
                if len(macaron_colors) >= num_colors: break
        return macaron_colors

    def _darken_color(self, color, factor=0.7):
        r, g, b = color
        return (int(r * factor), int(g * factor), int(b * factor))

    def _add_film_grain(self, image, intensity=0.05):
        img_array = np.array(image, dtype=np.float32)
        if image.mode == 'RGBA':
            noise = np.random.normal(0, intensity * 255, (img_array.shape[0], img_array.shape[1]))
            for i in range(3): img_array[:, :, i] = img_array[:, :, i] + noise
        else:
            noise = np.random.normal(0, intensity * 255, img_array.shape)
            img_array = img_array + noise
        img_array = np.clip(img_array, 0, 255).astype(np.uint8)
        return Image.fromarray(img_array, mode=image.mode)

    def _crop_to_square(self, img):
        width, height = img.size
        size = min(width, height)
        left = (width - size) // 2
        top = (height - size) // 2
        right = left + size
        bottom = top + size
        return img.crop((left, top, right, bottom))

    def _add_rounded_corners(self, img, radius=30):
        factor = 2
        width, height = img.size
        enlarged_img = img.resize((width * factor, height * factor), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new('L', (width * factor, height * factor), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([(0, 0), (width * factor, height * factor)], radius=radius * factor, fill=255)
        background = Image.new("RGBA", (width * factor, height * factor), (255, 255, 255, 0))
        high_res_result = Image.composite(enlarged_img, background, mask)
        return high_res_result.resize((width, height), Image.Resampling.LANCZOS)

    def _rotate_image(self, img, angle, bg_color=(0, 0, 0, 0)):
        return img.rotate(angle, Image.BICUBIC, expand=True, fillcolor=bg_color)

    def _add_shadow_and_rotate(self, canvas, img, angle, offset=(10, 10), radius=10, opacity=0.5, center_pos=None):
        width, height = img.size
        if center_pos is None: center_pos = (canvas.width // 2, canvas.height // 2)
        padding = max(radius * 4, 100)
        shadow_size = (width + padding * 2, height + padding * 2)
        shadow = Image.new("RGBA", shadow_size, (0, 0, 0, 0))
        shadow_mask = Image.new("L", (width, height), 255)
        if img.mode == "RGBA": shadow_mask = img.split()[3]
        shadow_center = (padding, padding)
        shadow.paste((0, 0, 0, int(255 * opacity)), 
                    (shadow_center[0], shadow_center[1], shadow_center[0] + width, shadow_center[1] + height), shadow_mask)
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius))
        rotated_shadow = self._rotate_image(shadow, angle)
        shadow_width, shadow_height = rotated_shadow.size
        shadow_x = center_pos[0] - shadow_width // 2 + offset[0]
        shadow_y = center_pos[1] - shadow_height // 2 + offset[1]
        canvas.paste(rotated_shadow, (shadow_x, shadow_y), rotated_shadow)
        rotated_img = self._rotate_image(img, angle)
        img_width, img_height = rotated_img.size
        img_x = center_pos[0] - img_width // 2
        img_y = center_pos[1] - img_height // 2
        canvas.paste(rotated_img, (img_x, img_y), rotated_img)
        return canvas

    def _image_to_base64(self, image, format="auto", quality=85):
        buffer = BytesIO()
        if format.lower() == "auto":
            format = "PNG" if image.mode == "RGBA" or (image.info.get('transparency') is not None) else "JPEG"
        if format.lower() == "png": image.save(buffer, format="PNG", optimize=True)
        elif format.lower() == "jpeg":
             if image.mode == 'RGBA': image = image.convert('RGB')
             image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        else: image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _add_shadow_simple(self, img, offset=(5, 5), shadow_color=(0, 0, 0, 100), blur_radius=3):
        shadow_width = img.width + offset[0] + blur_radius * 2
        shadow_height = img.height + offset[1] + blur_radius * 2
        shadow = Image.new("RGBA", (shadow_width, shadow_height), (0, 0, 0, 0))
        shadow_layer = Image.new("RGBA", img.size, shadow_color)
        shadow.paste(shadow_layer, (blur_radius + offset[0], blur_radius + offset[1]))
        shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))
        result = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
        result.paste(img, (blur_radius, blur_radius), img if img.mode == "RGBA" else None)
        return Image.alpha_composite(shadow, result)

    def _create_extended_column(self, column_posters, cell_width, cell_height, margin, corner_radius):
        rows = len(column_posters)
        single_column_height = rows * cell_height + (rows - 1) * margin
        
        shadow_extra_width = 20 + 20 * 2
        shadow_extra_height = 20 + 20 * 2
        
        extended_height = single_column_height * 2 + margin
        column_image = Image.new("RGBA", (cell_width + shadow_extra_width, extended_height + shadow_extra_height), (0, 0, 0, 0))
        
        for copy_index in range(2):
            base_y = copy_index * (single_column_height + margin)
            for row_index, poster_path in enumerate(column_posters):
                poster = None
                try:
                    poster = Image.open(poster_path)
                    resized_poster = ImageOps.fit(poster, (cell_width, cell_height), Image.LANCZOS)
                    if corner_radius > 0:
                        resized_poster = self._add_rounded_corners(resized_poster, corner_radius).convert("RGBA")
                    
                    resized_poster_with_shadow = self._add_shadow_simple(resized_poster, (20, 20), (0, 0, 0, 255), 20)
                    y_position = base_y + row_index * (cell_height + margin)
                    column_image.paste(resized_poster_with_shadow, (0, y_position), resized_poster_with_shadow)
                except Exception as e:
                    log_audit("封面", "失败", f"处理图片 {poster_path} 时出错: {e}", level="ERROR")
                    continue
                finally:
                    if poster is not None:
                        poster.close()
        return column_image, single_column_height

    def _generate_animation_frame(self, gradient_bg, extended_columns, column_heights, frame_index, total_frames, cfg, scale_factor=1.0):
        result = gradient_bg.copy()
        margin = int(cfg["MARGIN"] * scale_factor)
        cell_width = int(cfg["CELL_WIDTH"] * scale_factor)
        rotation_angle = cfg["ROTATION_ANGLE"]
        
        move_distance = column_heights[0] + margin
        progress = frame_index / total_frames
        base_offset = int(progress * move_distance)
        
        for col_index, (extended_column, single_height) in enumerate(zip(extended_columns, column_heights)):
            if col_index >= cfg["COLS"]: break
            
            offset = base_offset if col_index == 1 else -base_offset
            shadow_extra = 20 + 20 * 2
            
            crop_y_start = (single_height // 2 + offset) % (single_height + margin)
            cropped_column = extended_column.crop((0, crop_y_start, extended_column.width, crop_y_start + single_height + shadow_extra))
            
            diag = int(math.sqrt(cropped_column.width**2 + cropped_column.height**2) * 1.5)
            rot_canvas = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
            rot_canvas.paste(cropped_column, ((diag - cropped_column.width)//2, (diag - cropped_column.height)//2), cropped_column)
            rotated_column = rot_canvas.rotate(rotation_angle, Image.BICUBIC, expand=True)
            
            col_x = int(cfg["START_X"] * scale_factor) + col_index * int(cfg["COLUMN_SPACING"] * scale_factor)
            col_center_y = int(cfg["START_Y"] * scale_factor) + single_height // 2
            col_center_x = col_x
            
            if col_index == 1: col_center_x += int(380 * scale_factor)
            elif col_index == 2: col_center_y -= int(155 * scale_factor); col_center_x += int(760 * scale_factor)
            
            fx = col_center_x - rotated_column.width // 2 + cell_width // 2
            fy = col_center_y - rotated_column.height // 2
            result.paste(rotated_column, (int(fx), int(fy)), rotated_column)
            
        return result

    def _draw_text(self, image, text, position, font_path, font_size, fill_color=(255, 255, 255, 255), shadow=False, shadow_color=None, shadow_offset=10, shadow_alpha=75):
        if not text: return image
        img_copy = image.convert("RGBA")
        text_layer = Image.new('RGBA', img_copy.size, (255, 255, 255, 0))
        shadow_layer = Image.new('RGBA', img_copy.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(text_layer)
        shadow_draw = ImageDraw.Draw(shadow_layer)
        font = ImageFont.truetype(font_path, font_size)
        
        if shadow:
            if shadow_color is None: shadow_color = (50, 50, 50, shadow_alpha)
            else: shadow_color = shadow_color[:3] + (shadow_alpha,)
            for offset in range(3, shadow_offset + 1, 2):
                shadow_draw.text((position[0] + offset, position[1] + offset), text, font=font, fill=shadow_color)
        
        draw.text(position, text, font=font, fill=fill_color)
        blurred_shadow = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_offset))
        combined = Image.alpha_composite(img_copy, blurred_shadow)
        return Image.alpha_composite(combined, text_layer)

    def _draw_multiline_text(self, image, text, position, font_path, font_size, line_spacing=10, fill_color=(255, 255, 255, 255), shadow=False, shadow_color=None, shadow_offset=4, shadow_alpha=100):
        if not text: return image, 0
        img_copy = image.convert("RGBA")
        text_layer = Image.new('RGBA', img_copy.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(text_layer)
        font = ImageFont.truetype(font_path, font_size)
        lines = text.split(" ")
        
        if shadow:
             if shadow_color is None: shadow_color = (50, 50, 50, shadow_alpha)
             else: shadow_color = shadow_color[:3] + (shadow_alpha,)

        x, y = position
        for i, line in enumerate(lines):
            current_y = y + i * (font_size + line_spacing)
            if shadow:
                for offset in range(3, shadow_offset + 1, 2):
                    draw.text((x + offset, current_y + offset), line, font=font, fill=shadow_color)
            draw.text((x, current_y), line, font=font, fill=fill_color)
            
        return Image.alpha_composite(img_copy, text_layer), len(lines)

    def _create_gradient_background(self, width, height, color):
        if not color: color = (random.randint(50,200), random.randint(50,200), random.randint(50,200), 255)
        elif len(color) == 3: color = color + (255,)
        
        r, g, b = max(0, int(color[0]*0.65)), max(0, int(color[1]*0.65)), max(0, int(color[2]*0.65))
        left_color = (r, g, b, color[3])
        
        r2, g2, b2 = min(255, max(r+80, min(230, int(color[0]*1.9)))), min(255, max(g+80, min(230, int(color[1]*1.9)))), min(255, max(b+80, min(230, int(color[2]*1.9))))
        right_color = (r2, g2, b2, color[3])

        left_img = Image.new("RGBA", (width, height), left_color)
        right_img = Image.new("RGBA", (width, height), right_color)
        
        mask = Image.new("L", (width, height), 0)
        mask_data = [int(255.0 * (x / width) ** 0.7) for y in range(height) for x in range(width)]
        mask.putdata(mask_data)
        
        return Image.composite(right_img, left_img, mask)

    def _get_poster_primary_color(self, img_path):
        try:
            img = Image.open(img_path).resize((100, 150), Image.LANCZOS).convert('RGBA')
            pixels = [p for p in list(img.getdata()) if p[3] > 200 and 30 < (p[0]+p[1]+p[2])/3 < 220]
            if not pixels: return (150, 100, 50, 255)
            return Counter(pixels).most_common(1)[0][0]
        except: return (150, 100, 50, 255)

    def _create_blur_background(self, image_path, width, height, color, blur_size, color_ratio):
        original_img = Image.open(image_path).convert('RGBA')
        bg_img = ImageOps.fit(original_img, (width, height), method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        
        actual_color = self._darken_color(color, 0.85)
        bg_color_array = np.array([[actual_color[:3]]], dtype=float)
        bg_img_array = np.array(bg_img, dtype=float)[:,:,:3] # process RGB
        
        blended_bg = bg_img_array * (1 - float(color_ratio)) + bg_color_array * float(color_ratio)
        blended_bg = np.clip(blended_bg, 0, 255).astype(np.uint8)
        
        blended_bg_img = Image.fromarray(blended_bg, 'RGB').convert('RGBA')
        
        # Lighten gradient
        gradient_mask = Image.new("L", (width, height), 0)
        draw_mask = ImageDraw.Draw(gradient_mask)
        for x in range(width):
            alpha = int((x / width) * 255 * 0.6)
            draw_mask.line([(x, 0), (x, height)], fill=alpha)
        
        lighten_layer = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        lighten_layer.putalpha(gradient_mask)
        
        return self._add_film_grain(Image.alpha_composite(blended_bg_img, lighten_layer), 0.03)

    # ================= Style Generators =================

    def generate_style_single_1(self, image_paths: List[str], title_zh: str, title_en: str, 
                                font_zh_name: str, font_en_name: str, 
                                zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False) -> str:
        # Requires 1 image
        if not image_paths: raise ValueError("Single Style 1 requires at least 1 image")
        image_path = image_paths[0]
        
        zh_font_path = self.get_font_path(font_zh_name)
        en_font_path = self.get_font_path(font_en_name) or zh_font_path
        
        num_colors = 6
        original_img = Image.open(image_path).convert("RGB")
        candidate_colors = self._find_dominant_macaron_colors(original_img, num_colors=num_colors)
        random.shuffle(candidate_colors)
        extracted_colors = candidate_colors[:num_colors]
        
        soft_macaron_colors = [(237, 159, 77), (186, 225, 255), (255, 223, 186), (202, 231, 200)]
        while len(extracted_colors) < num_colors:
            extracted_colors.append(random.choice(soft_macaron_colors))
            
        bg_color = self._darken_color(extracted_colors[0], 0.85)
        card_colors = [extracted_colors[1], extracted_colors[2]]
        
        bg_img = ImageOps.fit(original_img.copy(), CANVAS_SIZE, method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=int(blur_size)))
        
        bg_img_arr = np.array(bg_img, dtype=float)
        bg_col_arr = np.array([[bg_color]], dtype=float)
        blended = np.clip(bg_img_arr * (1 - color_ratio) + bg_col_arr * color_ratio, 0, 255).astype(np.uint8)
        canvas = Image.fromarray(blended).convert("RGBA")
        canvas = self._add_film_grain(canvas, 0.03)
        
        square_img = self._crop_to_square(original_img)
        card_size = int(CANVAS_SIZE[1] * 0.7)
        square_img = square_img.resize((card_size, card_size), Image.LANCZOS)
        
        main_card = self._add_rounded_corners(square_img, card_size//8).convert("RGBA")
        
        def make_aux_card(radius, color, mix_ratio):
            blurred = square_img.copy().filter(ImageFilter.GaussianBlur(radius=radius))
            blended_aux = np.clip(np.array(blurred, float) * (1-mix_ratio) + np.array([[color]], float) * mix_ratio, 0, 255).astype(np.uint8)
            return self._add_rounded_corners(Image.fromarray(blended_aux), card_size//8).convert("RGBA")

        aux_card1 = make_aux_card(8, card_colors[0], 0.5)
        aux_card2 = make_aux_card(16, card_colors[1], 0.6)
        
        cards_canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
        center_pos = (int(CANVAS_SIZE[0] - CANVAS_SIZE[1] * 0.5), int(CANVAS_SIZE[1] * 0.5))
        
        configs = [
            (aux_card2, 36, {'offset': (10, 16), 'radius': 12, 'opacity': 0.4}),
            (aux_card1, 18, {'offset': (15, 22), 'radius': 15, 'opacity': 0.5}),
            (main_card, 0,  {'offset': (20, 26), 'radius': 18, 'opacity': 0.6})
        ]
        
        for card, angle, conf in configs:
            cards_canvas = self._add_shadow_and_rotate(cards_canvas, card, angle, **conf, center_pos=center_pos)
            
        canvas = Image.alpha_composite(canvas, cards_canvas)
        
        # Text
        shadow_color = self._darken_color(bg_color, 0.8) + (75,)
        left_center_x = int(CANVAS_SIZE[0] * 0.25)
        left_center_y = CANVAS_SIZE[1] // 2
        
        zh_size = int(CANVAS_SIZE[1] * 0.17 * zh_font_size_ratio)
        en_size = int(CANVAS_SIZE[1] * 0.07 * en_font_size_ratio)
        
        dummy_draw = ImageDraw.Draw(Image.new("L", (1,1)))
        zh_font = ImageFont.truetype(zh_font_path, zh_size)
        zh_bbox = dummy_draw.textbbox((0,0), title_zh, font=zh_font)
        zh_w, zh_h = zh_bbox[2]-zh_bbox[0], zh_bbox[3]-zh_bbox[1]
        zh_x, zh_y = left_center_x - zh_w // 2, left_center_y - zh_h - en_size // 2 - 5
        
        canvas = self._draw_text(canvas, title_zh, (zh_x, zh_y), zh_font_path, zh_size, shadow=True, shadow_color=shadow_color, shadow_alpha=75, shadow_offset=12)
        
        if title_en:
            en_font = ImageFont.truetype(en_font_path, en_size)
            en_bbox = dummy_draw.textbbox((0,0), title_en, font=en_font)
            en_w = en_bbox[2]-en_bbox[0]
            en_x, en_y = left_center_x - en_w // 2, zh_y + zh_h + en_size
            canvas = self._draw_text(canvas, title_en, (en_x, en_y), en_font_path, en_size, shadow=True, shadow_color=shadow_color, shadow_alpha=75, shadow_offset=6)
            
        return self._image_to_base64(canvas)

    def generate_style_single_2(self, image_paths: List[str], title_zh: str, title_en: str, 
                                font_zh_name: str, font_en_name: str, 
                                zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False) -> str:
        # Requires 1 image
        if not image_paths: raise ValueError("Single Style 2 requires at least 1 image")
        image_path = image_paths[0]
        
        zh_font_path = self.get_font_path(font_zh_name)
        en_font_path = self.get_font_path(font_en_name) or zh_font_path

        def align_image_right(img, size):
            cw, ch = size
            tw = int(cw * 0.675)
            iw, ih = img.size
            
            scale = ch / ih
            nw = int(iw * scale)
            resized = img.resize((nw, ch), Image.LANCZOS)
            
            if nw < tw:
                scale = tw / iw
                nh = int(ih * scale)
                resized = img.resize((tw, nh), Image.LANCZOS)
                crop_top = (nh - ch) // 2
                resized = resized.crop((0, crop_top, tw, crop_top + ch))
                final = Image.new("RGB", size)
                final.paste(resized, (cw - tw, 0))
                return final

            cx = nw / 2
            cl = max(0, cx - tw / 2)
            if cl + tw > nw: cl = nw - tw
            cropped = resized.crop((int(cl), 0, int(cl + tw), ch))
            final = Image.new("RGB", size)
            paste_x = cw - cropped.width + int(cw * 0.075)
            final.paste(cropped, (paste_x, 0))
            return final

        fg_img_orig = Image.open(image_path).convert("RGB")
        fg_img = align_image_right(fg_img_orig, CANVAS_SIZE)
        
        vibrant = self._find_dominant_vibrant_colors(fg_img)
        bg_color = vibrant[0] if vibrant else (237, 159, 77)
        shadow_color = self._darken_color(bg_color, 0.5)
        
        bg_img = ImageOps.fit(Image.open(image_path).convert("RGB"), CANVAS_SIZE, Image.LANCZOS).filter(ImageFilter.GaussianBlur(int(blur_size)))
        
        bg_fill = self._darken_color(bg_color, 0.85)
        blended_bg = np.clip(np.array(bg_img, float)*(1-color_ratio) + np.array([[bg_fill]], float)*color_ratio, 0, 255).astype(np.uint8)
        blended_bg_img = self._add_film_grain(Image.fromarray(blended_bg), 0.05)
        
        # Diagonal Mask
        w, h = CANVAS_SIZE
        mask = Image.new('L', CANVAS_SIZE, 255)
        mdraw = ImageDraw.Draw(mask)
        top_x, bot_x = int(w * 0.55), int(w * 0.4)
        mdraw.polygon([(top_x, 0), (w, 0), (w, h), (bot_x, h)], fill=0) # Right side black (transparent in composite)
        
        # Shadow Mask
        s_mask = Image.new('L', CANVAS_SIZE, 0)
        s_draw = ImageDraw.Draw(s_mask)
        sw = 10
        s_draw.polygon([(top_x - 5, 0), (top_x - 5 + sw, 0), (bot_x - 5 + sw, h), (bot_x - 5, h)], fill=255)
        s_mask = s_mask.filter(ImageFilter.GaussianBlur(10))
        
        # Composite
        canvas = fg_img.copy()
        s_layer = Image.new("RGB", CANVAS_SIZE, shadow_color)
        canvas.paste(s_layer, mask=s_mask)
        canvas = Image.composite(blended_bg_img, canvas, mask)
        
        # Text
        canvas = canvas.convert("RGBA")
        left_cx, left_cy = int(w * 0.25), h // 2
        zh_size = int(h * 0.17 * zh_font_size_ratio)
        en_size = int(h * 0.07 * en_font_size_ratio)
        
        dummy = ImageDraw.Draw(Image.new("L", (1,1)))
        zh_font = ImageFont.truetype(zh_font_path, zh_size)
        zh_bbox = dummy.textbbox((0,0), title_zh, font=zh_font)
        zh_x, zh_y = left_cx - (zh_bbox[2]-zh_bbox[0])//2, left_cy - (zh_bbox[3]-zh_bbox[1]) - en_size//2 - 5
        
        shadow_c = self._darken_color(bg_color, 0.8) + (75,)
        canvas = self._draw_text(canvas, title_zh, (zh_x, zh_y), zh_font_path, zh_size, shadow=True, shadow_color=shadow_c, shadow_offset=12)
        
        if title_en:
             en_font = ImageFont.truetype(en_font_path, en_size)
             en_bbox = dummy.textbbox((0,0), title_en, font=en_font)
             en_x, en_y = left_cx - (en_bbox[2]-en_bbox[0])//2, zh_y + (zh_bbox[3]-zh_bbox[1]) + en_size
             canvas = self._draw_text(canvas, title_en, (en_x, en_y), en_font_path, en_size, shadow=True, shadow_color=shadow_c, shadow_offset=6)

        return self._image_to_base64(canvas)

    def generate_style_multi_1(self, image_paths: List[str], title_zh: str, title_en: str, 
                               font_zh_name: str, font_en_name: str, 
                               zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                               blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False) -> str:
        
        # Ensure we have enough images or duplicate
        if not image_paths: raise ValueError("Multi Style 1 requires images")
        
        zh_font_path = self.get_font_path(font_zh_name)
        en_font_path = self.get_font_path(font_en_name) or zh_font_path
        
        # Config aliases
        cfg = POSTER_GEN_CONFIG
        
        first_img = Image.open(image_paths[0]).convert("RGB")
        vibrant = self._find_dominant_vibrant_colors(first_img)
        blur_color = vibrant[0] if vibrant else (237, 159, 77)
        
        # Background Logic
        if is_blur:
             bg_img = self._create_blur_background(image_paths[0], cfg["CANVAS_WIDTH"], cfg["CANVAS_HEIGHT"], blur_color, blur_size, color_ratio)
        else:
             grad_color = self._get_poster_primary_color(image_paths[0])
             bg_img = self._create_gradient_background(cfg["CANVAS_WIDTH"], cfg["CANVAS_HEIGHT"], grad_color)

        result = bg_img.copy()
        
        # Prepare Images
        target_count = cfg["ROWS"] * cfg["COLS"]
        while len(image_paths) < target_count:
             image_paths.extend(image_paths) # Repeat
        
        poster_files = image_paths[:target_count]
        
        # Sorting Logic
        ranks = [3, 1, 5, 4, 2, 6, 9, 8, 7]
        reordered = [None] * 9
        for slot_idx, rank in enumerate(ranks):
            # rank is 1-based.
            if rank <= len(poster_files):
                reordered[slot_idx] = poster_files[rank-1]
            else:
                reordered[slot_idx] = poster_files[0] # Fallback
        
        poster_files = reordered
        
        # Grid Logic
        grouped = [poster_files[i:i+cfg["ROWS"]] for i in range(0, len(poster_files), cfg["ROWS"])]
        
        for col_idx, col_posters in enumerate(grouped):
            if col_idx >= cfg["COLS"]:
                 break
            
            col_x = cfg["START_X"] + col_idx * cfg["COLUMN_SPACING"]
            col_h = cfg["ROWS"] * cfg["CELL_HEIGHT"] + (cfg["ROWS"] - 1) * cfg["MARGIN"]
            
            # Create column strip
            shadow_w_ext, shadow_h_ext = 60, 60
            col_img = Image.new("RGBA", (cfg["CELL_WIDTH"] + shadow_w_ext, col_h + shadow_h_ext), (0,0,0,0))
            
            for row_idx, p_path in enumerate(col_posters):
                try:
                    p = Image.open(p_path)
                    p_resized = ImageOps.fit(p, (cfg["CELL_WIDTH"], cfg["CELL_HEIGHT"] ), Image.LANCZOS)
                    p_rounded = self._add_rounded_corners(p_resized, cfg["CORNER_RADIUS"] ).convert("RGBA")
                    p_shadowed = self._add_shadow_simple(p_rounded, (20,20), (0,0,0,216), 20)
                    
                    y_pos = row_idx * (cfg["CELL_HEIGHT"] + cfg["MARGIN"])
                    col_img.paste(p_shadowed, (0, y_pos), p_shadowed)
                except: continue
            
            # Rotate Column
            diag = int(math.sqrt(col_img.width**2 + col_img.height**2) * 1.5)
            rot_canvas = Image.new("RGBA", (diag, diag), (0,0,0,0))
            rot_canvas.paste(col_img, ((diag - col_img.width)//2, (diag - col_img.height)//2), col_img)
            rot_col = rot_canvas.rotate(cfg["ROTATION_ANGLE"], Image.BICUBIC, expand=True)
            
            # Position on Main Canvas
            cy = cfg["START_Y"] + col_h // 2
            cx = col_x
            if col_idx == 1: cx += 380
            elif col_idx == 2: cy -= 155; cx += 760
            
            fx = cx - rot_col.width // 2 + cfg["CELL_WIDTH"] // 2
            fy = cy - rot_col.height // 2
            
            result.paste(rot_col, (int(fx), int(fy)), rot_col)

        # Text
        shadow_c = self._darken_color(blur_color, 0.8)
        
        # ZH Title
        result = self._draw_text(result, title_zh, (73, 427), zh_font_path, int(163 * zh_font_size_ratio), 
                                 shadow=True, shadow_color=shadow_c, shadow_offset=10)

        # EN Title
        if title_en:
            base_size = 50 * en_font_size_ratio
            line_spacing = base_size * 0.1
            wc = len(title_en.split())
            mc = max([len(w) for w in title_en.split()])
            f_size = base_size
            if mc > 10 or wc > 3: f_size = max(base_size * (10 / max(mc, wc*3))**0.8, 30)
            
            result, line_count = self._draw_multiline_text(result, title_en, (125, 625), en_font_path, int(f_size), 
                                                           line_spacing, shadow=True, shadow_color=shadow_c)
            
            # Color Block
            rand_color = (random.randint(50,200), random.randint(50,200), random.randint(50,200), 255)
            block_h = base_size + line_spacing + (line_count - 1) * (int(f_size) + line_spacing)
            draw = ImageDraw.Draw(result)
            draw.rectangle([(84, 620), (84+21, 620+block_h)], fill=rand_color)
            
        return self._image_to_base64(result)

    def generate_style_multi_animated(self, image_paths: List[str], title_zh: str, title_en: str, 
                                     font_zh_name: str, font_en_name: str, 
                                     zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                     blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False,
                                     animation_format: str = "gif") -> str:
        if not image_paths: raise ValueError("Multi Animated Style requires images")
        
        animation_format = animation_format.lower()
        zh_font_path = self.get_font_path(font_zh_name)
        en_font_path = self.get_font_path(font_en_name) or zh_font_path
        
        cfg = POSTER_GEN_CONFIG
        # Use 320x180 resolution (16:9) for better quality while maintaining compatibility with Emby dynamic wallpapers
        template_width = 320
        template_height = 180
        scale_factor = template_width / cfg["CANVAS_WIDTH"]
        
        first_img = None
        try:
            first_img = Image.open(image_paths[0]).convert("RGB")
            vibrant = self._find_dominant_vibrant_colors(first_img)
            blur_color = vibrant[0] if vibrant else (237, 159, 77)
            
            if is_blur:
                bg_img = self._create_blur_background(image_paths[0], template_width, template_height, blur_color, int(blur_size * scale_factor), color_ratio)
            else:
                grad_color = self._get_poster_primary_color(image_paths[0])
                bg_img = self._create_gradient_background(template_width, template_height, grad_color)

            # Prepare 9 images
            target_count = cfg["ROWS"] * cfg["COLS"]
            while len(image_paths) < target_count:
                image_paths.extend(image_paths)
            poster_files = image_paths[:target_count]
            
            # Reorder for columns
            reordered = []
            for col in range(cfg["COLS"]):
                for row in range(cfg["ROWS"]):
                    idx = row * cfg["COLS"] + col
                    if idx < len(poster_files): reordered.append(poster_files[idx])
            
            grouped = [reordered[i:i+cfg["ROWS"]] for i in range(0, len(reordered), cfg["ROWS"])]
            
            cell_width = int(cfg["CELL_WIDTH"] * scale_factor)
            cell_height = int(cfg["CELL_HEIGHT"] * scale_factor)
            margin = int(cfg["MARGIN"] * scale_factor)
            corner_radius = int(cfg["CORNER_RADIUS"] * scale_factor)
            
            extended_columns = []
            column_heights = []
            for col_posters in grouped:
                ext_col, h = self._create_extended_column(col_posters, cell_width, cell_height, margin, corner_radius)
                extended_columns.append(ext_col)
                column_heights.append(h)
                
            frame_count = 120  # Increased from 24 to 120 for super smooth animation
            frame_duration = 67 # ms (15 FPS)
            frames = []
            
            # Pre-calculate text color/block to avoid flickering
            rand_color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200), 255)
            shadow_c = self._darken_color(blur_color, 0.8)

            for i in range(frame_count):
                frame = self._generate_animation_frame(bg_img, extended_columns, column_heights, i, frame_count, cfg, scale_factor)
                
                # Add text
                frame = self._draw_text(frame, title_zh, (int(73 * scale_factor), int(427 * scale_factor)), zh_font_path, int(163 * zh_font_size_ratio * scale_factor), 
                                       shadow=True, shadow_color=shadow_c, shadow_offset=int(10 * scale_factor))
                
                if title_en:
                    base_size = 50 * en_font_size_ratio * scale_factor
                    line_spacing = base_size * 0.1
                    wc = len(title_en.split())
                    mc = max([len(w) for w in title_en.split()])
                    f_size = base_size
                    if mc > 10 or wc > 3: f_size = max(base_size * (10 / max(mc, wc*3))**0.8, 30 * scale_factor)
                    
                    frame, line_count = self._draw_multiline_text(frame, title_en, (int(125 * scale_factor), int(625 * scale_factor)), en_font_path, int(f_size), 
                                                                   line_spacing, shadow=True, shadow_color=shadow_c, shadow_offset=int(4 * scale_factor))
                    
                    block_h = base_size + line_spacing + (line_count - 1) * (int(f_size) + line_spacing)
                    draw = ImageDraw.Draw(frame)
                    bx, by = int(84 * scale_factor), int(620 * scale_factor)
                    bw = int(21 * scale_factor)
                    draw.rectangle([(bx, by), (bx + bw, by + block_h)], fill=rand_color)
                
                frames.append(frame)

            # Save animation
            result = self._save_animation(frames, animation_format, frame_duration)
            
            # 显式释放所有帧和中间图片
            for f in frames:
                f.close()
            for ec in extended_columns:
                ec.close()
            bg_img.close()
            
            return result
        finally:
            if first_img is not None:
                first_img.close()

    def _prepare_background(self, bg_path, size, blur_radius=0):
        """Helper to prepare background images correctly without excessive zooming"""
        bg = Image.open(bg_path).convert("RGB")
        # Use fit with centering to minimize 'zoomed' feel, or pad if ratios are too extreme
        # For fanart/backdrop, we want it to cover the screen
        bg = ImageOps.fit(bg, size, method=Image.LANCZOS, centering=(0.5, 0.5))
        if blur_radius > 0:
            bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        # Add a subtle dark overlay for better poster visibility
        overlay = Image.new("RGBA", size, (0, 0, 0, 60))
        bg_rgba = bg.convert("RGBA")
        return Image.alpha_composite(bg_rgba, overlay)

    def generate_style_6_plus_1(self, image_paths: List[str], title_zh: str, title_en: str, 
                                font_zh_name: str, font_en_name: str, 
                                zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False,
                                animation_format: str = "gif") -> str:
        if len(image_paths) < 2: raise ValueError("Style 6+1 requires background and posters")
        bg_path, poster_paths = image_paths[0], image_paths[1:]
        while len(poster_paths) < 6: poster_paths.extend(poster_paths)
        poster_paths = poster_paths[:6]
        
        template_width, template_height = 320, 180
        scale = template_width / 1920
        
        # Background: Using improved preparation (Clear but dimmed)
        # Use lower blur or no blur by default for this style unless specified
        bg_img = self._prepare_background(bg_path, (template_width, template_height), int(blur_size * scale) if is_blur else 0)
        
        # Larger posters to show about 5.5 cards (Calculation: 1920 / 5.5 approx 350 per slot)
        p_w, p_h = int(310 * scale), int(465 * scale)
        margin = int(40 * scale)
        posters = []
        for p_path in poster_paths:
            p = ImageOps.fit(Image.open(p_path).convert("RGBA"), (p_w, p_h), Image.LANCZOS)
            p = self._add_rounded_corners(p, int(25 * scale))
            p = self._add_shadow_simple(p, (int(8*scale), int(8*scale)), (0,0,0,150), int(12*scale))
            posters.append(p)
            
        frame_count, frame_duration, frames = 120, 67, []
        strip_w = len(posters) * (p_w + margin)
        zh_font_path = self.get_font_path(font_zh_name)
        en_font_path = self.get_font_path(font_en_name) or zh_font_path

        for i in range(frame_count):
            frame = bg_img.copy()
            offset = (i / frame_count) * strip_w
            
            # Draw posters at the bottom
            for j in range(-1, 2):
                for idx, p in enumerate(posters):
                    x = int(j * strip_w + idx * (p_w + margin) - offset + template_width // 2 - p_w // 2)
                    y = int(template_height - p_h - 80 * scale)
                    if -p_w < x < template_width: frame.paste(p, (x, y), p)
            
            # Text moved further down
            if title_zh:
                text_x, text_y = int(80*scale), int(220*scale) # Moved down from 80
                zh_size = int(140 * zh_font_size_ratio * scale)
                frame = self._draw_text(frame, title_zh, (text_x, text_y), zh_font_path, zh_size, shadow=True, shadow_alpha=120)
                
                if title_en:
                    en_size = int(60 * en_font_size_ratio * scale)
                    frame = self._draw_text(frame, title_en.upper(), (text_x + int(5*scale), text_y + zh_size + int(15*scale)), en_font_path, en_size, shadow=True, shadow_alpha=100)
            
            frames.append(frame)
        return self._save_animation(frames, animation_format, frame_duration)

    def generate_style_9_plus_1(self, image_paths: List[str], title_zh: str, title_en: str, 
                                font_zh_name: str, font_en_name: str, 
                                zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False,
                                animation_format: str = "gif") -> str:
        if len(image_paths) < 2: raise ValueError("Style 9+1 requires background and posters")
        bg_path, poster_paths = image_paths[0], image_paths[1:]
        while len(poster_paths) < 9: poster_paths.extend(poster_paths)
        poster_paths = poster_paths[:9]
        
        # Local config for style 9+1 to avoid affecting other styles
        cfg = POSTER_GEN_CONFIG.copy()
        cfg.update({
            "START_X": 1205,
            "START_Y": -397,
        })
        
        template_width, template_height = 320, 180
        scale = template_width / cfg["CANVAS_WIDTH"]
        
        # Background: Using improved preparation
        bg_img = self._prepare_background(bg_path, (template_width, template_height), int(blur_size * scale) if is_blur else 0)
        
        reordered = []
        for col in range(cfg["COLS"]):
            for row in range(cfg["ROWS"]):
                reordered.append(poster_paths[(row * cfg["COLS"] + col) % len(poster_paths)])
        
        grouped = [reordered[i:i+cfg["ROWS"]] for i in range(0, len(reordered), cfg["ROWS"])]
        cell_w, cell_h = int(cfg["CELL_WIDTH"] * scale), int(cfg["CELL_HEIGHT"] * scale)
        margin, corner = int(cfg["MARGIN"] * scale), int(cfg["CORNER_RADIUS"]*scale)
        
        extended_columns, column_heights = [], []
        for col_posters in grouped:
            ext_col, h = self._create_extended_column(col_posters, cell_w, cell_h, margin, corner)
            extended_columns.append(ext_col); column_heights.append(h)
            
        frame_count, frame_duration, frames = 120, 67, []

        for i in range(frame_count):
            frame = self._generate_animation_frame(bg_img, extended_columns, column_heights, i, frame_count, cfg, scale)
            frames.append(frame)
        return self._save_animation(frames, animation_format, frame_duration)

    def generate_style_5_horizontal(self, image_paths: List[str], title_zh: str, title_en: str, 
                                   font_zh_name: str, font_en_name: str, 
                                   zh_font_size_ratio: float = 1.0, en_font_size_ratio: float = 1.0,
                                   blur_size: int = 50, color_ratio: float = 0.8, is_blur: bool = False,
                                   animation_format: str = "gif") -> str:
        if not image_paths: raise ValueError("Style 5 requires images")
        
        # Limit to 4 images as requested
        poster_paths = image_paths[:4]
        while len(poster_paths) < 4: poster_paths.extend(poster_paths)
        poster_paths = poster_paths[:4]
        
        template_width, template_height = 320, 180
        scale = template_width / 1920
        
        # Background: Solid Black, no light or blur
        bg_img = Image.new("RGBA", (template_width, template_height), (0, 0, 0, 255))
        
        # Layout: Top 2/3 (poster) + Bottom 1/3 (reflection)
        main_h = int(template_height * 2 / 3)
        reflection_h = template_height - main_h
        p_w = int(main_h * 2 / 3) 
        margin = int(25 * scale)
        
        posters = []
        for p_path in poster_paths:
            # Main Poster (Top 2/3)
            p_main = ImageOps.fit(Image.open(p_path).convert("RGBA"), (p_w, main_h), Image.LANCZOS)
            
            # Create Reflection (Bottom 1/3)
            reflection = p_main.crop((0, main_h - reflection_h, p_w, main_h)).transpose(Image.FLIP_TOP_BOTTOM)
            # Very subtle blur to keep it sharp and clear
            reflection = reflection.filter(ImageFilter.GaussianBlur(radius=0.5 * scale))
            
            # Reflection Gradient Mask (High visibility, slow fade)
            mask = Image.new("L", (p_w, reflection_h), 0)
            for y in range(reflection_h):
                # Slower fade: stays visible longer
                ratio = 1 - (y / reflection_h)
                alpha = int(200 * (ratio ** 0.7)) 
                for x in range(p_w):
                    mask.putpixel((x, y), alpha)
            
            # Combine Main and Reflection
            full_p = Image.new("RGBA", (p_w, template_height), (0, 0, 0, 0))
            full_p.paste(p_main, (0, 0))
            full_p.paste(reflection, (0, main_h), mask)
            
            posters.append(full_p)
            
        frame_count, frame_duration, frames = 120, 67, []
        strip_w = len(posters) * (p_w + margin)

        for i in range(frame_count):
            frame = bg_img.copy()
            offset = (i / frame_count) * strip_w
            # Loop for continuous scrolling
            for j in range(-1, 2):
                for idx, p in enumerate(posters):
                    x = int(j * strip_w + idx * (p_w + margin) - offset + template_width // 2 - p_w // 2)
                    y = 0 
                    if -p_w < x < template_width: frame.paste(p, (x, y), p)
            frames.append(frame)
        return self._save_animation(frames, animation_format, frame_duration)

    def _save_animation(self, frames, format, duration):
        buffer = BytesIO()
        format = format.lower()
        if format == "webp":
            rgb_frames = [f.convert("RGBX") for f in frames]
            rgb_frames[0].save(buffer, format="WEBP", save_all=True, append_images=rgb_frames[1:], duration=duration, loop=0, quality=80, method=4)
            for f in rgb_frames:
                f.close()
        elif format == "png":
            frames[0].save(buffer, format="PNG", save_all=True, append_images=frames[1:], duration=duration, loop=0)
        else:
            gif_frames = []
            palette = frames[0].convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT)
            for f in frames:
                gif_frames.append(f.convert("RGB").quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG))
            gif_frames[0].save(buffer, format="GIF", save_all=True, append_images=gif_frames[1:], duration=duration, loop=0, optimize=True)
            for f in gif_frames:
                f.close()
            palette.close()
        return base64.b64encode(buffer.getvalue()).decode('utf-8')


    # ================= Public Generation Method =================
    
    def parse_title_config(self, text: str) -> dict:
        mapping = {}
        if not text:
            return mapping
            
        current_key = None
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if line.endswith(':'):
                current_key = line[:-1].strip()
                mapping[current_key] = []
            elif line.startswith('-') and current_key is not None:
                val = line[1:].strip()
                # Remove quotes if present
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                mapping[current_key].append(val)
        return mapping

    async def upload_cover(self, library_id: str, base64_image: str) -> None:
        if not globals.service or not globals.service.emby_client:
            raise RuntimeError("Emby Client not connected")
        
        # Determine format from base64 header or content
        content_type = "image/png"
        if "," in base64_image:
             header, base64_image = base64_image.split(",", 1)
             if "image/gif" in header: content_type = "image/gif"
             elif "image/webp" in header: content_type = "image/webp"
        else:
             # Auto detect from magic bytes in base64
             if base64_image.startswith("R0lGOD"): content_type = "image/gif"
             elif base64_image.startswith("UklGR"): content_type = "image/webp"
             # Default to image/png (which includes APNG)
        
        data_to_send = base64_image.encode('utf-8')
        
        headers = {
            "Content-Type": content_type,
        }
        
        endpoint = f"/Items/{library_id}/Images/Primary"
        
        log_audit("封面", "开始", f"正在上传图片到 Emby ({library_id}), Content-Type: {content_type}")
        _, err = await globals.service.emby_client._make_request("POST", endpoint, data=data_to_send, headers_override=headers, timeout=60)
        if err:
             raise RuntimeError(f"Upload failed: {err}")

    async def generate_cover(self, library_id: str, style_type: str, 
                             title_zh: str, title_en: str, 
                             font_zh: str, font_en: str,
                             zh_scale: float, en_scale: float,
                             blur: int, color_ratio: float,
                             is_blur: bool = False,
                             sort_by: str = "Random",
                             use_primary_first: bool = False,
                             animation_format: str = "gif") -> str:
        
        if not globals.service or not globals.service.emby_client:
            raise RuntimeError("Emby 客户端未连接")
            
        query_params = {
            'ParentId': library_id,
            'Recursive': 'true',
            'IncludeItemTypes': 'Movie,Series',
            'ImageTypes': 'Primary,Backdrop', # Fetch both to check existence
            'Limit': 30,
            'SortBy': sort_by,
            'Fields': 'Id,Name,ImageTags,BackdropImageTags,ParentBackdropImageTags,ParentBackdropItemId'
        }
        
        if sort_by == "Random":
             query_params['SortBy'] = "Random"
        elif sort_by == "DateCreated":
             query_params['SortBy'] = "DateCreated"
             query_params['SortOrder'] = "Descending"
        elif sort_by == "ProductionYear":
             query_params['SortBy'] = "ProductionYear"
             query_params['SortOrder'] = "Descending"
        elif sort_by == "CommunityRating":
             query_params['SortBy'] = "CommunityRating"
             query_params['SortOrder'] = "Descending"
        
        data, err = await globals.service.emby_client._make_request("GET", "/Items", params=query_params)
        
        # 如果指定类型没有结果，尝试去掉类型限制（特别是针对混合媒体库，里面可能直接放了视频文件或文件夹）
        if (not data or not data.get("Items")) and 'IncludeItemTypes' in query_params:
            log_audit("封面", "处理", f"媒体库 {library_id} 未找到电影或剧集项目，尝试取消类型限制重新获取...")
            query_params.pop('IncludeItemTypes')
            data, err = await globals.service.emby_client._make_request("GET", "/Items", params=query_params)

        if err or not data or not data.get("Items"):
            raise ValueError(f"无法从媒体库获取项目: {err}")
            
        items = data["Items"]
        log_audit("封面", "处理", f"从媒体库 {library_id} 获取到 {len(items)} 个项目")
        if not items:
            raise ValueError("媒体库为空")

        task_id = str(uuid.uuid4())
        task_dir = self.temp_dir / task_id
        task_dir.mkdir(exist_ok=True)
        
        image_paths = []
        
        try:
            needed = 1
            if style_type in ["multi_1", "multi_animated", "style_9_plus_1"]: needed = 9
            elif style_type == "style_6_plus_1": needed = 6
            elif style_type == "style_5_horizontal": needed = 5
            
            # Select items for posters
            selected_items = items[:needed]
            if len(selected_items) < needed:
                 while len(selected_items) < needed:
                      selected_items.append(random.choice(items))
            
            # If style needs a background, try to find a high quality backdrop item
            bg_item = None
            if style_type in ["style_6_plus_1", "style_9_plus_1"]:
                # Prefer items with backdrops for the background
                backdrop_items = [i for i in items if i.get("BackdropImageTags") or i.get("ParentBackdropImageTags")]
                bg_item = random.choice(backdrop_items) if backdrop_items else random.choice(items)

            async def dl(item, force_type=None):
                item_id = item.get("Id")
                
                tag_primary = item.get("ImageTags", {}).get("Primary")
                tag_backdrop = item.get("BackdropImageTags", [None])[0] if item.get("BackdropImageTags") else None
                tag_parent = item.get("ParentBackdropImageTags", [None])[0] if item.get("ParentBackdropImageTags") else None
                
                final_image_type = None
                final_item_id = item_id

                if force_type == "Backdrop":
                    if tag_backdrop: final_image_type = "Backdrop"
                    elif tag_parent: final_image_type = "Backdrop"; final_item_id = item.get("ParentBackdropItemId")
                    elif tag_primary: final_image_type = "Primary" # Last resort
                elif force_type == "Primary":
                    if tag_primary: final_image_type = "Primary"
                    elif tag_backdrop: final_image_type = "Backdrop"
                else:
                    # Normal priority logic
                    if use_primary_first:
                        if tag_primary: final_image_type = "Primary"
                        elif tag_backdrop: final_image_type = "Backdrop"
                        elif tag_parent: final_image_type = "Backdrop"; final_item_id = item.get("ParentBackdropItemId")
                    else:
                        if tag_backdrop: final_image_type = "Backdrop"
                        elif tag_parent: final_image_type = "Backdrop"; final_item_id = item.get("ParentBackdropItemId")
                        elif tag_primary: final_image_type = "Primary"
                
                if not final_image_type: return None

                path = task_dir / f"{uuid.uuid4()}.jpg"
                if await globals.service.emby_client.download_image_for_item(final_item_id, final_image_type, str(path)):
                    return str(path)
                return None
            
            log_audit("封面", "开始", f"开始为封面生成下载素材: {len(selected_items)} 个项目...")
            # Download posters - For foreground posters in new styles, we prefer Primary (vertical)
            poster_pref = "Primary" if style_type in ["style_6_plus_1", "style_9_plus_1", "style_5_horizontal"] else None
            
            results = await asyncio.gather(*[dl(item, poster_pref) for item in selected_items])
            image_paths = [r for r in results if r]
            
            # Download background if needed - FORCE Backdrop type
            bg_path = None
            if bg_item:
                bg_path = await dl(bg_item, "Backdrop")
                if bg_path:
                    # Background path is inserted at index 0
                    image_paths = [bg_path] + image_paths

            log_audit("封面", "完成", f"素材下载完成，成功获取 {len(image_paths)} 张图片。")
            if not image_paths:
                raise ValueError("未能下载任何有效的图片")

            loop = asyncio.get_running_loop()
            
            log_audit("封面", "开始", f"正在执行图片合成处理 (样式: {style_type})...")
            style_args = (image_paths, title_zh, title_en, font_zh, font_en, zh_scale, en_scale, blur, color_ratio, is_blur)

            if style_type == "single_1":
                return await loop.run_in_executor(None, self.generate_style_single_1, *style_args)
            elif style_type == "single_2":
                return await loop.run_in_executor(None, self.generate_style_single_2, *style_args)
            elif style_type == "multi_1":
                return await loop.run_in_executor(None, self.generate_style_multi_1, *style_args)
            elif style_type == "multi_animated":
                return await loop.run_in_executor(None, self.generate_style_multi_animated, *style_args, animation_format)
            elif style_type == "style_6_plus_1":
                return await loop.run_in_executor(None, self.generate_style_6_plus_1, *style_args, animation_format)
            elif style_type == "style_9_plus_1":
                return await loop.run_in_executor(None, self.generate_style_9_plus_1, *style_args, animation_format)
            elif style_type == "style_5_horizontal":
                return await loop.run_in_executor(None, self.generate_style_5_horizontal, *style_args, animation_format)
            else:
                raise ValueError(f"Unknown style: {style_type}")
                
        finally:
            try:
                shutil.rmtree(task_dir)
            except:
                 pass

cover_generator = CoverGeneratorService()
