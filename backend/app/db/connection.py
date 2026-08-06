"""Database connection helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Result

_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://gefin:gefin@localhost:5432/gefin"
)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            _DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


@contextmanager
def get_connection() -> Generator:
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()


def run_query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute a read-only query and return list of dicts."""
    with get_connection() as conn:
        result: Result = conn.execute(text(sql), params or {})
        columns = list(result.keys())
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]
