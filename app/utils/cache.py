"""
app/utils/cache.py
─────────────────────────────────────────────────────────────────
Thread-safe in-memory query cache with TTL expiry.
Uses cachetools.TTLCache under the hood.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import hashlib
import threading
from typing import Any

from cachetools import TTLCache


class QueryCache:
    """
    Thread-safe wrapper around TTLCache for caching agent responses.

    Keys are derived from the (query, include_news) tuple.
    Disabled automatically when ttl=0.
    """

    def __init__(self, maxsize: int = 200, ttl: int = 300) -> None:
        self._enabled = ttl > 0
        self._lock    = threading.Lock()
        if self._enabled:
            self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _key(query: str, include_news: bool) -> str:
        raw = f"{query.strip().lower()}|{include_news}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    # ── Public API ────────────────────────────────────────────────

    def get(self, query: str, include_news: bool) -> Any | None:
        if not self._enabled:
            return None
        key = self._key(query, include_news)
        with self._lock:
            return self._store.get(key)

    def set(self, query: str, include_news: bool, value: Any) -> None:
        if not self._enabled:
            return
        key = self._key(query, include_news)
        with self._lock:
            self._store[key] = value

    def invalidate(self, query: str, include_news: bool) -> None:
        if not self._enabled:
            return
        key = self._key(query, include_news)
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._store.clear()

    @property
    def stats(self) -> dict:
        if not self._enabled:
            return {"enabled": False}
        with self._lock:
            return {
                "enabled":  True,
                "size":     len(self._store),
                "maxsize":  self._store.maxsize,
                "ttl":      self._store.ttl,
            }
