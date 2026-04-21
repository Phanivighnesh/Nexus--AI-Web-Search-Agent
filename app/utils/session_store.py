"""
app/utils/session_store.py — In-memory session store with preferences
"""
from __future__ import annotations
import threading, time, uuid
from dataclasses import dataclass, field
from typing import Optional
from app.utils.logger import get_logger

logger = get_logger(__name__)
SESSION_TTL    = 7200
MAX_CONVS      = 50
MAX_MSGS       = 100

DEFAULT_PREFS = {
    "name":            "",
    "tone":            "balanced",
    "language":        "English",
    "model":           "",          # empty = use env default
    "news_categories": [],
}


@dataclass
class Message:
    role:       str
    content:    str
    sources:    list[dict] = field(default_factory=list)
    time_taken: float      = 0.0
    cached:     bool       = False
    model:      str        = ""
    timestamp:  float      = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"role":self.role,"content":self.content,"sources":self.sources,
                "time_taken":self.time_taken,"cached":self.cached,"model":self.model,"timestamp":self.timestamp}


@dataclass
class Conversation:
    id:       str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title:    str   = "New Chat"
    messages: list  = field(default_factory=list)
    created:  float = field(default_factory=time.time)
    updated:  float = field(default_factory=time.time)

    def add_message(self, msg: Message) -> None:
        self.messages.append(msg)
        self.updated = time.time()
        if len(self.messages) == 1 and msg.role == "user":
            self.title = msg.content[:60] + ("…" if len(msg.content) > 60 else "")
        if len(self.messages) > MAX_MSGS:
            self.messages = self.messages[-MAX_MSGS:]

    def to_dict(self) -> dict:
        return {"id":self.id,"title":self.title,"messages":[m.to_dict() for m in self.messages],
                "created":self.created,"updated":self.updated}

    def to_summary(self) -> dict:
        return {"id":self.id,"title":self.title,"message_count":len(self.messages),
                "created":self.created,"updated":self.updated}


@dataclass
class Session:
    id:            str            = field(default_factory=lambda: str(uuid.uuid4()))
    conversations: dict           = field(default_factory=dict)
    active_id:     Optional[str]  = None
    last_active:   float          = field(default_factory=time.time)
    preferences:   dict           = field(default_factory=lambda: dict(DEFAULT_PREFS))

    def touch(self): self.last_active = time.time()
    def is_expired(self): return (time.time() - self.last_active) > SESSION_TTL

    def update_preferences(self, updates: dict) -> None:
        allowed = set(DEFAULT_PREFS.keys())
        for k, v in updates.items():
            if k in allowed:
                self.preferences[k] = v

    def new_conversation(self) -> Conversation:
        conv = Conversation()
        self.conversations[conv.id] = conv
        self.active_id = conv.id
        self.touch()
        if len(self.conversations) > MAX_CONVS:
            oldest = sorted(self.conversations.values(), key=lambda c: c.updated)[0]
            del self.conversations[oldest.id]
        return conv

    def get_conversation(self, cid: str) -> Optional[Conversation]:
        return self.conversations.get(cid)

    def delete_conversation(self, cid: str) -> bool:
        if cid not in self.conversations: return False
        del self.conversations[cid]
        if self.active_id == cid:
            rem = sorted(self.conversations.values(), key=lambda c: c.updated, reverse=True)
            self.active_id = rem[0].id if rem else None
        return True

    def list_conversations(self) -> list:
        return [c.to_summary() for c in sorted(self.conversations.values(), key=lambda c: c.updated, reverse=True)]


class SessionStore:
    def __init__(self):
        self._store: dict[str, Session] = {}
        self._lock  = threading.Lock()
        self._start_cleanup()
        logger.info("[session_store] initialized")

    def get_or_create(self, sid: Optional[str]) -> Session:
        with self._lock:
            if sid and sid in self._store:
                s = self._store[sid]; s.touch(); return s
            s = Session()
            self._store[s.id] = s
            logger.info(f"[session_store] new session id={s.id}")
            return s

    def get(self, sid: str) -> Optional[Session]:
        with self._lock:
            s = self._store.get(sid)
            if s: s.touch()
            return s

    @property
    def active_count(self) -> int:
        with self._lock: return len(self._store)

    def _cleanup(self):
        with self._lock:
            expired = [k for k,v in self._store.items() if v.is_expired()]
            for k in expired: del self._store[k]
            if expired: logger.info(f"[session_store] removed {len(expired)} expired sessions")

    def _start_cleanup(self):
        def loop():
            while True:
                time.sleep(300)
                try: self._cleanup()
                except Exception as e: logger.error(f"cleanup error: {e}")
        threading.Thread(target=loop, daemon=True).start()
