"""In-memory chat session management."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ChatSession:
    """A single chat session with message history."""

    session_id: str
    messages: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    MAX_MESSAGES = 20

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.last_active = time.time()
        if len(self.messages) > self.MAX_MESSAGES:
            # Keep system message if present, trim oldest
            if self.messages and self.messages[0].get("role") == "system":
                self.messages = [self.messages[0]] + self.messages[-(self.MAX_MESSAGES - 1) :]
            else:
                self.messages = self.messages[-self.MAX_MESSAGES :]

    def get_history(self) -> list[dict]:
        """Return last 6 user/assistant messages for context."""
        hist = [m for m in self.messages if m["role"] in ("user", "assistant")]
        return hist[-6:]


class SessionManager:
    """Manage chat sessions with TTL and eviction."""

    TTL_SECONDS = 1800  # 30 minutes
    MAX_SESSIONS = 50

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}

    def get_or_create(self, session_id: str) -> ChatSession:
        self._cleanup_expired()
        if session_id not in self._sessions:
            if len(self._sessions) >= self.MAX_SESSIONS:
                oldest = min(self._sessions.values(), key=lambda s: s.last_active)
                del self._sessions[oldest.session_id]
            self._sessions[session_id] = ChatSession(session_id=session_id)
        session = self._sessions[session_id]
        session.last_active = time.time()
        return session

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_active > self.TTL_SECONDS]
        for sid in expired:
            del self._sessions[sid]
