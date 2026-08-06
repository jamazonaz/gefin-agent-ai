"""Simple audit logger that writes to the audit_log table."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.db.connection import get_connection
from sqlalchemy import text

logger = logging.getLogger("gefin.audit")


def write_audit(
    *,
    session_id: str,
    user_message: str,
    agent_plan: str | None = None,
    tools_called: list | dict | None = None,
    final_sql: str | None = None,
    response_summary: str | None = None,
    lineage: dict | None = None,
    latency_ms: int | None = None,
) -> None:
    sql = text(
        """
        INSERT INTO audit_log
            (session_id, user_message, agent_plan, tools_called,
             final_sql, response_summary, lineage, latency_ms)
        VALUES
            (:session_id, :user_message, :agent_plan, CAST(:tools_called AS jsonb),
             :final_sql, :response_summary, CAST(:lineage AS jsonb), :latency_ms)
        """
    )
    params = {
        "session_id": session_id,
        "user_message": user_message,
        "agent_plan": agent_plan,
        "tools_called": json.dumps(tools_called or [], default=str),
        "final_sql": final_sql,
        "response_summary": response_summary,
        "lineage": json.dumps(lineage or {}, default=str),
        "latency_ms": latency_ms,
    }
    try:
        with get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()
    except Exception as e:
        logger.exception("Audit write failed: %s", e)
