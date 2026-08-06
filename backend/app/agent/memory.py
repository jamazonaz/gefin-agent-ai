"""Simple in-memory session store (sufficient for prototype)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

# session_id -> list of messages / intermediate state
_sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)


def get_history(session_id: str) -> list[dict[str, Any]]:
    return list(_sessions.get(session_id, []))


def append_message(session_id: str, role: str, content: str, **extra: Any) -> None:
    _sessions[session_id].append({"role": role, "content": content, **extra})


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
