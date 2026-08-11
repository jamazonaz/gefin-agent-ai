"""Local (non-MCP) agent tools for the Fabric / Sales Pipeline domain."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from app.catalog.fabric_loader import (
    get_fabric_catalog_summary,
    get_fabric_measure,
    get_fabric_report_pages,
)

logger = logging.getLogger("gefin.fabric_tools")

FABRIC_SOURCE_SYSTEM = "Microsoft Fabric / Power BI Semantic Model"
FABRIC_LINEAGE_NOTE = (
    "Linhagem de consulta: medidas/tabelas usadas na consulta DAX. "
    "Não é lineage ponta-a-ponta (não reflete a origem dos dados antes do modelo semântico)."
)


@tool
def list_fabric_measures() -> dict[str, Any]:
    """Lista todas as medidas e tabelas disponíveis no catálogo semântico do Fabric (Pipeline de Vendas)."""
    try:
        return get_fabric_catalog_summary()
    except Exception as e:
        logger.exception("Failed to load Fabric catalog summary")
        return {"error": str(e)}


@tool
def get_fabric_measure_definition(measure_id: str) -> dict[str, Any]:
    """Retorna a definição completa de uma medida do catálogo Fabric (descrição, tabela, dax_reference, tipo, exemplos e páginas de relatório relacionadas)."""
    try:
        measure = get_fabric_measure(measure_id)
    except Exception as e:
        logger.exception("Failed to load Fabric measure %s", measure_id)
        return {"error": str(e)}

    if not measure:
        return {"error": f"Medida '{measure_id}' não encontrada. Use list_fabric_measures."}

    result = dict(measure)
    try:
        result["related_report_pages"] = get_fabric_report_pages(measure_id)
    except Exception as e:
        logger.exception("Failed to load Fabric report pages for %s", measure_id)
        result["related_report_pages"] = []
        result["report_pages_warning"] = str(e)
    return result


@tool
def get_fabric_lineage(measures_used: list[str], dax: str | None = None) -> dict[str, Any]:
    """
    Retorna a linhagem (origem) das medidas do modelo semântico usadas na resposta.
    Sempre chame esta tool antes da resposta final.
    """
    lineage_measures: list[dict[str, Any]] = []
    for measure_id in measures_used:
        try:
            measure = get_fabric_measure(measure_id)
            report_pages = get_fabric_report_pages(measure_id)
        except Exception as e:
            logger.exception("Failed to build lineage for measure %s", measure_id)
            lineage_measures.append({"measure": measure_id, "error": str(e)})
            continue

        lineage_measures.append(
            {
                "measure": measure_id,
                "name": measure.get("name") if measure else None,
                "dax_reference": measure.get("dax_reference") if measure else None,
                "table": measure.get("table") if measure else None,
                "description": measure.get("description") if measure else None,
                "report_pages": report_pages,
            }
        )

    return {
        "source_system": FABRIC_SOURCE_SYSTEM,
        "layer": "fabric_semantic_model",
        "measures": lineage_measures,
        "dax": dax,
        "note": FABRIC_LINEAGE_NOTE,
    }


@tool
def triage_fabric_scope(in_scope: bool, reason: str) -> dict[str, Any]:
    """
    Classifica se a pergunta do usuário pertence ao domínio de Pipeline de Vendas
    coberto pelo modelo semântico do Fabric (Revenue Won, Revenue in Pipeline,
    Forecast, Win/Loss Ratio, Close Rate, contagem e valor de oportunidades,
    ticket médio, meta de receita, páginas e visuais do relatório).
    Chame com in_scope=False para qualquer outro assunto (notícias, política,
    cultura geral, outros domínios de negócio, receitas, manutenção, etc.),
    incluindo perguntas sobre Contas a Receber — esse é outro assistente —
    mesmo que você saiba a resposta.
    """
    return {"in_scope": in_scope, "reason": reason}


FABRIC_LOCAL_TOOLS = [
    list_fabric_measures,
    get_fabric_measure_definition,
    get_fabric_lineage,
]
