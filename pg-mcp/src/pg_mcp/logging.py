"""Structured logging and sanitization."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import structlog


def sanitize_processor(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Redact sensitive fields; at INFO, replace SQL with hash."""
    sensitive_keys = ("password", "api_key", "token", "dsn")
    for key in sensitive_keys:
        if key in event_dict:
            event_dict[key] = "***REDACTED***"

    if "sql" in event_dict:
        log_level = event_dict.get("_log_level", "INFO")
        if log_level == "DEBUG":
            pass  # Keep SQL at DEBUG
        else:
            sql = event_dict.pop("sql", "")
            if isinstance(sql, str):
                event_dict["sql_hash"] = hashlib.sha256(sql.encode()).hexdigest()[:16]

    for key in ("rows", "result_data", "prompt"):
        event_dict.pop(key, None)

    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog with sanitization."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            sanitize_processor,
            structlog.dev.ConsoleRenderer()
            if level.upper() == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )
