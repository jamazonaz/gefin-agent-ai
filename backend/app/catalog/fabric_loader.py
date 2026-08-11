"""Lightweight catalog loader (YAML) for the Fabric sales pipeline domain."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_FABRIC_CATALOG_PATH = os.getenv("FABRIC_CATALOG_PATH", "/app/catalog/fabric_metrics.yaml")


@lru_cache(maxsize=1)
def load_fabric_catalog() -> dict[str, Any]:
    path = Path(_FABRIC_CATALOG_PATH)
    if not path.exists():
        # Fallback for local dev outside Docker
        alt = Path(__file__).resolve().parents[3] / "catalog" / "fabric_metrics.yaml"
        if alt.exists():
            path = alt
        else:
            return {"measures": [], "tables": [], "report_pages": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_fabric_catalog_summary() -> dict[str, Any]:
    cat = load_fabric_catalog()
    return {
        "domain": cat.get("domain"),
        "measures": [
            {
                "id": m["id"],
                "name": m["name"],
                "description": m.get("description"),
                "table": m.get("table"),
                "dax_reference": m.get("dax_reference"),
                "examples": m.get("examples", []),
            }
            for m in cat.get("measures", [])
        ],
        "tables": [
            {
                "name": t["name"],
                "description": t.get("description"),
                **({"hidden": t["hidden"]} if "hidden" in t else {}),
            }
            for t in cat.get("tables", [])
        ],
    }


def get_fabric_measure(measure_id: str) -> dict[str, Any] | None:
    cat = load_fabric_catalog()
    for m in cat.get("measures", []):
        if m["id"] == measure_id:
            return m
    return None


def list_fabric_tables() -> list[str]:
    cat = load_fabric_catalog()
    return [t["name"] for t in cat.get("tables", [])]


def get_fabric_report_pages(measure_id: str | None = None) -> list[dict[str, Any]]:
    cat = load_fabric_catalog()
    pages = cat.get("report_pages", [])
    if measure_id is None:
        return pages
    return [p for p in pages if measure_id in (p.get("related_measures") or [])]
