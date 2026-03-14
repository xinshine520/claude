"""Tests for MetricsCollector and timed context manager (Phase 10)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pg_mcp.middleware.metrics import MetricsCollector, timed


@pytest.mark.asyncio
async def test_increment_accumulates():
    """increment() accumulates counter values."""
    m = MetricsCollector(enabled=True)
    await m.increment("queries")
    await m.increment("queries")
    await m.increment("errors")
    assert m._counters["queries"] == 2
    assert m._counters["errors"] == 1


@pytest.mark.asyncio
async def test_record_duration_accumulates():
    """record_duration() accumulates duration samples."""
    m = MetricsCollector(enabled=True)
    await m.record_duration("stage_a", 0.5)
    await m.record_duration("stage_a", 1.5)
    await m.record_duration("stage_b", 0.2)
    assert m._durations["stage_a"] == [0.5, 1.5]
    assert m._durations["stage_b"] == [0.2]


@pytest.mark.asyncio
async def test_disabled_collector_ignores_calls():
    """Disabled collector does not accumulate anything."""
    m = MetricsCollector(enabled=False)
    await m.increment("queries")
    await m.record_duration("stage", 1.0)
    assert len(m._counters) == 0
    assert len(m._durations) == 0


@pytest.mark.asyncio
async def test_emit_logs_via_structlog():
    """emit() calls structlog with counters and avg_durations."""
    m = MetricsCollector(enabled=True)
    await m.increment("queries")
    await m.record_duration("execute_sql", 0.4)
    await m.record_duration("execute_sql", 0.6)

    with patch("pg_mcp.middleware.metrics.logger") as mock_logger:
        m.emit()

    mock_logger.info.assert_called_once()
    call_kwargs = mock_logger.info.call_args
    event_name = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("event", "")
    assert event_name == "pipeline_metrics"

    # Check keyword args
    kwargs = call_kwargs[1] if call_kwargs[1] else {}
    assert "counters" in kwargs
    assert "avg_durations_s" in kwargs
    assert kwargs["counters"]["queries"] == 1
    assert abs(kwargs["avg_durations_s"]["execute_sql"] - 0.5) < 1e-9


@pytest.mark.asyncio
async def test_emit_resets_state():
    """emit() clears counters and durations."""
    m = MetricsCollector(enabled=True)
    await m.increment("x")
    await m.record_duration("y", 1.0)
    with patch("pg_mcp.middleware.metrics.logger"):
        m.emit()
    assert len(m._counters) == 0
    assert len(m._durations) == 0


@pytest.mark.asyncio
async def test_emit_noop_when_disabled():
    """emit() does nothing when disabled."""
    m = MetricsCollector(enabled=False)
    with patch("pg_mcp.middleware.metrics.logger") as mock_logger:
        m.emit()
    mock_logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_timed_records_duration():
    """timed() context manager records elapsed duration."""
    m = MetricsCollector(enabled=True)

    with patch("pg_mcp.middleware.metrics.time") as mock_time:
        mock_time.monotonic.side_effect = [0.0, 0.3]
        async with timed(m, "my_stage"):
            pass

    assert "my_stage" in m._durations
    assert abs(m._durations["my_stage"][0] - 0.3) < 1e-9


@pytest.mark.asyncio
async def test_timed_none_collector_is_noop():
    """timed() with None collector does not raise."""
    async with timed(None, "stage"):
        pass  # no error


@pytest.mark.asyncio
async def test_timed_disabled_collector_is_noop():
    """timed() with disabled collector does not record."""
    m = MetricsCollector(enabled=False)
    async with timed(m, "stage"):
        pass
    assert len(m._durations) == 0


@pytest.mark.asyncio
async def test_increment_with_tags():
    """increment() with tags creates tagged key."""
    m = MetricsCollector(enabled=True)
    await m.increment("requests", db="mydb", status="ok")
    # Key should contain tag information
    assert any("requests" in k for k in m._counters)


@pytest.mark.asyncio
async def test_record_duration_with_tags():
    """record_duration() with tags creates tagged key."""
    m = MetricsCollector(enabled=True)
    await m.record_duration("query", 0.1, db="mydb")
    assert any("query" in k for k in m._durations)
