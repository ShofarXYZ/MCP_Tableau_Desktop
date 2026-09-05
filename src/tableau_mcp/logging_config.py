"""Structured logging configuration.

Logs are written both to stderr (never stdout, which is reserved for the MCP
stdio transport) and to a rotating file inside the configured logs directory.
Log records are emitted as single-line JSON for easy machine parsing and never
contain data-source credentials or row-level data.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOGGER_NAME = "tableau_mcp"
_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Format log records as compact single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge structured extras attached via ``logger.info(..., extra={"context": {...}})``.
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(logs_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configure and return the package logger.

    Args:
        logs_dir: Directory where the rotating log file is stored.
        level: Logging level name (``DEBUG``/``INFO``/``WARNING``/``ERROR``).

    Returns:
        The configured package logger.
    """
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    logger.setLevel(level.upper())
    logger.propagate = False
    formatter = JsonFormatter()

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            logs_dir / "tableau_mcp.log",
            maxBytes=5_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # File logging is best-effort; stderr logging still works.
        logger.warning("Could not initialize file logging in %s", logs_dir)

    _CONFIGURED = True
    return logger


def get_logger() -> logging.Logger:
    """Return the package logger (configuring a stderr-only fallback if needed)."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel("INFO")
    return logger
