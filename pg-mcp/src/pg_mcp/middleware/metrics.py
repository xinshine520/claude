"""Structured metrics collection for pipeline stages."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog

logger = structlog.get_logger()


class MetricsCollector:
    """Accumulates counters and durations, emits via structlog."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._counters: dict[str, int] = defaultdict(int)
        self._durations: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def increment(self, name: str, **tags: Any) -> None:
        """Increment a named counter."""
        if not self._enabled:
            return
        async with self._lock:
            key = name
            if tags:
                key = f"{name}[{','.join(f'{k}={v}' for k, v in sorted(tags.items()))}]"
            self._counters[key] += 1

    async def record_duration(self, name: str, duration: float, **tags: Any) -> None:
        """Record a duration sample for a named stage."""
        if not self._enabled:
            return
        async with self._lock:
            key = name
            if tags:
                key = f"{name}[{','.join(f'{k}={v}' for k, v in sorted(tags.items()))}]"
            self._durations[key].append(duration)

    def emit(self) -> None:
        """Emit accumulated metrics via structlog and reset."""
        if not self._enabled:
            return
        avg_durations = {
            k: (sum(v) / len(v)) if v else 0.0
            for k, v in self._durations.items()
        }
        logger.info(
            "pipeline_metrics",
            counters=dict(self._counters),
            avg_durations_s=avg_durations,
        )
        self._counters.clear()
        self._durations.clear()


@asynccontextmanager
async def timed(
    collector: MetricsCollector | None,
    stage_name: str,
    **tags: Any,
) -> AsyncIterator[None]:
    """Async context manager that records stage duration into collector."""
    if collector is None or not collector._enabled:
        yield
        return

    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        await collector.record_duration(stage_name, duration, **tags)
