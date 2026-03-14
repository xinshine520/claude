"""Tests for the sliding-window rate limiter (Phase 10)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pg_mcp.errors import RateLimitError
from pg_mcp.middleware.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_within_limit_succeeds():
    """Requests within RPM limit all succeed."""
    limiter = RateLimiter(rpm=5)
    for _ in range(5):
        await limiter.acquire()  # should not raise


@pytest.mark.asyncio
async def test_exceeds_limit_raises():
    """N+1 requests within 1-minute window raises RateLimitError."""
    limiter = RateLimiter(rpm=3)
    with patch("pg_mcp.middleware.rate_limiter.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()
        with pytest.raises(RateLimitError) as exc:
            await limiter.acquire()
    assert "rate limit exceeded" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_window_slides_allows_new_requests():
    """After the 60-second window passes, new requests are allowed."""
    limiter = RateLimiter(rpm=2)
    with patch("pg_mcp.middleware.rate_limiter.time") as mock_time:
        mock_time.monotonic.return_value = 0.0
        await limiter.acquire()
        await limiter.acquire()

        # Window not yet expired → next call raises
        with pytest.raises(RateLimitError):
            await limiter.acquire()

        # Advance time past 60 seconds
        mock_time.monotonic.return_value = 61.0
        await limiter.acquire()  # old timestamps evicted → succeeds


@pytest.mark.asyncio
async def test_rpm_zero_disables_limiting():
    """rpm=0 disables rate limiting entirely."""
    limiter = RateLimiter(rpm=0)
    for _ in range(1000):
        await limiter.acquire()  # should never raise


@pytest.mark.asyncio
async def test_negative_rpm_disables_limiting():
    """Negative rpm disables rate limiting."""
    limiter = RateLimiter(rpm=-1)
    for _ in range(100):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_rate_limiter_error_message_includes_limit():
    """RateLimitError message includes the configured RPM."""
    limiter = RateLimiter(rpm=1)
    await limiter.acquire()
    with pytest.raises(RateLimitError) as exc:
        await limiter.acquire()
    assert "1" in str(exc.value)
