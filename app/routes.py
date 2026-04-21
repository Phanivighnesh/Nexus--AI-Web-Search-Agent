"""
app/routes.py — Session-aware routes with per-request API key support.

Key resolution order:
  1. X-Api-Key request header  (user's browser-stored key)
  2. GROQ_API_KEY env variable  (server-side / Vercel env)
  3. Missing → 401 with friendly message
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request, current_app, make_response
from pydantic import ValidationError
from app.agent.models        import SearchRequest, UserPreferences
from app.agent.orchestrator  import APP_VERSION
from app.middleware          import apply_rate_limit
from app.utils.logger        import get_logger
from app.utils.session_store import Message

logger = get_logger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")
COOKIE  = "nxs_session"
MAX_AGE = 7200

AVAILABLE_MODELS = [
    {"id":"llama-3.3-70b-versatile",                   "label":"Llama 3.3 · 70B",    "badge":"Best"},
    {"id":"llama-3.1-8b-instant",                      "label":"Llama 3.1 · 8B",     "badge":"Fast"},
    {"id":"meta-llama/llama-4-scout-17b-16e-instruct", "label":"Llama 4 Scout · 17B","badge":"New"},
    {"id":"qwen/qwen3-32b",                            "label":"Qwen 3 · 32B",        "badge":""},
    {"id":"openai/gpt-oss-120b",                       "label":"GPT-OSS · 120B",      "badge":"Large"},
    {"id":"openai/gpt-oss-20b",                        "label":"GPT-OSS · 20B",       "badge":""},
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _agent(): return current_app.extensions["agent"]
def _store(): return current_app.extensions["session_store"]

def _get_session():
    return _store().get_or_create(request.cookies.get(COOKIE))

def _cookie(resp, sid):
    resp.set_cookie(COOKIE, sid, max_age=MAX_AGE, httponly=True, samesite="Lax", secure=False)
    return resp

def _resolve_api_key() -> str:
    """
    Resolve Groq API key with priority:
      1. X-Api-Key request header  (user's browser localStorage key)
      2. GROQ_API_KEY env variable  (server / Vercel)
    Returns empty string if neither is available.
    """
    header_key = (request.headers.get("X-Api-Key") or "").strip()
    if header_key:
        return header_key
    from app.config import get_settings
    return get_settings().groq_api_key

def _require_key():
    """Return resolved key or abort with 401."""
    key = _resolve_api_key()
    if not key or key.startswith("gsk_your"):
        return None, (jsonify({
            "error":   "api_key_missing",
            "message": "No Groq API key found. Add your key in Settings (it stays in your browser).",
            "code":    "NO_KEY",
        }), 401)
    return key, None

# ── Key validation ─────────────────────────────────────────────────────────────

@api_bp.route("/validate-key", methods=["POST"])
def validate_key():
    """
    Test a Groq API key by making a minimal completion request.
    The key is NOT stored server-side — only used for this test.
    """
    body = request.get_json(silent=True) or {}
    key  = (body.get("api_key") or "").strip()
    if not key:
        return jsonify({"valid": False, "message": "No key provided"}), 400

    try:
        from groq import Groq
        client = Groq(api_key=key)
        client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":"hi"}],
            max_tokens=3,
        )
        return jsonify({"valid": True, "message": "Key is valid ✓"}), 200
    except Exception as exc:
        msg = str(exc)
        friendly = "Invalid API key." if "auth" in msg.lower() or "401" in msg else f"Connection error: {msg[:120]}"
        return jsonify({"valid": False, "message": friendly}), 200

# ── Preferences ────────────────────────────────────────────────────────────────

@api_bp.route("/preferences", methods=["GET"])
def get_preferences():
    s = _get_session()
    r = make_response(jsonify({"preferences": s.preferences}))
    return _cookie(r, s.id)

@api_bp.route("/preferences", methods=["PATCH"])
def update_preferences():
    s    = _get_session()
    body = request.get_json(silent=True) or {}
    s.update_preferences(body)
    r = make_response(jsonify({"preferences": s.preferences}))
    return _cookie(r, s.id)

# ── Session ────────────────────────────────────────────────────────────────────

@api_bp.route("/session", methods=["GET"])
def get_session_route():
    s = _get_session()
    has_server_key = bool(get_settings_key())
    r = make_response(jsonify({
        "session_id":      s.id,
        "active_conv_id":  s.active_id,
        "conversations":   s.list_conversations(),
        "preferences":     s.preferences,
        "has_server_key":  has_server_key,
    }))
    return _cookie(r, s.id)

def get_settings_key():
    from app.config import get_settings
    k = get_settings().groq_api_key
    return k if k and not k.startswith("gsk_your") else ""

# ── Conversations ──────────────────────────────────────────────────────────────

@api_bp.route("/conversations", methods=["POST"])
def new_conversation():
    s = _get_session()
    c = s.new_conversation()
    r = make_response(jsonify({"conversation": c.to_summary(), "active_conv_id": s.active_id}))
    return _cookie(r, s.id)

@api_bp.route("/conversations/<cid>", methods=["GET"])
def get_conversation(cid):
    s = _get_session()
    c = s.get_conversation(cid)
    if not c: return jsonify({"error":"not_found","message":"Conversation not found"}), 404
    s.active_id = cid
    r = make_response(jsonify({"conversation": c.to_dict()}))
    return _cookie(r, s.id)

@api_bp.route("/conversations/<cid>", methods=["DELETE"])
def delete_conversation(cid):
    s = _get_session()
    if not s.delete_conversation(cid):
        return jsonify({"error":"not_found","message":"Conversation not found"}), 404
    r = make_response(jsonify({"message":"Deleted","active_conv_id":s.active_id,"conversations":s.list_conversations()}))
    return _cookie(r, s.id)

@api_bp.route("/conversations/<cid>/rename", methods=["PATCH"])
def rename_conversation(cid):
    s = _get_session()
    c = s.get_conversation(cid)
    if not c: return jsonify({"error":"not_found","message":"Conversation not found"}), 404
    body  = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title: return jsonify({"error":"validation_error","message":"title required"}), 422
    c.title = title[:80]
    r = make_response(jsonify({"conversation": c.to_summary()}))
    return _cookie(r, s.id)

# ── Search ─────────────────────────────────────────────────────────────────────

@api_bp.route("/search", methods=["POST"])
def search():
    apply_rate_limit()
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error":"invalid_json","message":"Request body must be valid JSON"}), 400

    # Resolve key — UI key header takes priority over env
    api_key, err = _require_key()
    if err: return err

    s = _get_session()

    merged = dict(s.preferences)
    req_prefs = body.get("preferences", {})
    if req_prefs:
        merged.update({k:v for k,v in req_prefs.items() if k in merged})
    if not merged.get("model"):
        merged["model"] = s.preferences.get("model", "")

    try:
        prefs = UserPreferences(**merged)
    except ValidationError as exc:
        return jsonify({"error":"validation_error","message":str(exc.errors()[0].get("msg",""))}), 422

    try:
        req = SearchRequest(
            query=body.get("query",""),
            include_news=body.get("include_news", True),
            preferences=prefs,
        )
    except ValidationError as exc:
        errors = exc.errors(); first = errors[0]
        field  = ".".join(str(l) for l in first.get("loc",[]))
        return jsonify({"error":"validation_error","message":f"{field}: {first.get('msg','')}"}), 422

    cid  = body.get("conv_id")
    conv = s.get_conversation(cid) if cid else None
    if not conv: conv = s.new_conversation()
    s.active_id = conv.id

    conv.add_message(Message(role="user", content=req.query))

    # Pass api_key to agent — it will use this instead of the env default
    try:
        result = _agent().run(req, api_key=api_key)
    except Exception as exc:
        # Catch ALL exceptions — RuntimeError from LLM, unexpected bugs, etc.
        # Always return a clean JSON 502, never a raw 500
        err_msg = str(exc)
        logger.error(f"[routes] agent error: {err_msg}")
        conv.add_message(Message(role="assistant", content=f"⚠️ {err_msg}"))
        r = make_response(jsonify({"error":"agent_error","message":err_msg,"conv_id":conv.id}), 502)
        return _cookie(r, s.id)

    srcs = [src.model_dump() for src in result.sources]
    conv.add_message(Message(role="assistant", content=result.answer, sources=srcs,
                             time_taken=result.time_taken, cached=result.cached, model=result.model))

    r = make_response(jsonify({
        "query":result.query,"answer":result.answer,"sources":srcs,
        "model":result.model,"time_taken":result.time_taken,"cached":result.cached,
        "result_count":result.result_count,"conv_id":conv.id,"conv_title":conv.title,
    }))
    return _cookie(r, s.id)

# ── Models / Health / Info / Cache ────────────────────────────────────────────

@api_bp.route("/models", methods=["GET"])
def list_models():
    from app.config import get_settings
    default = get_settings().groq_model
    s       = _get_session()
    current = s.preferences.get("model") or default
    models  = [dict(m, selected=(m["id"]==current)) for m in AVAILABLE_MODELS]
    r = make_response(jsonify({"models":models,"default":default,"current":current}))
    return _cookie(r, s.id)

@api_bp.route("/health", methods=["GET"])
def health():
    from app.config import get_settings
    cfg = get_settings(); a = _agent()
    return jsonify({
        "status":          "ok",
        "version":         APP_VERSION,
        "model":           a.model,
        "search":          "DuckDuckGo",
        "cache_stats":     a.cache.stats,
        "active_sessions": _store().active_count,
        "has_server_key":  bool(cfg.groq_api_key and not cfg.groq_api_key.startswith("gsk_your")),
    }), 200

@api_bp.route("/info", methods=["GET"])
def info():
    from app.config import get_settings
    cfg = get_settings()
    return jsonify({"name":"NEXUS AI Web Search Agent","version":APP_VERSION,
                    "model":cfg.groq_model,"search":"DuckDuckGo",
                    "max_results":cfg.search_max_results}), 200

@api_bp.route("/cache", methods=["DELETE"])
def clear_cache():
    _agent().cache.clear()
    return jsonify({"message":"Cache cleared"}), 200