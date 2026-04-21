"""
app/utils/logger.py
─────────────────────────────────────────────────────────────────
Structured logging with support for both text and JSON formats.
Provides a single get_logger() factory used throughout the app.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """Coloured, human-readable log lines for development."""

    _COLOURS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        ts     = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        level  = f"{colour}{record.levelname:<8}{self._RESET}"
        name   = f"\033[2m{record.name}\033[0m"
        return f"{ts} {level} {name}  {record.getMessage()}"


_configured: set[str] = set()


def get_logger(name: str, *, level: str = "INFO", fmt: str = "text") -> logging.Logger:
    """
    Return (and lazily configure) a named logger.

    Args:
        name:  Module name, typically __name__.
        level: Log level string — DEBUG | INFO | WARNING | ERROR.
        fmt:   Output format — 'text' (coloured) or 'json'.
    """
    logger = logging.getLogger(name)

    if name not in _configured:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter() if fmt == "json" else _TextFormatter())
        logger.addHandler(handler)
        logger.propagate = False

        _configured.add(name)

    return logger


def configure_root(level: str = "INFO", fmt: str = "text") -> None:
    """Configure the root logger (called once from app factory)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter() if fmt == "json" else _TextFormatter())
        root.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ("werkzeug", "urllib3", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
