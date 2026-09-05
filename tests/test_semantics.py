"""Tests for the Analytics Copilot semantic layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from tableau_mcp.config import Settings
from tableau_mcp.models import FieldMetadata
from tableau_mcp.semantics.field_classifier import classify_field
from tableau_mcp.semantics.normalization import normalize, tokens
from tableau_mcp.tools import analytics_tools, field_tools
from tableau_mcp.tools.context import ToolContext

# A realistic sales workbook with varied naming styles (camelCase, accents, EN/PT).
SALES_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1'>
  <datasources>
    <datasource caption='Vendas' name='federated.vendas'>
      <connection class='federated' />
      <column caption='PedidoID' datatype='integer' name='[PedidoID]' role='dimension' type='ordinal' />
      <column caption='Cliente' datatype='string' name='[Cliente]' role='dimension' type='nominal' />
      <column caption='Produto' datatype='string' name='[Produto]' role='dimension' type='nominal' />
      <column caption='Categoria' datatype='string' name='[Categoria]' role='dimension' type='nominal' />
      <column caption='Canal' datatype='string' name='[Canal]' role='dimension' type='nominal' />
      <column caption='Estado' datatype='string' name='[Estado]' role='dimension' type='nominal' />
      <column caption='Data' datatype='date' name='[Data]' role='dimension' type='ordinal' />
      <column caption='Quantidade' datatype='integer' name='[Quantidade]' role='measure' type='quantitative' />
      <column caption='ValorVenda' datatype='real' name='[ValorVenda]' role='measure' type='quantitative' />
      <column caption='Desconto' datatype='real' name='[Desconto]' role='measure' type='quantitative' />
      <column caption='Custo' datatype='real' name='[Custo]' role='measure' type='quantitative' />
    </datasource>
  </datasources>
</workbook>
"""


@pytest.fixture
def sales_workbook(sandbox: Settings) -> str:
    path: Path = sandbox.workbooks_path / "vendas.twb"
    path.write_text(SALES_TWB, encoding="utf-8")
    return "vendas.twb"


# -- normalization / classification -----------------------------------------


def test_normalize_camelcase_and_accents() -> None:
    assert normalize("ValorVenda") == "valor venda"
    assert normalize("[Região]") == "regiao"
    assert tokens("OrderDate") == ["order", "date"]


def test_classify_revenue() -> None:
    cf = classify_field(FieldMetadata(name="[ValorVenda]", caption="ValorVenda", role="measure"))
    assert cf.semantic_type == "revenue"
    assert cf.confidence == "high"


def test_classify_identifier() -> None:
    cf = classify_field(FieldMetadata(name="[PedidoID]", caption="PedidoID", role="dimension"))
    assert cf.semantic_type == "identifier"


def test_classify_date_by_datatype() -> None:
    cf = classify_field(
        FieldMetadata(name="[Data]", caption="Data", role="dimension", datatype="date")
    )
    assert cf.semantic_type == "date"


def test_classify_discount_and_cost() -> None:
    disc = classify_field(FieldMetadata(name="[Desconto]", caption="Desconto", role="measure"))
    cost = classify_field(FieldMetadata(name="[Custo]", caption="Custo", role="measure"))
    assert disc.semantic_type == "discount"
    assert cost.semantic_type == "cost"


# -- analyze_dataset ---------------------------------------------------------


def test_analyze_dataset_domain(ctx: ToolContext, sales_workbook: str) -> None:
    resp = analytics_tools.analyze_dataset(sales_workbook, ctx=ctx)
    assert resp.success
    analysis = resp.analyses[0]
    assert analysis.inferred_domain == "Vendas"
    assert analysis.domain_confidence == "high"
    assert "ValorVenda" in analysis.measures
    assert "Data" in analysis.dates
    assert "PedidoID" in analysis.identifiers
    assert "Estado" in analysis.geo_fields


# -- suggest_business_metrics ------------------------------------------------


def test_suggest_metrics_covers_core_kpis(ctx: ToolContext, sales_workbook: str) -> None:
    resp = analytics_tools.suggest_business_metrics(sales_workbook, "Vendas", ctx=ctx)
    assert resp.success
    names = {m.name for m in resp.metrics}
    assert {
        "Receita Bruta",
        "Receita Líquida",
        "Lucro",
        "Margem %",
        "Ticket Médio",
        "Pedidos",
        "Clientes Únicos",
        "MoM",
        "YoY",
        "Running Total",
    } <= names
    # Every metric carries a rationale.
    assert all(m.rationale for m in resp.metrics)


def test_suggested_formulas_are_native_not_dax(ctx: ToolContext, sales_workbook: str) -> None:
    from tableau_mcp.calculations.dax_detector import detect_dax_functions

    resp = analytics_tools.suggest_business_metrics(sales_workbook, "Vendas", ctx=ctx)
    for metric in resp.metrics:
        if metric.formula:
            assert detect_dax_functions(metric.formula) == [], metric.name


# -- create_recommended_metrics ---------------------------------------------


def test_create_recommended_metrics(ctx: ToolContext, sales_workbook: str) -> None:
    resp = analytics_tools.create_recommended_metrics(sales_workbook, "Vendas", ctx=ctx)
    assert resp.success, resp.error
    assert resp.applied
    assert resp.backup is not None
    created = {c.field_name for c in resp.changes if c.status == "created"}
    assert "Receita Bruta" in created and "Ticket Médio" in created

    # All created fields must be real calculated fields in the workbook now.
    calc = field_tools.list_calculated_fields(sales_workbook, ctx).calculated_fields
    calc_names = {c.caption for c in calc}
    assert created <= calc_names


def test_create_recommended_is_idempotent(ctx: ToolContext, sales_workbook: str) -> None:
    first = analytics_tools.create_recommended_metrics(sales_workbook, "Vendas", ctx=ctx)
    assert first.applied
    second = analytics_tools.create_recommended_metrics(sales_workbook, "Vendas", ctx=ctx)
    # Nothing new to create the second time.
    assert second.success
    assert not second.applied


# -- suggest_visualizations --------------------------------------------------


def test_suggest_visualizations(ctx: ToolContext, sales_workbook: str) -> None:
    resp = analytics_tools.suggest_visualizations(sales_workbook, "Vendas", ctx=ctx)
    assert resp.success
    charts = {(v.title, v.chart_type) for v in resp.visualizations}
    assert any(ct == "map" for _, ct in charts)  # Estado -> map
    assert any(ct == "line" for _, ct in charts)  # Data -> line
    assert all(v.rationale for v in resp.visualizations)
