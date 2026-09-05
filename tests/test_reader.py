"""Tests for reading, listing, and inspecting workbooks."""

from __future__ import annotations

from tableau_mcp.tools import field_tools, workbook_tools
from tableau_mcp.tools.context import ToolContext


def test_list_workbooks(ctx: ToolContext, single_workbook: str) -> None:
    resp = workbook_tools.list_workbooks(ctx)
    assert resp.success
    names = [w.filename for w in resp.workbooks]
    assert single_workbook in names
    wb = next(w for w in resp.workbooks if w.filename == single_workbook)
    assert wb.size_bytes > 0
    assert wb.relative_path == single_workbook


def test_inspect_workbook(ctx: ToolContext, single_workbook: str) -> None:
    resp = workbook_tools.inspect_workbook(single_workbook, ctx)
    assert resp.success
    assert len(resp.datasources) == 1
    assert resp.datasources[0].caption == "Vendas"
    assert resp.worksheets == ["Vendas por Região"]
    assert resp.dashboards == ["Dashboard Vendas"]
    captions = {f.caption for f in resp.fields}
    assert {"Receita", "Pedido ID", "Região", "Desconto Total"} <= captions


def test_inspect_detects_calculated_field(ctx: ToolContext, single_workbook: str) -> None:
    resp = workbook_tools.inspect_workbook(single_workbook, ctx)
    calc = next(f for f in resp.fields if f.caption == "Desconto Total")
    assert calc.kind == "calculated"
    assert calc.formula is not None
    assert "SUM([Receita])" in calc.formula


def test_list_datasources_multi(ctx: ToolContext, multi_workbook: str) -> None:
    resp = field_tools.list_datasources(multi_workbook, ctx)
    assert resp.success
    assert {d.caption for d in resp.datasources} == {"Vendas", "Custos"}


def test_list_fields_filter_measure(ctx: ToolContext, single_workbook: str) -> None:
    resp = field_tools.list_fields(single_workbook, "Vendas", "measure", ctx)
    assert resp.success
    assert all(f.role == "measure" for f in resp.fields)
    assert "Receita" in {f.caption for f in resp.fields}


def test_list_calculated_fields(ctx: ToolContext, single_workbook: str) -> None:
    resp = field_tools.list_calculated_fields(single_workbook, ctx)
    assert resp.success
    assert len(resp.calculated_fields) == 1
    assert resp.calculated_fields[0].caption == "Desconto Total"


def test_empty_workbook_has_no_datasources(ctx: ToolContext, empty_workbook: str) -> None:
    resp = workbook_tools.inspect_workbook(empty_workbook, ctx)
    assert resp.success
    assert resp.datasources == []


def test_invalid_xml_returns_error(ctx: ToolContext, invalid_workbook: str) -> None:
    resp = workbook_tools.inspect_workbook(invalid_workbook, ctx)
    assert not resp.success
    assert resp.error is not None
    assert resp.error.code == "workbook_parse_error"
