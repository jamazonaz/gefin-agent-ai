"""Tests for the Fabric (sales pipeline) catalog loader and agent tools."""

from __future__ import annotations

from app.agent.fabric_tools import (
    FABRIC_LOCAL_TOOLS,
    get_fabric_lineage,
    get_fabric_measure_definition,
    list_fabric_measures,
    triage_fabric_scope,
)
from app.catalog.fabric_loader import (
    get_fabric_catalog_summary,
    get_fabric_measure,
    get_fabric_report_pages,
    list_fabric_tables,
)


def test_get_fabric_catalog_summary_returns_domain_and_lists() -> None:
    summary = get_fabric_catalog_summary()
    assert summary["domain"] == "sales_pipeline_fabric"
    assert len(summary["measures"]) > 0
    assert len(summary["tables"]) > 0


def test_get_fabric_measure_returns_expected_keys() -> None:
    measure = get_fabric_measure("revenue_won")
    assert measure is not None
    assert measure["id"] == "revenue_won"
    assert measure["name"] == "Revenue Won"
    assert measure["dax_reference"] == "Opportunities[Revenue Won]"
    assert measure["table"] == "Opportunities"


def test_get_fabric_measure_returns_none_for_unknown() -> None:
    assert get_fabric_measure("does_not_exist") is None


def test_list_fabric_tables_excludes_hidden_table() -> None:
    tables = list_fabric_tables()
    assert len(tables) > 0
    assert all(isinstance(t, str) for t in tables)
    assert "Opportunity Forecast Adjustment" not in tables


def test_get_fabric_report_pages_filters_by_measure() -> None:
    filtered = get_fabric_report_pages("revenue_won")
    all_pages = get_fabric_report_pages()
    assert isinstance(filtered, list)
    assert isinstance(all_pages, list)
    assert len(all_pages) >= len(filtered)


def test_list_fabric_measures_tool_returns_non_empty_measures() -> None:
    result = list_fabric_measures.invoke({})
    assert isinstance(result["measures"], list)
    assert len(result["measures"]) > 0


def test_get_fabric_measure_definition_tool_returns_definition() -> None:
    result = get_fabric_measure_definition.invoke({"measure_id": "revenue_won"})
    assert "error" not in result
    assert "related_report_pages" in result


def test_get_fabric_measure_definition_tool_errors_on_unknown_measure() -> None:
    result = get_fabric_measure_definition.invoke({"measure_id": "nope"})
    assert "error" in result


def test_get_fabric_lineage_tool_returns_lineage_for_known_measure() -> None:
    result = get_fabric_lineage.invoke(
        {"measures_used": ["revenue_won"], "dax": "EVALUATE ROW(1,1)"}
    )
    assert result["source_system"] == "Microsoft Fabric / Power BI Semantic Model"
    assert result["layer"] == "fabric_semantic_model"
    assert len(result["measures"]) > 0
    assert any(m["measure"] == "revenue_won" for m in result["measures"])


def test_get_fabric_lineage_tool_handles_empty_measures_used() -> None:
    result = get_fabric_lineage.invoke({"measures_used": []})
    assert result["measures"] == []


def test_triage_fabric_scope_tool_echoes_input() -> None:
    result = triage_fabric_scope.invoke({"in_scope": True, "reason": "test"})
    assert result == {"in_scope": True, "reason": "test"}


def test_fabric_local_tools_has_three_entries() -> None:
    assert len(FABRIC_LOCAL_TOOLS) == 3
    names = {t.name for t in FABRIC_LOCAL_TOOLS}
    assert names == {
        "list_fabric_measures",
        "get_fabric_measure_definition",
        "get_fabric_lineage",
    }
