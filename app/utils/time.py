import os
import time
from datetime import datetime, timedelta, timezone

# 在模块加载时尝试应用 TZ 环境变量
if os.name != "nt" and "TZ" in os.environ:
    try:
        time.tzset()
    except Exception:
        pass


def get_local_time() -> datetime:
    """
    获取本地时间。
    1. 优先使用系统本地时间 (受 TZ 环境变量控制，如 Asia/Shanghai)
    2. 如果强制设置了 TZ_OFFSET 环境变量，则按偏移量计算
    """
    tz_offset_env = os.getenv("TZ_OFFSET")
    if tz_offset_env is not None:
        try:
            offset = int(tz_offset_env)
            # 使用 UTC 偏移量构造带有时区的 datetime
            return datetime.now(timezone(timedelta(hours=offset)))
        except:
            pass

    # 默认返回系统本地时间 (datetime.now() 会自动遵循已设置的 TZ)
    return datetime.now()


def format_time(dt: datetime = None) -> str:
    """格式化显示时间"""
    if dt is None:
        dt = get_local_time()
    return dt.strftime("%Y-%m-%d %H:%M:%S")
