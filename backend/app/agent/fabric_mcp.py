"""MCP session lifecycle for the Fabric domain — one connection per chat turn."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("gefin.fabric_mcp")

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp-fabric-dck4.onrender.com/mcp")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
MCP_TIMEOUT_SECONDS = int(os.getenv("MCP_TIMEOUT_SECONDS", "60"))

ALLOWED_MCP_TOOLS = {"execute_dax_query", "list_report_pages", "list_report_visuals"}


@asynccontextmanager
async def fabric_mcp_tools() -> AsyncIterator[list[BaseTool]]:
    """Open one MCP session for the current chat turn; yield allow-listed LangChain tools."""
    headers = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"}
    async with streamablehttp_client(
        MCP_SERVER_URL, headers=headers, timeout=MCP_TIMEOUT_SECONDS
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools: list[BaseTool] = await load_mcp_tools(session)
            allowed_tools = [t for t in tools if t.name in ALLOWED_MCP_TOOLS]
            if len(allowed_tools) != len(ALLOWED_MCP_TOOLS):
                logger.warning(
                    "MCP tool mismatch: expected %s, got %s (server exposed: %s)",
                    sorted(ALLOWED_MCP_TOOLS),
                    sorted(t.name for t in allowed_tools),
                    sorted(t.name for t in tools),
                )
            yield allowed_tools
