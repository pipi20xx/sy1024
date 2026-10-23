import logging
import re
import sys
import os
import time
import asyncio
from collections import deque
from typing import List, Optional, Any
from app.utils.time import get_local_time

# --- 配置 ---
DATA_PATH = os.environ.get("DATA_PATH", "data")
LOG_DIR = os.path.join(DATA_PATH, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# --- 全局状态 (兼容性) ---
LOG_HISTORY = deque(maxlen=200)

# --- Formatter ---
class LogFormatter(logging.Formatter):
    """带颜色的控制台格式化，统一输出 级别 + 消息"""

    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    reset = "\x1b[0m"

    # 统一格式: 时间 | 级别 | 消息 (对齐 cs123)
    fmt_str = "%(asctime)s | %(levelname)-5s | %(message)s"

    FORMATS = {
        logging.DEBUG: fmt_str,
        logging.INFO: blue + fmt_str + reset,
        logging.WARNING: yellow + fmt_str + reset,
        logging.ERROR: red + fmt_str + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.fmt_str)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

# --- Broadcaster (类方法模式，对齐 cs123) ---
class LogBroadcaster:
    """实时日志广播管理器，支持多订阅者和历史回填"""
    _subscribers: set = set()
    _history: list = []

    @classmethod
    def subscribe(cls):
        queue = asyncio.Queue()
        cls._subscribers.add(queue)
        return queue

    @classmethod
    def unsubscribe(cls, queue):
        cls._subscribers.discard(queue)

    @classmethod
    async def broadcast(cls, message):
        """兼容方法：直接同步分发即可，不需要 async。
        保留 async 签名以兼容外部调用方。"""
        # 维护内存回填 (最后 100 条)
        cls._history.append(message)
        if len(cls._history) > 100:
            cls._history = cls._history[-100:]

        for queue in list(cls._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except Exception:
                    pass

    @classmethod
    def get_history(cls) -> list:
        """获取历史日志回填数据"""
        return list(cls._history)

# --- Handlers ---
class QueueHandler(logging.Handler):
    """WebSocket 广播处理器"""
    def emit(self, record):
        try:
            msg = self.format(record).strip()
            # 存入历史 (兼容)
            LOG_HISTORY.append(msg)

            # 直接同步写入所有 subscriber 的 queue，避免创建大量 fire-and-forget task
            # 如果没有 event loop（启动早期），跳过广播
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return

            # 维护 LogBroadcaster 的历史回填列表 (最后 100 条)
            LogBroadcaster._history.append(msg)
            if len(LogBroadcaster._history) > 100:
                LogBroadcaster._history = LogBroadcaster._history[-100:]

            # 同步分发到所有 subscriber queue
            for queue in list(LogBroadcaster._subscribers):
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    # 慢客户端：丢弃最旧的消息，放入最新的
                    try:
                        queue.get_nowait()
                        queue.put_nowait(msg)
                    except Exception:
                        pass
        except Exception:
            pass

class DailyFileHandler(logging.FileHandler):
    """自定义处理程序：始终以 YYYY-MM-DD.log 命名，并在跨天时自动切换"""

    def __init__(self, dirname, backupCount=7, encoding="utf-8"):
        self.dirname = dirname
        self.backupCount = backupCount
        self.encoding = encoding
        self.current_date = get_local_time().strftime("%Y-%m-%d")
        log_file = os.path.join(self.dirname, f"{self.current_date}.log")
        super().__init__(log_file, encoding=encoding)

    def emit(self, record):
        new_date = get_local_time().strftime("%Y-%m-%d")
        if new_date != self.current_date:
            self.current_date = new_date
            try:
                self.stream.close()
                self.baseFilename = os.path.join(self.dirname, f"{self.current_date}.log")
                self.stream = self._open()
                self._cleanup_old_logs()
            except Exception:
                self.handleError(record)
        super().emit(record)

    def _cleanup_old_logs(self):
        try:
            files = [f for f in os.listdir(self.dirname) if f.endswith(".log")]
            files.sort(reverse=True)
            if len(files) > self.backupCount:
                for old_file in files[self.backupCount:]:
                    os.remove(os.path.join(self.dirname, old_file))
        except Exception:
            pass

class MonitorLogHandler(logging.FileHandler):
    """monitor.log 每天清空，只保留当天日志。
    替代 TimedRotatingFileHandler：后者依赖 rolloverAt 时间戳，
    app 重启后重新计算会导致跨天轮转失效。
    本 handler 在每次 emit 时检查日期，跨天时截断文件。
    """
    def __init__(self, filename, encoding="utf-8"):
        self.current_date = get_local_time().strftime("%Y-%m-%d")
        self.encoding = encoding
        # 启动时检查文件是否包含旧日期的日志，如果是则截断
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding=encoding) as f:
                    first_line = f.readline().strip()
                if first_line and not first_line.startswith(self.current_date):
                    super().__init__(filename, mode="w", encoding=encoding)
                    return
            except Exception:
                pass
        super().__init__(filename, mode="a", encoding=encoding)

    def emit(self, record):
        new_date = get_local_time().strftime("%Y-%m-%d")
        if new_date != self.current_date:
            self.current_date = new_date
            self.stream.close()
            self.stream = open(self.baseFilename, "w", encoding=self.encoding)
        super().emit(record)

class StreamToLogger:
    """将 stdout/stderr 重定向到日志系统，捕获 print() 输出
    
    设计要点：
    1. 保存原始流引用，StreamHandler 写原始流，避免递归
    2. 过滤已格式化的日志行（匹配 "时间戳 | LEVEL |" 模式），避免双重格式化
    3. 递归保护：_in_write 标志防止死循环
    """
    # 匹配已格式化的日志行: "2026-07-24 20:03:48 | INFO  | ..." 或 "20:03:48 | INFO | ..."
    _LOG_PATTERN = re.compile(
        r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*\|\s*\w+\s*\|'
        r'|^\d{2}:\d{2}:\d{2}\s*\|\s*\w+\s*\|'
    )

    def __init__(self, logger_instance, level, original_stream):
        self.logger = logger_instance
        self.level = level
        self.original_stream = original_stream  # 保存原始 sys.stdout/stderr
        self._in_write = False  # 递归保护

    def write(self, buf):
        # 递归保护：如果已经在 write 中，直接写原始流，避免死循环
        if self._in_write:
            self.original_stream.write(buf)
            return

        # 空内容直接忽略
        if not buf or not buf.strip():
            return

        self._in_write = True
        try:
            for line in buf.rstrip().splitlines():
                line = line.rstrip()
                if not line:
                    continue
                # 跳过已格式化的日志行，避免双重时间戳
                if self._LOG_PATTERN.match(line):
                    continue
                self.logger.log(self.level, line)
        except Exception:
            # 日志系统异常时回退到原始流
            try:
                self.original_stream.write(buf)
            except Exception:
                pass
        finally:
            self._in_write = False

    def flush(self):
        self.original_stream.flush()

# --- Helper Functions ---
def get_log_dates() -> List[str]:
    """获取所有存在日志的日期列表"""
    try:
        files = [f.replace(".log", "") for f in os.listdir(LOG_DIR) if f.endswith(".log")]
        return sorted(files, reverse=True)
    except Exception:
        return []

def get_log_content(date: str, reverse: bool = False) -> str:
    """读取指定日期的完整日志文本"""
    # 处理 "monitor" 或 "today" 别名
    if date in ["monitor", "today"]:
        date = get_local_time().strftime("%Y-%m-%d")

    path = os.path.join(LOG_DIR, f"{date}.log")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if reverse:
                    lines.reverse()
                return "".join(lines)
        except Exception as e:
            return f"Error reading log: {str(e)}"
    return "Log file not found."

def get_last_n_logs(n: int = 100) -> List[str]:
    """获取当前日志文件最后的 n 行"""
    current_date = get_local_time().strftime("%Y-%m-%d")
    path = os.path.join(LOG_DIR, f"{current_date}.log")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-n:]]
    except Exception:
        return []

async def clean_old_logs():
    """清理旧日志逻辑"""
    retention_days = 7
    now = time.time()
    try:
        for filename in os.listdir(LOG_DIR):
            if filename.endswith(".log"):
                filepath = os.path.join(LOG_DIR, filename)
                if (now - os.path.getmtime(filepath)) > (retention_days * 86400):
                    os.remove(filepath)
                    log_audit("日志", "清理", f"已删除超期系统日志: {filename}", level="CLEAN")
    except Exception as e:
        log_audit("日志", "清理", f"清理日志失败: {e}", level="ERROR")

def audit_log(title: str, duration_ms: float, details: List[str]):
    """性能审计日志格式化输出"""
    if duration_ms < 100:
        return
    _logger = logging.getLogger()
    _logger.info("⏱️ [性能审计]: %s 耗时 %.0fms", title, duration_ms)
    if details:
        detail_str = " | ".join(details)
        _logger.info("┗ %s", detail_str)

def log_audit(module: str, action: str, message: str, level: str = "INFO", details: Any = None):
    """
    结构化审计日志 (对齐 cs123)

    Args:
        module: 模块名，如 "认证", "备份", "扫描", "Emby"
        action: 动作，如 "登录", "创建", "删除", "同步"
        message: 具体描述
        level: INFO / WARN / ERROR / SUCCESS / START / DONE / CLEAN / DB / AUTH
        details: 可选的补充细节行
    """
    lvl = getattr(logging, level.upper(), logging.INFO)
    _logger = logging.getLogger("System")

    # 映射 Emoji
    emoji_map = {
        "INFO": "✨",
        "WARN": "⚠️",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "SUCCESS": "✅",
        "START": "🚀",
        "DONE": "🏁",
        "CLEAN": "🗑️",
        "DB": "🗄️",
        "AUTH": "🔒",
        "DEBUG": "🔍",
        "CRITICAL": "💥",
    }

    emoji = emoji_map.get(level.upper(), "✨")
    if action in emoji_map:
        emoji = emoji_map[action]
    elif module in emoji_map:
        emoji = emoji_map[module]

    msg = f"{emoji} [{module}] {action}: {message}"
    _logger.log(lvl, msg)

    if details:
        detail_msg = f"┗ {details}"
        _logger.log(lvl, detail_msg)

# --- 初始化 ---
def init_logging(level=logging.INFO):
    """
    初始化根日志记录器，配置文件滚动、控制台、WebSocket 和 monitor.log。
    """
    root = logging.getLogger()
    root.setLevel(level)

    # 清除现有的 handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    # 1. 控制台输出
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(LogFormatter())
    root.addHandler(stdout_handler)

    # 2. WebSocket 广播处理器
    q_handler = QueueHandler()
    q_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-5s | %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(q_handler)

    # 3. 按天分割的文件记录
    try:
        file_handler = DailyFileHandler(LOG_DIR, backupCount=7, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        root.addHandler(file_handler)
    except Exception as e:
        logging.getLogger().error("设置文件日志处理器失败: %s", e)

    # 4. monitor.log 只保留当天的实时日志
    try:
        monitor_path = os.path.join(LOG_DIR, "monitor.log")
        monitor_handler = MonitorLogHandler(monitor_path, encoding="utf-8")
        monitor_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        root.addHandler(monitor_handler)
    except Exception as e:
        logging.getLogger().error("设置 monitor 日志处理器失败: %s", e)

    # 注意: 不再重定向 stdout/stderr
    # 之前的 StreamToLogger 重定向会导致已格式化的日志行被再次 log，
    # 产生双重时间戳。项目内 print() 调用极少，不值得为此引入回环风险。

    # 抑制吵闹的库
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

def get_logger(name: str):
    return logging.getLogger(name)

# 默认导出 logger，避免 import error
logger = logging.getLogger(__name__)
