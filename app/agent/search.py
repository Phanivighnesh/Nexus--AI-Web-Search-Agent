"""
app/agent/search.py
─────────────────────────────────────────────────────────────────
Web & news search via DuckDuckGo (free, no API key required).
Supports retry logic and graceful degradation.
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.agent.models import SearchResult
from app.utils.logger import get_logger

# Support both ddgs (v7+) and the legacy duckduckgo_search package
try:
    from ddgs import DDGS
    _PKG = "ddgs"
except ImportError:
    try:
        from duckduckgo_search import DDGS  # type: ignore[no-redef]
        _PKG = "duckduckgo_search"
    except ImportError:
        DDGS = None  # type: ignore[assignment,misc]
        _PKG = "unavailable"

if TYPE_CHECKING:
    from app.config import Settings

logger = get_logger(__name__)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _safe_ddg_text(query: str, max_results: int, snippet_chars: int) -> list[SearchResult]:
    """Run a DuckDuckGo text search with basic retry on rate-limit."""
    if DDGS is None:
        logger.error("No DuckDuckGo library available — install 'ddgs'")
        return []

    for attempt in range(1, 4):  # up to 3 attempts
        try:
            results: list[SearchResult] = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href") or r.get("url", ""),
                        snippet=r.get("body", "")[:snippet_chars],
                        source="web",
                    ))
            logger.debug(f"[search] web  query={query!r}  results={len(results)}")
            return results
        except Exception as exc:
            wait = attempt * 1.5
            logger.warning(f"[search] web attempt {attempt} failed: {exc} — retrying in {wait}s")
            time.sleep(wait)

    logger.error(f"[search] web search exhausted retries for query={query!r}")
    return []


def _safe_ddg_news(query: str, max_results: int, snippet_chars: int) -> list[SearchResult]:
    """Run a DuckDuckGo news search with basic retry on rate-limit."""
    if DDGS is None:
        return []

    for attempt in range(1, 3):
        try:
            results: list[SearchResult] = []
            with DDGS() as ddgs:
                for r in ddgs.news(query, max_results=max_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url") or r.get("href", ""),
                        snippet=r.get("body", "")[:snippet_chars],
                        date=r.get("date", ""),
                        source=r.get("source", "news"),
                    ))
            logger.debug(f"[search] news query={query!r}  results={len(results)}")
            return results
        except Exception as exc:
            wait = attempt * 1.5
            logger.warning(f"[search] news attempt {attempt} failed: {exc} — retrying in {wait}s")
            time.sleep(wait)

    logger.error(f"[search] news search exhausted retries for query={query!r}")
    return []


def _dedup(results: list[SearchResult]) -> list[SearchResult]:
    """Remove duplicates by URL, preserving insertion order."""
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for r in results:
        if r.url and r.url not in seen:
            seen.add(r.url)
            unique.append(r)
    return unique


# ─── Public API ───────────────────────────────────────────────────────────────

class SearchTool:
    """
    Encapsulates all search operations.
    Injected into the agent orchestrator via dependency injection.
    """

    def __init__(self, settings: "Settings") -> None:
        self._max_web     = settings.search_max_results
        self._max_news    = settings.search_max_news
        self._snippet     = settings.search_snippet_chars
        logger.info(f"[search] using {_PKG} — web={self._max_web}, news={self._max_news}")

    def search(self, query: str, include_news: bool = True) -> list[SearchResult]:
        """
        Perform web (and optionally news) search, then deduplicate.
        News results are placed first for recency.
        """
        web   = _safe_ddg_text(query, self._max_web,  self._snippet)
        news  = _safe_ddg_news(query, self._max_news, self._snippet) if include_news else []
        combined = _dedup(news + web)
        logger.info(f"[search] total unique results: {len(combined)}")
        return combined
