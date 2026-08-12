"""GEFIN Agent - FastAPI entrypoint."""

from __future__ import annotations

import logging

from chainlit.utils import mount_chainlit
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/health")
def health():
    return {"status": "ok", "service": "gefin-backend"}


@app.get("/catalog")
def catalog():
    """Return a human-readable summary of the semantic catalog."""
    return get_catalog_summary()


mount_chainlit(app=app, target="app/chainlit_app.py", path="/chainlit")
