"""GEFIN Agent - FastAPI entrypoint."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agent.graph import run_agent
from app.audit.logger import write_audit
from app.catalog.loader import get_catalog_summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gefin")

app = FastAPI(
    title="GEFIN Agent API",
    description="Agentic analytics for Contas a Receber (prototype)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    data: list[dict[str, Any]] | None = None
    chart_spec: dict[str, Any] | None = None
    lineage: dict[str, Any] | None = None
    steps: list[str] | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "gefin-backend"}


@app.get("/catalog")
def catalog():
    """Return a human-readable summary of the semantic catalog."""
    return get_catalog_summary()


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    logger.info("Chat request session=%s msg=%s", session_id, req.message[:80])

    result = await run_agent(user_message=req.message, session_id=session_id)

    # Persist audit trail
    try:
        write_audit(
            session_id=session_id,
            user_message=req.message,
            agent_plan=result.get("plan"),
            tools_called=result.get("tools_called"),
            final_sql=result.get("final_sql"),
            response_summary=result.get("answer", "")[:500],
            lineage=result.get("lineage"),
            latency_ms=result.get("latency_ms"),
        )
    except Exception as e:
        logger.warning("Failed to write audit: %s", e)

    return ChatResponse(
        session_id=session_id,
        answer=result.get("answer", "Não foi possível gerar uma resposta."),
        data=result.get("data"),
        chart_spec=result.get("chart_spec"),
        lineage=result.get("lineage"),
        steps=result.get("steps"),
    )
