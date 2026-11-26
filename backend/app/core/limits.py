"""单进程内存限流器（滑动窗口）。

约束：仅在「单 worker」部署下有效（与线上部署约定一致）。
将来扩多 worker 需替换为 Redis 等共享存储，届时本模块的接口保持不变。
"""

import threading
import time
from collections import deque

# 字典清理周期：每 500 次请求清理一次已过期的 key，防止被大量 IP 扫描撑大内存
_SWEEP_INTERVAL = 500


class SlidingWindowLimiter:
    """固定时间窗口内的滑动计数。

    同一 key 在 window_seconds 内最多允许 max_requests 次，超出即拒绝。
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._calls_since_sweep = 0

    def allow(self, key: str) -> tuple[bool, int]:
        """返回 (是否允许, 拒绝时建议等待的秒数)。"""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket

            # 丢弃窗口外的历史记录
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after

            bucket.append(now)
            self._sweep_if_needed(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _sweep_if_needed(self, now: float) -> None:
        self._calls_since_sweep += 1
        if self._calls_since_sweep < _SWEEP_INTERVAL:
            return
        self._calls_since_sweep = 0
        stale = [
            key
            for key, bucket in self._buckets.items()
            if not bucket or now - bucket[-1] >= self.window_seconds
        ]
        for key in stale:
            del self._buckets[key]


class RateLimiterRegistry:
    """按接口路径维护多个限流器。"""

    def __init__(self, rules: list[tuple[str, str, int, int]]):
        # rules: (路径, 方法, 最大次数, 窗口秒数)
        self._rules = {path: (method.upper(), SlidingWindowLimiter(max_requests, window))
                       for path, method, max_requests, window in rules}

    def check(self, path: str, method: str, client_ip: str) -> tuple[bool, int]:
        rule = self._rules.get(path)
        if rule is None:
            return True, 0
        rule_method, limiter = rule
        if method.upper() != rule_method:
            return True, 0
        return limiter.allow(client_ip)

    def reset(self) -> None:
        for _, limiter in self._rules.values():
            limiter.reset()
