from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from gateway_ia.models import Session


class SessionStore:
    """Thread-safe in-memory session store with bounded capacity."""

    def __init__(self, max_sessions: int = 1000) -> None:
        self._sessions: OrderedDict[str, Session] = OrderedDict()
        self._max = max_sessions
        self._lock = Lock()

    def add(self, session: Session) -> None:
        with self._lock:
            self._sessions[session.id] = session
            while len(self._sessions) > self._max:
                self._sessions.popitem(last=False)

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_all(self) -> list[Session]:
        """Return sessions newest-first."""
        with self._lock:
            return list(reversed(self._sessions.values()))

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
