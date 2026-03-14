"""Sliding-window in-memory rate limiter."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from pg_mcp.errors import RateLimitError


class RateLimiter:
    """Sliding-window rate limiter enforcing a requests-per-minute cap."""

    def __init__(self, rpm: int = 60) -> None:
        self._rpm = rpm
        self._window: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Raise RateLimitError if current request would exceed the RPM limit."""
        if self._rpm <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            cutoff = now - 60.0
            while self._window and self._window[0] < cutoff:
                self._window.popleft()
            if len(self._window) >= self._rpm:
                raise RateLimitError(f"Rate limit exceeded: {self._rpm} RPM")
            self._window.append(now)
