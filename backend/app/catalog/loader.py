"""Lightweight catalog loader (YAML)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CATALOG_PATH = os.getenv("CATALOG_PATH", "/app/catalog/metrics.yaml")


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    path = Path(_CATALOG_PATH)
    if not path.exists():
        # Fallback for local dev outside Docker
        alt = Path(__file__).resolve().parents[3] / "catalog" / "metrics.yaml"
        if alt.exists():
            path = alt
        else:
            return {"metrics": [], "dimensions": [], "views": []}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_catalog_summary() -> dict[str, Any]:
    cat = load_catalog()
    return {
        "domain": cat.get("domain"),
        "metrics": [
            {
                "id": m["id"],
                "name": m["name"],
                "description": m.get("description"),
                "view": m.get("view"),
                "expression": m.get("expression"),
                "examples": m.get("examples", []),
            }
            for m in cat.get("metrics", [])
        ],
        "views": [
            {
                "name": v["name"],
                "description": v.get("description"),
                "columns": v.get("columns", []),
            }
            for v in cat.get("views", [])
        ],
    }


def get_metric(metric_id: str) -> dict[str, Any] | None:
    cat = load_catalog()
    for m in cat.get("metrics", []):
        if m["id"] == metric_id:
            return m
    return None


def list_allowed_views() -> set[str]:
    cat = load_catalog()
    return {v["name"] for v in cat.get("views", [])}


def get_view_info(view_name: str) -> dict[str, Any] | None:
    cat = load_catalog()
    for v in cat.get("views", []):
        if v["name"] == view_name:
            return v
    return None
