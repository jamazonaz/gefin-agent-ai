"""Agent tools with strong guardrails."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import sqlglot
from sqlglot import exp
from langchain_core.tools import tool

from app.catalog.loader import (
    get_catalog_summary,
    get_metric,
    get_view_info,
    list_allowed_views,
)
from app.db.connection import run_query

logger = logging.getLogger("gefin.tools")

SQL_ROW_LIMIT = int(os.getenv("SQL_ROW_LIMIT", "500"))
ALLOWED_VIEWS = list_allowed_views()
DEPLOYMENT_ENV = os.getenv("DEPLOYMENT_ENV", "local")


def _is_safe_select(sql: str) -> tuple[bool, str]:
    """Validate that SQL is a single SELECT against whitelisted views only."""
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as e:
        return False, f"SQL parse error: {e}"

    if not isinstance(parsed, exp.Select):
        return False, "Only SELECT statements are allowed."

    # Disallow dangerous constructs
    forbidden = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
    for node in parsed.walk():
        if isinstance(node, forbidden):
            return False, f"Forbidden statement type: {type(node).__name__}"

    # Collect tables/views referenced
    tables = {t.name.lower() for t in parsed.find_all(exp.Table)}
    if not tables:
        return False, "No table/view found in query."

    allowed = {v.lower() for v in ALLOWED_VIEWS}
    illegal = tables - allowed
    if illegal:
        return False, f"Views not allowed: {', '.join(sorted(illegal))}. Allowed: {', '.join(sorted(allowed))}"

    return True, "ok"


def _ensure_limit(sql: str) -> str:
    """Add LIMIT if missing."""
    upper = sql.upper()
    if "LIMIT" in upper:
        return sql
    # Simple append (good enough for MVP)
    return f"{sql.rstrip().rstrip(';')} LIMIT {SQL_ROW_LIMIT}"


@tool
def list_metrics() -> dict[str, Any]:
    """Lista todas as métricas, dimensões e views disponíveis no catálogo semântico do GEFIN."""
    return get_catalog_summary()


@tool
def get_metric_definition(metric_id: str) -> dict[str, Any]:
    """Retorna a definição completa de uma métrica do catálogo (descrição, view, expressão, colunas disponíveis, exemplos)."""
    m = get_metric(metric_id)
    if not m:
        return {"error": f"Métrica '{metric_id}' não encontrada. Use list_metrics."}
    result = dict(m)
    view_info = get_view_info(m.get("view", ""))
    if view_info:
        result["view_columns"] = view_info.get("columns", [])
        if view_info.get("warning"):
            result["view_warning"] = view_info["warning"]
    return result


@tool
def execute_sql(sql: str) -> dict[str, Any]:
    """
    Executa um SELECT seguro apenas contra as views semânticas whitelisted.
    Nunca use tabelas brutas (customers, invoices, payments).
    Sempre prefira as views: vw_ar_open_items, vw_ar_aging, vw_ar_customer_summary, vw_ar_kpi_daily, vw_ar_dso.
    """
    sql = sql.strip().rstrip(";")
    ok, msg = _is_safe_select(sql)
    if not ok:
        logger.warning("Blocked SQL: %s | reason: %s", sql[:200], msg)
        return {"error": msg, "sql": sql}

    sql = _ensure_limit(sql)
    try:
        rows = run_query(sql)
        return {
            "success": True,
            "row_count": len(rows),
            "columns": list(rows[0].keys()) if rows else [],
            "data": rows,
            "sql_executed": sql,
        }
    except Exception as e:
        logger.exception("SQL execution failed")
        return {"error": str(e), "sql": sql}


@tool
def validate_result(data: list[dict[str, Any]]) -> dict[str, Any]:
    """Faz checagens básicas de qualidade em um resultado tabular."""
    if not data:
        return {"ok": True, "warnings": ["Resultado vazio."]}

    warnings = []
    n = len(data)
    if n == 0:
        warnings.append("Nenhuma linha retornada.")

    # Check numeric columns for extreme nulls
    if data:
        keys = data[0].keys()
        for k in keys:
            nulls = sum(1 for r in data if r.get(k) is None)
            if nulls / max(n, 1) > 0.5:
                warnings.append(f"Coluna '{k}' tem >50% de nulos ({nulls}/{n}).")

    return {
        "ok": len(warnings) == 0,
        "row_count": n,
        "warnings": warnings,
    }


@tool
def generate_chart(
    chart_type: str,
    title: str,
    data: list[dict[str, Any]],
    x_key: str,
    y_key: str,
) -> dict[str, Any]:
    """
    Gera uma especificação simples de gráfico (consumida pelo frontend Plotly).
    chart_type: bar | line | pie
    """
    chart_type = chart_type.lower().strip()
    if chart_type not in {"bar", "line", "pie"}:
        return {"error": "chart_type deve ser bar, line ou pie"}

    if not data:
        return {"error": "Sem dados para gerar gráfico"}

    return {
        "chart_type": chart_type,
        "title": title,
        "x_key": x_key,
        "y_key": y_key,
        "data": data,
    }


@tool
def get_lineage(views_used: list[str], sql: str | None = None) -> dict[str, Any]:
    """
    Retorna a linhagem (origem) dos dados usados na resposta.
    Sempre chame esta tool antes da resposta final.
    """
    lineage_views = []
    for v in views_used:
        info = get_view_info(v)
        lineage_views.append(
            {
                "view": v,
                "description": info.get("description") if info else None,
                "columns": info.get("columns") if info else None,
            }
        )

    return {
        "source_system": f"PostgreSQL ({DEPLOYMENT_ENV})",
        "layer": "semantic_views",
        "views": lineage_views,
        "sql": sql,
        "note": "Dados provenientes exclusivamente de views curadas. Tabelas brutas não são acessíveis ao agente.",
    }


@tool
def triage_scope(in_scope: bool, reason: str) -> dict[str, Any]:
    """
    Classifica se a pergunta do usuário pertence ao domínio de Contas a Receber
    coberto pelo catálogo semântico do GEFIN (saldo em aberto, aging, DSO,
    faturas, clientes devedores, tendências de contas a receber).
    Chame com in_scope=False para qualquer outro assunto (notícias, política,
    cultura geral, outros domínios de negócio, receitas, manutenção, etc.),
    mesmo que você saiba a resposta.
    """
    return {"in_scope": in_scope, "reason": reason}


# Export list for the agent
ALL_TOOLS = [
    list_metrics,
    get_metric_definition,
    execute_sql,
    validate_result,
    generate_chart,
    get_lineage,
]
