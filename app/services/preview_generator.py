import os
import random
import shutil
import subprocess
import math
import asyncio
import uuid
import json # Added import
from pathlib import Path
from typing import List, Tuple, Optional
from app import globals
from app.common import get_config_path # Added import
from app.logger import log_audit


class PreviewGeneratorService:
    def __init__(self):
        self.temp_dir = Path("app/static/temp_previews")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = "ffmpeg"
        self.ffprobe_path = "ffprobe"
        # Use get_config_path to ensure correct data directory
        # Changed to preview_generator_config.json to avoid conflict with cover_generator
        self.config_path = Path(get_config_path("preview_generator_config.json"))
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log_audit("预览", "失败", f"加载配置失败: {e}", level="ERROR")
        return {
            "count": 12,
            "start_pct": 10,
            "end_pct": 90,
            "path_mappings": []
        }

    def save_config(self, new_config: dict) -> Tuple[bool, str]:
        try:
            # Merge with existing
            self.config.update(new_config)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True, "配置保存成功"
        except Exception as e:
            log_audit("预览", "失败", f"保存配置失败: {e}", level="ERROR")
            return False, str(e)

    def get_config(self) -> dict:
        return self.config

    async def get_media_source_info(self, item_id: str) -> Tuple[Optional[str], float]:
        """
        Get the file path and duration (in seconds) of the media item.
        """
        if not globals.service or not globals.service.emby_client:
            raise RuntimeError("Emby Client not connected")
        
        client = globals.service.emby_client
        # We need to fetch item info including MediaSources
        # The reference script uses /Users/{UserId}/Items/{ItemId} which returns MediaSources for that user context
        # We can use the client's existing mechanism or a direct request
        
        await client._ensure_user_id()
        endpoint = f"/Users/{client.user_id}/Items/{item_id}"
        data, err = await client._make_request("GET", endpoint)
        
        if err or not data:
            log_audit("预览", "处理", f"无法获取项目 {item_id} 的信息: {err}", level="ERROR")
            return None, 0

        final_path = None
        duration_ticks = 0

        if data.get('MediaSources') and isinstance(data['MediaSources'], list) and len(data['MediaSources']) > 0:
            media_source = data['MediaSources'][0]
            final_path = media_source.get('Path')
            duration_ticks = media_source.get('RunTimeTicks', 0)
        else:
            final_path = data.get('Path')
            duration_ticks = data.get('RunTimeTicks', 0)

        if not final_path:
            log_audit("预览", "处理", f"ID: {item_id} 未找到路径。", level="ERROR")
            return None, 0
        
        duration_sec = duration_ticks / 10000000 if duration_ticks else 0
        return final_path, duration_sec

    def get_video_duration(self, video_path: str) -> float:
        """
        Get video duration using ffprobe directly (fallback if Emby doesn't provide it).
        """
        command = [self.ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', 
                   '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        log_audit("预览", "处理", f"执行 ffprobe: {' '.join(command)}")
        try:
            result = subprocess.run(command, capture_output=True, check=True, timeout=60)
            duration = float(result.stdout.decode('utf-8').strip())
            log_audit("预览", "处理", f"FFprobe 时长结果: {duration}秒")
            return duration
        except subprocess.CalledProcessError as e:
            log_audit("预览", "失败", f"ffprobe 失败。返回码: {e.returncode}", level="ERROR")
            log_audit("预览", "处理", f"stderr: {e.stderr.decode('utf-8', errors='ignore')}", level="ERROR")
            return 0
        except Exception as e:
            log_audit("预览", "失败", f"ffprobe 错误: {e}", level="ERROR")
            return 0

    def create_screenshot(self, video_path: str, timestamp: float, output_path: str) -> bool:
        """
        Capture a single screenshot at the given timestamp.
        Scales to fit 1920x1080 and pads with black bars to preserve aspect ratio.
        """
        timestamp_int = math.floor(timestamp)
        # Using -ss before -i is faster (seek)
        # Scale to fit 1920x1080 (decreasing if larger), then pad to exactly 1920x1080 with black background
        # This ensures the output is always 1920x1080 16:9, preserving original content aspect ratio
        command = [self.ffmpeg_path, '-y',
                   '-analyzeduration', '20000000', '-probesize', '20000000',
                   '-ss', str(timestamp_int), '-i', video_path,
                   '-vf', "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                   '-frames:v', '1', output_path]
        
        log_audit("预览", "处理", f"执行 ffmpeg: {' '.join(command)}")
        try:
            result = subprocess.run(command, check=True, capture_output=True, timeout=60)
            log_audit("预览", "完成", f"截图成功 (时间点: {timestamp_int}s): {output_path}")
            return True
        except subprocess.CalledProcessError as e:
            log_audit("预览", "失败", f"ffmpeg 在 {timestamp_int}秒处失败。", level="ERROR")
            log_audit("预览", "处理", f"Return code: {e.returncode}", level="ERROR")
            log_audit("预览", "处理", f"stderr: {e.stderr.decode('utf-8', errors='ignore')}", level="ERROR")
            return False
        except Exception as e:
            log_audit("预览", "失败", f"ffmpeg 截图错误: {e}", level="ERROR")
            return False

    async def generate_previews(self, item_id: str, count: int = 12, 
                                start_pct: int = 10, end_pct: int = 90,
                                path_mappings: List[dict] = []) -> Tuple[bool, str, List[str], str]:
        """
        Generate a batch of previews for the given item.
        Returns: (success, message, list_of_relative_urls, session_id)
        """
        try:
            media_path, emby_duration = await self.get_media_source_info(item_id)
            if not media_path:
                return False, "无法获取媒体路径，请确认 Emby 中该项目存在且有文件路径。", [], ""

            # Apply Path Mappings
            original_path = media_path
            if path_mappings:
                log_audit("预览", "处理", f"收到路径映射: {path_mappings}")
                for m in path_mappings:
                    # Support multiple formats: source/target, source_prefix/target_prefix, key/value (Naive UI)
                    src = m.get('source', '') or m.get('source_prefix', '') or m.get('key', '')
                    tgt = m.get('target', '') or m.get('target_prefix', '') or m.get('value', '')
                    
                    if src and tgt and media_path.startswith(src):
                        media_path = media_path.replace(src, tgt, 1)
                        log_audit("预览", "处理", f"路径映射: {original_path} -> {media_path}")
                        break
                else:
                    log_audit("预览", "查询", f"未找到匹配的路径映射: {media_path}")
            else:
                log_audit("预览", "处理", "未提供路径映射。")
            # Check if file exists locally (if Emby is local or mapped correctly)
            # If not locally accessible, this will fail. 
            # The reference script assumes local access or mapped paths.
            # In a docker container, the path MUST be accessible.
            is_url = media_path.lower().startswith('http://') or media_path.lower().startswith('https://')
            if not is_url and not os.path.exists(media_path):
                 # Try to check if we can access it via some mapping?
                 # For now, assume mapped. If not, maybe we can't do it without downloading file (too slow).
                 # Or maybe the path from Emby IS the container path if configured so.
                 # Let's check duration with ffprobe to verify access.
                 if not os.path.exists(media_path):
                     return False, f"媒体文件无法在本地访问: {media_path}。请确保 Emby 媒体目录已挂载到此容器。", [], ""

            duration = emby_duration
            
            # Force verify duration with ffprobe if path is a URL or was mapped
            # This ensures the file is actually accessible and metadata is correct for the new path
            if is_url or original_path != media_path or duration == 0:
                log_audit("预览", "开始", f"路径是URL或已映射，正在使用 ffprobe 验证时长: {media_path}")
                # ffprobe 是同步 subprocess（最长 60s），放线程池避免阻塞事件循环
                probed_duration = await asyncio.to_thread(self.get_video_duration, media_path)
                if probed_duration > 0:
                    duration = probed_duration
                else:
                    log_audit("预览", "失败", "FFprobe 获取时长失败，回退到 Emby 时长。", level="WARN")
            if duration < 30:
                return False, f"视频时长太短 (<30秒): {duration}s", [], ""

            session_id = str(uuid.uuid4())
            session_dir = self.temp_dir / session_id
            session_dir.mkdir(exist_ok=True)

            start_time = duration * (start_pct / 100.0)
            end_time = duration * (end_pct / 100.0)
            
            generated_paths = []
            relative_urls = []
            
            attempts = 0
            max_attempts = count * 3

            loop = asyncio.get_running_loop()

            while len(generated_paths) < count and attempts < max_attempts:
                attempts += 1
                timestamp = random.uniform(start_time, end_time)
                filename = f"preview_{len(generated_paths) + 1}.jpg"
                out_path = session_dir / filename
                
                # Run ffmpeg in executor to avoid blocking async loop
                success = await loop.run_in_executor(None, self.create_screenshot, media_path, timestamp, str(out_path))
                
                if success:
                    generated_paths.append(str(out_path))
                    # URL relative to static mount
                    relative_urls.append(f"/static/temp_previews/{session_id}/{filename}")

            if not generated_paths:
                shutil.rmtree(session_dir)
                return False, "未能生成任何有效的截图。", [], ""
            
            return True, "生成完成", relative_urls, session_id

        except Exception as e:
            log_audit("预览", "处理", f"生成预览图时出错: {e}", level="ERROR")
            return False, str(e), [], ""

    async def upload_selected_image(self, item_id: str, relative_path: str) -> Tuple[bool, str]:
        """
        Upload the selected image to Emby as Primary image.
        """
        if not globals.service or not globals.service.emby_client:
             return False, "Emby 客户端未连接"

        # Convert relative URL back to local path
        # relative_path ex: /static/temp_previews/{session_id}/preview_1.jpg
        try:
            # Strip /static/
            clean_path = relative_path.lstrip('/')
            if clean_path.startswith('static/'):
                clean_path = clean_path[7:]
            
            full_path = Path("app/static") / clean_path
            
            if not full_path.exists():
                return False, "图片文件已失效或被删除"

            # Use existing upload logic
            success, msg = await globals.service.emby_client.upload_collection_image(item_id, "Primary", str(full_path))
            
            # Cleanup session? 
            # Maybe we keep it for a bit or let the user generate again.
            # But usually once uploaded we can clear.
            # For now let's leave cleanup to a scheduled task or manual.
            
            return success, msg

        except Exception as e:
            return False, str(e)

    async def cleanup_old_previews(self, max_age_hours: int = 24):
        """
        Cleanup temporary preview directories older than max_age_hours.
        """
        log_audit("预览", "清理", "开始清理旧预览文件...")
        try:
            if not self.temp_dir.exists():
                return
            
            import time
            current_time = time.time()
            age_seconds = max_age_hours * 3600
            
            cleaned_count = 0
            
            for item in self.temp_dir.iterdir():
                if item.is_dir():
                    try:
                        # Check modification time
                        stat = item.stat()
                        if current_time - stat.st_mtime > age_seconds:
                            log_audit("预览", "清理", f"删除旧预览目录: {item}")
                            shutil.rmtree(item)
                            cleaned_count += 1
                    except Exception as e:
                        log_audit("预览", "失败", f"删除 {item} 失败: {e}", level="WARN")
            if cleaned_count > 0:
                log_audit("预览", "完成", f"清理完成。删除了 {cleaned_count} 个旧预览目录。")
            else:
                log_audit("预览", "完成", "清理完成。无需删除文件。")
        except Exception as e:
            log_audit("预览", "处理", f"Error during preview cleanup: {e}", level="ERROR")
preview_service = PreviewGeneratorService()
