# -*- coding: utf-8 -*-
"""
# @File    : rate_limiter.py
# @Date    : 2026-06-09
# @Author  : jeremyzhai
# @Description  : 令牌桶限流器
#
# 职责：提供线程安全的令牌桶限流能力，保护下游模型服务不被压垮。
#
# 使用方式：
#   from utils.rate_limiter import global_rate_limiter
#
#   # 请求前获取令牌（阻塞等待）
#   global_rate_limiter.acquire()
#   response = send_request()
#
#   # 获取当前统计信息
#   stats = global_rate_limiter.stats()
"""

import os
import time
import threading
from typing import Optional


class TokenBucket:
    """
    令牌桶限流器（线程安全）

    原理：
        - 以固定速率（rate）向桶中投放令牌
        - 每次请求消耗一个令牌
        - 桶的容量（burst）决定了允许的最大突发请求数
        - 令牌不足时，请求会阻塞等待直到获得令牌

    使用方式：
        limiter = TokenBucket(rate=60.0, burst=5)  # 每分钟60次，允许突发5次
        limiter.acquire()  # 获取令牌，可能阻塞等待
    """

    def __init__(
        self,
        rate: float = 60.0,
        burst: Optional[int] = None,
        enable: bool = True,
        name: str = "default",
    ):
        """
        初始化令牌桶限流器

        :param rate: 每分钟产生令牌数（RPM）
        :param burst: 桶容量（默认 rate / 60 * 3）
        :param enable: 是否启用限流（False 时 acquire 立即返回）
        :param name: 限流器名称（用于日志和统计）
        """
        self.rate_per_minute = max(0.1, rate)  # 最小 0.1，防止除零
        self.rate = self.rate_per_minute / 60.0  # 内部转换为每秒速率
        self.burst = burst or max(1, int(self.rate_per_minute / 60 * 3))
        self.enable = enable
        self.name = name

        self._lock = threading.Lock()
        self._tokens = float(self.burst)
        self._last_update = time.time()

        # 统计信息
        self._total_acquired = 0
        self._total_waited = 0.0
        self._max_wait = 0.0

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
        self._last_update = now

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        获取一个令牌（线程安全）

        采用循环重试策略：
        1. 加锁检查令牌是否足够
        2. 不够则计算等待时间，释放锁后 sleep
        3. 醒来后重新竞争锁，再次检查
        这样确保多线程并发时不会超发令牌。

        :param blocking: 是否阻塞等待
        :param timeout: 最大等待时间（秒），None 表示无限等待
        :return: 是否成功获取令牌
        """
        if not self.enable:
            return True

        deadline = time.time() + timeout if timeout else None
        total_wait = 0.0

        while True:
            with self._lock:
                self._refill()

                if self._tokens >= 1:
                    self._tokens -= 1
                    self._total_acquired += 1
                    if total_wait > 0:
                        self._total_waited += total_wait
                        self._max_wait = max(self._max_wait, total_wait)
                    return True

                if not blocking:
                    return False

                # 计算需要等待的时间
                wait_needed = (1 - self._tokens) / self.rate

                # 检查是否超时
                if deadline is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return False
                    wait_needed = min(wait_needed, remaining)

            # 释放锁后等待（让其他线程有机会获取锁并消费/补充令牌）
            time.sleep(max(0.01, wait_needed))
            total_wait += wait_needed

    def try_acquire(self) -> bool:
        """非阻塞获取令牌"""
        return self.acquire(blocking=False)

    def stats(self) -> dict:
        """获取限流统计信息"""
        with self._lock:
            return {
                "name": self.name,
                "rate_per_minute": self.rate_per_minute,
                "rate_per_second": round(self.rate, 2),
                "burst": self.burst,
                "current_tokens": round(self._tokens, 2),
                "total_acquired": self._total_acquired,
                "total_waited": round(self._total_waited, 3),
                "max_wait": round(self._max_wait, 3),
            }


# ============================================================
# 根据环境变量初始化全局限流器
# ============================================================
_ENABLE = os.getenv("MODEL_RPM_ENABLE", "0") == "1"
_RPM = float(os.getenv("MODEL_RPM", "60.0"))
_BURST = int(os.getenv("MODEL_BURST", str(max(1, int(_RPM / 60 * 3)))))

global_rate_limiter = TokenBucket(
    rate=_RPM,
    burst=_BURST,
    enable=_ENABLE,
    name="model_rpc",
)
