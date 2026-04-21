"""
app/config.py — Centralised env-driven configuration.
GROQ_API_KEY is optional here; the UI can supply it per-request
via the X-Api-Key header (stored in the user's browser localStorage).
"""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)
load_dotenv(_ROOT / ".env.local", override=True)   # local dev override


class Settings(BaseSettings):
    # ── LLM (optional — UI key takes priority if supplied) ───────
    groq_api_key: str  = Field("", description="Server-side Groq API key (optional if UI key supplied)")
    groq_model:   str  = Field("llama-3.3-70b-versatile")
    groq_max_tokens:   int   = Field(1024, ge=64, le=8192)
    groq_temperature:  float = Field(0.25, ge=0.0, le=1.0)

    # ── Search ────────────────────────────────────────────────────
    search_max_results:  int = Field(5, ge=1, le=10)
    search_max_news:     int = Field(3, ge=0, le=10)
    search_snippet_chars:int = Field(900, ge=100, le=4000)

    # ── Flask ─────────────────────────────────────────────────────
    flask_env:        str  = Field("production")
    flask_debug:      bool = Field(False)
    flask_host:       str  = Field("0.0.0.0")
    flask_port:       int  = Field(7860, ge=1, le=65535)
    flask_secret_key: str  = Field("change-me-in-production")

    # ── Rate / Cache / CORS / Logging ────────────────────────────
    rate_limit_per_minute: int  = Field(30, ge=1, le=1000)
    cache_ttl_seconds:     int  = Field(300, ge=0)
    cache_max_size:        int  = Field(200, ge=10)
    cors_origins:          str  = Field("*")
    log_level:             str  = Field("INFO")
    log_format:            str  = Field("text")

    @property
    def cors_origins_list(self):
        if self.cors_origins.strip() == "*": return "*"
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("log_level")
    @classmethod
    def _log(cls, v):
        v = v.upper()
        assert v in {"DEBUG","INFO","WARNING","ERROR","CRITICAL"}, f"bad log_level: {v}"
        return v

    @field_validator("log_format")
    @classmethod
    def _fmt(cls, v):
        assert v.lower() in {"json","text"}, f"bad log_format: {v}"
        return v.lower()

    @field_validator("flask_env")
    @classmethod
    def _env(cls, v):
        assert v.lower() in {"development","production","testing"}, f"bad flask_env: {v}"
        return v.lower()

    model_config = {
        "env_file": str(_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
