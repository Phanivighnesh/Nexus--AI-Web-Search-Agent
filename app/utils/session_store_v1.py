"""
app/utils/session_store.py
─────────────────────────────────────────────────────────────────
In-memory session store for multi-chat support.
Each session holds a list of conversations; each conversation
holds an ordered list of messages (user query + agent response).
─────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Session TTL: 2 hours of inactivity
SESSION_TTL = 7200
# Max conversations per session
MAX_CONVERSATIONS = 50
# Max messages per conversation
MAX_MESSAGES = 100


@dataclass
class Message:
    role: str           # "user" | "assistant"
    content: str
    sources: list[dict] = field(default_factory=list)
    time_taken: float   = 0.0
    cached: bool        = False
    timestamp: float    = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "role":       self.role,
            "content":    self.content,
            "sources":    self.sources,
            "time_taken": self.time_taken,
            "cached":     self.cached,
            "timestamp":  self.timestamp,
        }


@dataclass
class Conversation:
    id:       str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:    str = "New Chat"
    messages: list[Message] = field(default_factory=list)
    created:  float = field(default_factory=time.time)
    updated:  float = field(default_factory=time.time)

    def add_message(self, msg: Message) -> None:
        self.messages.append(msg)
        self.updated = time.time()
        # Auto-title from first user message
        if len(self.messages) == 1 and msg.role == "user":
            self.title = msg.content[:60] + ("…" if len(msg.content) > 60 else "")
        # Keep within max
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]

    def to_dict(self) -> dict:
        return {
            "id":       self.id,
            "title":    self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created":  self.created,
            "updated":  self.updated,
        }

    def to_summary(self) -> dict:
        """Lightweight dict for sidebar listing (no messages)."""
        return {
            "id":           self.id,
            "title":        self.title,
            "message_count": len(self.messages),
            "created":      self.created,
            "updated":      self.updated,
        }


@dataclass
class Session:
    id:            str = field(default_factory=lambda: str(uuid.uuid4()))
    conversations: dict[str, Conversation] = field(default_factory=dict)
    active_id:     Optional[str] = None
    last_active:   float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_active = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > SESSION_TTL

    def new_conversation(self) -> Conversation:
        conv = Conversation()
        self.conversations[conv.id] = conv
        self.active_id = conv.id
        self.touch()
        # Trim old conversations
        if len(self.conversations) > MAX_CONVERSATIONS:
            oldest = sorted(self.conversations.values(), key=lambda c: c.updated)[0]
            del self.conversations[oldest.id]
        return conv

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        return self.conversations.get(conv_id)

    def delete_conversation(self, conv_id: str) -> bool:
        if conv_id in self.conversations:
            del self.conversations[conv_id]
            if self.active_id == conv_id:
                remaining = sorted(self.conversations.values(), key=lambda c: c.updated, reverse=True)
                self.active_id = remaining[0].id if remaining else None
            return True
        return False

    def list_conversations(self) -> list[dict]:
        return [
            c.to_summary()
            for c in sorted(self.conversations.values(), key=lambda c: c.updated, reverse=True)
        ]


class SessionStore:
    """
    Thread-safe in-memory store for all active sessions.
    Sessions expire after SESSION_TTL seconds of inactivity.
    A background cleanup thread removes expired sessions.
    """

    def __init__(self) -> None:
        self._store: dict[str, Session] = {}
        self._lock  = threading.Lock()
        self._start_cleanup_thread()
        logger.info("[session_store] initialized")

    # ── Session lifecycle ─────────────────────────────────────────

    def get_or_create(self, session_id: Optional[str]) -> Session:
        with self._lock:
            if session_id and session_id in self._store:
                session = self._store[session_id]
                session.touch()
                return session
            session = Session()
            self._store[session.id] = session
            logger.info(f"[session_store] new session id={session.id}")
            return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            s = self._store.get(session_id)
            if s:
                s.touch()
            return s

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._store)

    # ── Cleanup ───────────────────────────────────────────────────

    def _cleanup(self) -> None:
        with self._lock:
            expired = [sid for sid, s in self._store.items() if s.is_expired()]
            for sid in expired:
                del self._store[sid]
            if expired:
                logger.info(f"[session_store] cleaned up {len(expired)} expired sessions")

    def _start_cleanup_thread(self) -> None:
        def loop():
            while True:
                time.sleep(300)  # run every 5 minutes
                try:
                    self._cleanup()
                except Exception as e:
                    logger.error(f"[session_store] cleanup error: {e}")
        t = threading.Thread(target=loop, daemon=True)
        t.start()
