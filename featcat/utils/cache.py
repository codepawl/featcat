"""LLM response caching with SQLite backend."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

CACHE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash TEXT PRIMARY KEY,
    prompt_preview TEXT,
    response TEXT NOT NULL,
    created_at REAL NOT NULL,
    ttl_seconds INTEGER NOT NULL
);
"""


class ResponseCache:
    """SQLite-backed cache for LLM responses."""

    def __init__(self, db_path: str = "catalog.db") -> None:
        self.conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.execute(CACHE_SCHEMA)
        self.conn.commit()

    def get(self, prompt: str, system: Optional[str] = None) -> Optional[str]:
        """Look up a cached response. Returns None if missing or expired."""
        key = self._hash(prompt, system)
        row = self.conn.execute(
            "SELECT response, created_at, ttl_seconds FROM llm_cache WHERE prompt_hash = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None

        response, created_at, ttl = row
        if time.time() - created_at > ttl:
            # Expired — delete and return None
            self.conn.execute("DELETE FROM llm_cache WHERE prompt_hash = ?", (key,))
            self.conn.commit()
            return None

        return response

    def put(
        self,
        prompt: str,
        response: str,
        ttl_seconds: int,
        system: Optional[str] = None,
    ) -> None:
        """Store a response in the cache."""
        key = self._hash(prompt, system)
        preview = prompt[:100]
        self.conn.execute(
            """INSERT OR REPLACE INTO llm_cache
               (prompt_hash, prompt_preview, response, created_at, ttl_seconds)
               VALUES (?, ?, ?, ?, ?)""",
            (key, preview, response, time.time(), ttl_seconds),
        )
        self.conn.commit()

    def clear(self) -> int:
        """Remove all cached entries. Returns count of deleted rows."""
        cursor = self.conn.execute("DELETE FROM llm_cache")
        self.conn.commit()
        return cursor.rowcount

    def clear_expired(self) -> int:
        """Remove only expired entries."""
        now = time.time()
        cursor = self.conn.execute(
            "DELETE FROM llm_cache WHERE (? - created_at) > ttl_seconds",
            (now,),
        )
        self.conn.commit()
        return cursor.rowcount

    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]
        now = time.time()
        expired = self.conn.execute(
            "SELECT COUNT(*) FROM llm_cache WHERE (? - created_at) > ttl_seconds",
            (now,),
        ).fetchone()[0]
        return {"total": total, "active": total - expired, "expired": expired}

    def close(self) -> None:
        self.conn.close()

    @staticmethod
    def _hash(prompt: str, system: Optional[str] = None) -> str:
        content = f"{system or ''}|||{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()


# TTL constants (seconds)
TTL_AUTODOC = 7 * 24 * 3600  # 7 days
TTL_NL_QUERY = 3600           # 1 hour
TTL_MONITORING = 3600          # 1 hour
