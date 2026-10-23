import os
import time
from typing import Dict, Tuple

class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, lockout_minutes: int = 15):
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_minutes * 60
        # 存储格式: { ip: (失败次数, 最后一次失败时间) }
        self.attempts: Dict[str, Tuple[int, float]] = {}

    def is_locked(self, ip: str) -> Tuple[bool, int]:
        """检查该 IP 是否处于封锁状态，返回 (是否锁定, 剩余秒数)"""
        if ip not in self.attempts:
            return False, 0

        count, last_time = self.attempts[ip]
        if count >= self.max_attempts:
            remaining = int((last_time + self.lockout_duration) - time.time())
            if remaining > 0:
                return True, remaining
            else:
                # 封锁期已过，重置
                del self.attempts[ip]
                return False, 0
        return False, 0

    def record_failure(self, ip: str):
        """记录一次失败尝试"""
        count, _ = self.attempts.get(ip, (0, 0.0))
        self.attempts[ip] = (count + 1, time.time())

    def reset(self, ip: str):
        """登录成功后重置该 IP 的记录"""
        if ip in self.attempts:
            del self.attempts[ip]

# 全局单例
login_limiter = LoginRateLimiter()
