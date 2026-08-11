"""One-shot, manual-refresh CLI to discover the Fabric semantic model schema.

Connects to the remote Fabric MCP server, runs the view-level DAX INFO
queries and the report introspection tools, and prints the raw results as
JSON to stdout. This is a discovery/audit tool for a human to read and use
to manually update catalog/fabric_metrics.yaml — it does not write the YAML
file itself. Run it whenever the underlying Fabric semantic model changes:

    python scripts/discover_fabric_schema.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")

DAX_QUERIES: dict[str, str] = {
    "tables": "EVALUATE INFO.VIEW.TABLES()",
    "measures": "EVALUATE INFO.VIEW.MEASURES()",
    "columns": "EVALUATE INFO.VIEW.COLUMNS()",
}


def _print_section(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


async def main() -> None:
    headers = {"Authorization": f"Bearer {MCP_AUTH_TOKEN}"}
    async with streamablehttp_client(MCP_SERVER_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            for title, dax_query in DAX_QUERIES.items():
                result = await session.call_tool(
                    "execute_dax_query", {"query": dax_query}
                )
                _print_section(f"execute_dax_query :: {title}", result.model_dump())

            pages_result = await session.call_tool("list_report_pages", {})
            _print_section("list_report_pages", pages_result.model_dump())

            visuals_result = await session.call_tool("list_report_visuals", {})
            _print_section("list_report_visuals", visuals_result.model_dump())


if __name__ == "__main__":
    asyncio.run(main())
