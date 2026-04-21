"""
app/agent/models.py — Pydantic v2 data models
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class UserPreferences(BaseModel):
    """User personalisation settings sent with each request."""
    tone: str             = Field("balanced",   description="Response tone: formal | casual | concise | detailed | balanced")
    name: str             = Field("",           description="User's display name")
    language: str         = Field("English",    description="Preferred response language")
    news_categories: list[str] = Field(default_factory=list, description="Preferred news topics")
    model: str            = Field("",           description="Override LLM model (empty = use .env default)")

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        allowed = {"formal", "casual", "concise", "detailed", "balanced"}
        if v not in allowed:
            raise ValueError(f"tone must be one of {allowed}")
        return v


class SearchResult(BaseModel):
    title:   str = Field(default="")
    url:     str = Field(default="")
    snippet: str = Field(default="")
    date:    str = Field(default="")
    source:  str = Field(default="web")

    @property
    def domain(self) -> str:
        try:    return self.url.split("/")[2]
        except: return ""


class SourceItem(BaseModel):
    title:  str = Field(default="")
    url:    str = Field(default="")
    domain: str = Field(default="")
    date:   str = Field(default="")
    source: str = Field(default="web")


class SearchRequest(BaseModel):
    query:        str             = Field(..., min_length=1, max_length=512)
    include_news: bool            = Field(True)
    preferences:  UserPreferences = Field(default_factory=UserPreferences)

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("query must not be empty")
        return s


class SearchResponse(BaseModel):
    query:        str              = ""
    answer:       str              = ""
    sources:      list[SourceItem] = Field(default_factory=list)
    model:        str              = ""
    time_taken:   float            = 0.0
    cached:       bool             = False
    result_count: int              = 0


class HealthResponse(BaseModel):
    status:          str  = "ok"
    version:         str  = ""
    model:           str  = ""
    search:          str  = ""
    cache_stats:     dict = Field(default_factory=dict)
    groq_key_set:    bool = False
    active_sessions: int  = 0
