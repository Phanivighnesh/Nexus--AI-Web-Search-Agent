"""
app/middleware.py
─────────────────────────────────────────────────────────────────
Flask middleware and extension setup:
  - CORS
  - Per-IP rate limiting (in-memory sliding window)
  - Global JSON error handlers (400, 404, 405, 429, 500)
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict, deque
from typing import TYPE_CHECKING

from flask import Flask, jsonify, request
from flask_cors import CORS

from app.utils.logger import get_logger

if TYPE_CHECKING:
    from app.config import Settings

logger = get_logger(__name__)


# ─── In-memory sliding-window rate limiter ────────────────────────────────────

class _RateLimiter:
    """
    Per-IP sliding-window rate limiter (in-memory).
    Thread-safe via a single lock.
    """

    def __init__(self, max_calls: int, window_secs: int = 60) -> None:
        self._max   = max_calls
        self._win   = window_secs
        self._store: dict[str, deque] = defaultdict(deque)
        self._lock  = threading.Lock()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_secs).
        retry_after_secs is 0 when allowed.
        """
        now = time.monotonic()
        cutoff = now - self._win

        with self._lock:
            window = self._store[key]
            # Evict timestamps outside the window
            while window and window[0] < cutoff:
                window.popleft()

            if len(window) >= self._max:
                retry_after = int(self._win - (now - window[0])) + 1
                return False, retry_after

            window.append(now)
            return True, 0


_limiter: _RateLimiter | None = None


# ─── Setup functions (called from app factory) ────────────────────────────────

def init_cors(app: Flask, settings: "Settings") -> None:
    CORS(app, resources={r"/api/*": {"origins": settings.cors_origins_list}})
    logger.info(f"[middleware] CORS origins={settings.cors_origins}")


def init_rate_limiter(settings: "Settings") -> None:
    global _limiter
    _limiter = _RateLimiter(
        max_calls=settings.rate_limit_per_minute,
        window_secs=60,
    )
    logger.info(f"[middleware] rate limit={settings.rate_limit_per_minute} req/min")


def apply_rate_limit() -> None:
    """
    Call before processing any API request.
    Raises a 429 response if the IP is over limit.
    """
    if _limiter is None:
        return

    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    allowed, retry_after = _limiter.is_allowed(ip)

    if not allowed:
        logger.warning(f"[middleware] rate limit exceeded for ip={ip}")
        from flask import abort
        abort(429, description=f"Too many requests. Retry after {retry_after}s.")


# ─── Global error handlers ────────────────────────────────────────────────────

def register_error_handlers(app: Flask) -> None:

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "bad_request", "message": str(e.description)}), 400

    @app.errorhandler(404)
    def not_found(e):
        # Only return JSON 404 for /api/* paths; let the SPA catch-all handle others
        if request.path.startswith("/api/"):
            return jsonify({"error": "not_found", "message": "API endpoint not found"}), 404
        # For non-API paths return 404 plainly (frontend catch-all handles this)
        return jsonify({"error": "not_found", "message": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "method_not_allowed", "message": str(e.description)}), 405

    @app.errorhandler(429)
    def too_many_requests(e):
        return jsonify({
            "error":   "rate_limit_exceeded",
            "message": str(e.description),
        }), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception(f"[middleware] unhandled 500: {e}")
        return jsonify({
            "error":   "internal_server_error",
            "message": "An unexpected error occurred. Please try again.",
        }), 500
