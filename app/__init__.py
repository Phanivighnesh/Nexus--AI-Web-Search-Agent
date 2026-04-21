"""
app/__init__.py  —  Flask application factory
"""
from __future__ import annotations

import os
from flask import Flask, send_from_directory

from app.config       import get_settings
from app.middleware   import init_cors, init_rate_limiter, register_error_handlers
from app.routes       import api_bp
from app.utils.logger import configure_root, get_logger
from app.utils.session_store import SessionStore


def create_app() -> Flask:
    settings = get_settings()

    configure_root(level=settings.log_level, fmt=settings.log_format)
    logger = get_logger(__name__, level=settings.log_level, fmt=settings.log_format)
    logger.info("=== NEXUS AI Web Search Agent starting ===")
    logger.info(f"model={settings.groq_model}  env={settings.flask_env}")

    static_folder = os.path.join(os.path.dirname(__file__), "..", "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="/static")
    app.secret_key = settings.flask_secret_key

    # Extensions
    init_cors(app, settings)
    init_rate_limiter(settings)
    register_error_handlers(app)

    # Agent singleton — key is optional at startup (UI key supplied per-request)
    from app.agent.orchestrator import AgentOrchestrator
    try:
        agent = AgentOrchestrator(settings)
        app.extensions["agent"] = agent
        logger.info("[app] agent initialized")
    except ValueError as exc:
        # Key missing is fine — UI key will be passed per-request
        logger.warning(f"[app] agent init without server key: {exc}")
        # Create agent with empty key — requests with UI key will work
        pass  # key check skipped in test
        from app.config import get_settings as _gs; _gs.cache_clear()
        from app.config import Settings as _S
        _patched = _S.model_construct(**{**settings.model_dump(), "groq_api_key": "__placeholder__"})
        agent = AgentOrchestrator.__new__(AgentOrchestrator)
        from app.agent.search import SearchTool
        from app.agent.llm import LLMClient
        from app.utils.cache import QueryCache
        agent._settings = _patched
        agent._search   = SearchTool(_patched)
        agent._cache    = QueryCache(maxsize=_patched.cache_max_size, ttl=_patched.cache_ttl_seconds)
        # LLMClient with placeholder — real key comes per-request
        try:
            agent._llm = LLMClient(_patched)
        except ValueError:
            agent._llm = None
        app.extensions["agent"] = agent
        logger.info("[app] agent initialized in keyless mode (UI key required per-request)")

    # Session store singleton
    store = SessionStore()
    app.extensions["session_store"] = store
    logger.info("[app] session store initialized")

    # Blueprints
    app.register_blueprint(api_bp)

    # Serve SPA — /api/* is excluded so blueprint routes are never shadowed
    @app.route("/", defaults={"path": ""}, methods=["GET", "HEAD"])
    @app.route("/<path:path>",             methods=["GET", "HEAD"])
    def serve_frontend(path: str):
        from flask import abort
        if path.startswith("api/"):
            abort(404)
        full = os.path.join(app.static_folder, path)
        if path and os.path.exists(full):
            return send_from_directory(app.static_folder, path)
        return send_from_directory(app.static_folder, "index.html")

    logger.info(f"[app] ready — http://{settings.flask_host}:{settings.flask_port}")
    return app