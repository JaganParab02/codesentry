"""
In-memory session store.
No database required — all sessions are held in process memory
and automatically expire after a configurable TTL.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 3600  # 1 hour
MAX_SESSIONS = 1000  # prevent unbounded growth


class SessionStore:
    """
    Thread-safe (asyncio-safe) in-memory key-value session store.
    Sessions expire after TTL seconds and are evicted on next access.
    """

    def __init__(self, ttl: int = DEFAULT_TTL_SECONDS, max_sessions: int = MAX_SESSIONS) -> None:
        self._store: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._ttl = ttl
        self._max_sessions = max_sessions
        self._lock = asyncio.Lock()

    # ── Internal helpers ─────────────────────────────

    def _is_expired(self, session: Dict[str, Any]) -> bool:
        return time.monotonic() - session["_created_at"] > self._ttl

    def _evict_expired(self) -> None:
        expired = [sid for sid, s in self._store.items() if self._is_expired(s)]
        for sid in expired:
            del self._store[sid]
            logger.debug("[Session] Evicted expired session %s", sid)

    def _evict_oldest(self) -> None:
        if self._store:
            oldest_id, _ = next(iter(self._store.items()))
            del self._store[oldest_id]
            logger.debug("[Session] Evicted oldest session %s (capacity limit)", oldest_id)

    # ── Public API ───────────────────────────────────

    async def create(self, session_id: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Create a new session, returning the initial session dict."""
        async with self._lock:
            self._evict_expired()
            if len(self._store) >= self._max_sessions:
                self._evict_oldest()

            session: Dict[str, Any] = {
                "_session_id": session_id,
                "_created_at": time.monotonic(),
                "_status": "pending",
                **(data or {}),
            }
            self._store[session_id] = session
            logger.info("[Session] Created session %s", session_id)
            return session

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by ID, or None if not found / expired."""
        async with self._lock:
            session = self._store.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                del self._store[session_id]
                logger.debug("[Session] Session %s expired on get", session_id)
                return None
            # Move to end (LRU-style freshness)
            self._store.move_to_end(session_id)
            return session

    async def update(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update fields in an existing session. Returns False if session not found."""
        async with self._lock:
            session = self._store.get(session_id)
            if session is None or self._is_expired(session):
                return False
            session.update(updates)
            self._store.move_to_end(session_id)
            return True

    async def delete(self, session_id: str) -> bool:
        """Delete a session by ID. Returns True if it existed."""
        async with self._lock:
            existed = session_id in self._store
            self._store.pop(session_id, None)
            if existed:
                logger.info("[Session] Deleted session %s", session_id)
            return existed

    async def set_status(self, session_id: str, status: str) -> None:
        """Convenience method to update only the session status."""
        await self.update(session_id, {"_status": status})

    async def list_sessions(self) -> list:
        """Return a list of non-expired session IDs."""
        async with self._lock:
            self._evict_expired()
            return list(self._store.keys())

    async def count(self) -> int:
        """Return the number of active (non-expired) sessions."""
        async with self._lock:
            self._evict_expired()
            return len(self._store)

    async def clear_all(self) -> int:
        """Wipe all sessions. Returns the count of sessions removed."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.info("[Session] Cleared all %d sessions", count)
            return count


# ──────────────────────────────────────────────
# Singleton instance (shared across the app)
# ──────────────────────────────────────────────

_store: Optional[SessionStore] = None


def get_store() -> SessionStore:
    """Return the global singleton SessionStore, creating it if necessary."""
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
