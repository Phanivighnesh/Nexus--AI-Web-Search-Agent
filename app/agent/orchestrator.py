"""
app/agent/orchestrator.py — Agent pipeline with preferences
"""
from __future__ import annotations
import time
from typing import TYPE_CHECKING
from app.agent.llm     import LLMClient
from app.agent.models  import SearchRequest, SearchResponse, SourceItem
from app.agent.search  import SearchTool
from app.utils.cache   import QueryCache
from app.utils.logger  import get_logger

if TYPE_CHECKING:
    from app.config import Settings

logger = get_logger(__name__)
APP_VERSION = "2.0.0"


class AgentOrchestrator:
    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._search   = SearchTool(settings)
        self._llm      = LLMClient(settings)
        self._cache    = QueryCache(maxsize=settings.cache_max_size, ttl=settings.cache_ttl_seconds)
        logger.info("[orchestrator] ready")

    def run(self, request: SearchRequest, api_key: str = "") -> SearchResponse:
        t0 = time.perf_counter()

        # Cache key includes tone + model so different prefs get different answers
        prefs    = request.preferences
        cache_ns = f"{prefs.tone}|{prefs.model}|{prefs.language}"

        cached = self._cache.get(request.query + cache_ns, request.include_news)
        if cached is not None:
            logger.info(f"[orchestrator] cache HIT query={request.query!r}")
            cached.cached = True
            return cached

        logger.info(f"[orchestrator] pipeline query={request.query!r} tone={prefs.tone} model={prefs.model or 'default'}")

        results = self._search.search(request.query, request.include_news)

        # If LLMClient was not initialised at startup (keyless mode), build one on-the-fly
        # using the per-request UI key passed via X-Api-Key header.
        llm = self._llm
        if llm is None:
            if not api_key:
                raise RuntimeError(
                    "No API key available. Add your Groq key in Settings."
                )
            from app.agent.llm import LLMClient
            from app.config import get_settings
            from pydantic_settings import BaseSettings
            # Build a minimal settings clone with the UI key injected
            s = get_settings()
            from app.config import Settings
            tmp = Settings.model_construct(**{**s.model_dump(), "groq_api_key": api_key})
            llm = LLMClient(tmp)

        answer, model_used = llm.generate(request.query, results[:self._settings.search_max_results], prefs, api_key=api_key)

        sources = [
            SourceItem(title=r.title or r.domain or r.url, url=r.url,
                       domain=r.domain, date=r.date, source=r.source)
            for r in results[:self._settings.search_max_results] if r.url
        ]

        elapsed = round(time.perf_counter() - t0, 3)
        logger.info(f"[orchestrator] done in {elapsed}s sources={len(sources)}")

        response = SearchResponse(
            query=request.query, answer=answer, sources=sources,
            model=model_used, time_taken=elapsed, cached=False, result_count=len(results),
        )
        self._cache.set(request.query + cache_ns, request.include_news, response)
        return response

    @property
    def cache(self) -> QueryCache:   return self._cache
    @property
    def model(self) -> str:          return self._llm.model
    @property
    def version(self) -> str:        return APP_VERSION