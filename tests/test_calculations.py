"""Tests for calculated-field creation, update, delete, batch, and validation."""

from __future__ import annotations

from tableau_mcp.models import CalculatedFieldSpec
from tableau_mcp.tools import calculation_tools, field_tools
from tableau_mcp.tools.context import ToolContext
from tableau_mcp.workbook.inspector import WorkbookInspector


def _formula_of(ctx: ToolContext, filename: str, caption: str) -> str | None:
    _, tree = ctx.reader.load_tree(filename)
    for field in WorkbookInspector(tree).all_fields():
        if field.caption == caption:
            return field.formula
    return None


def test_create_calculated_field(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        single_workbook,
        "Vendas",
        "Ticket Médio",
        "SUM([Receita]) / COUNTD([Pedido ID])",
        ctx=ctx,
    )
    assert resp.success, resp.error
    assert resp.change is not None and resp.change.status == "created"
    assert resp.backup is not None
    assert (
        _formula_of(ctx, single_workbook, "Ticket Médio") == "SUM([Receita]) / COUNTD([Pedido ID])"
    )


def test_create_duplicate_rejected(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Receita", "SUM([Receita])", ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None and resp.error.code == "duplicate_field"


def test_create_rejects_dax(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Bad", "CALCULATE(SUM([Receita]))", ctx=ctx
    )
    assert not resp.success
    assert resp.validation is not None
    assert "CALCULATE" in resp.validation.dax_functions_detected


def test_create_unknown_reference(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Ghost", "SUM([Inexistente])", ctx=ctx
    )
    assert not resp.success
    assert resp.validation is not None
    assert any(i.code == "unknown_reference" for i in resp.validation.issues)


def test_update_calculated_field(ctx: ToolContext, single_workbook: str) -> None:
    calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Ticket", "SUM([Receita])", ctx=ctx
    )
    resp = calculation_tools.update_calculated_field(
        single_workbook, "Vendas", "Ticket", "AVG([Receita])", ctx=ctx
    )
    assert resp.success, resp.error
    assert resp.change is not None
    assert resp.change.previous_formula == "SUM([Receita])"
    assert resp.change.formula == "AVG([Receita])"


def test_update_missing_field(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.update_calculated_field(
        single_workbook, "Vendas", "NaoExiste", "SUM([Receita])", ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None and resp.error.code == "field_not_found"


def test_delete_requires_confirmation(ctx: ToolContext, single_workbook: str) -> None:
    calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Tmp", "SUM([Receita])", ctx=ctx
    )
    resp = calculation_tools.delete_calculated_field(
        single_workbook, "Vendas", "Tmp", confirm=False, ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None and resp.error.code == "confirmation_required"


def test_delete_confirmed(ctx: ToolContext, single_workbook: str) -> None:
    calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Tmp", "SUM([Receita])", ctx=ctx
    )
    resp = calculation_tools.delete_calculated_field(
        single_workbook, "Vendas", "Tmp", confirm=True, ctx=ctx
    )
    assert resp.success, resp.error
    assert _formula_of(ctx, single_workbook, "Tmp") is None


def test_delete_physical_field_blocked(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.delete_calculated_field(
        single_workbook, "Vendas", "Receita", confirm=True, ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None and resp.error.code == "field_not_found"


def test_batch_all_or_nothing(ctx: ToolContext, single_workbook: str) -> None:
    fields = [
        CalculatedFieldSpec(field_name="Receita Total", formula="SUM([Receita])"),
        CalculatedFieldSpec(field_name="Ruim", formula="CALCULATE(SUM([Receita]))"),
    ]
    resp = calculation_tools.create_calculated_fields_batch(
        single_workbook, "Vendas", fields, ctx=ctx
    )
    assert not resp.success
    assert not resp.applied
    # No field should have been written.
    assert _formula_of(ctx, single_workbook, "Receita Total") is None


def test_batch_success(ctx: ToolContext, single_workbook: str) -> None:
    fields = [
        CalculatedFieldSpec(field_name="Receita Total", formula="SUM([Receita])"),
        CalculatedFieldSpec(
            field_name="Ticket Médio", formula="SUM([Receita]) / COUNTD([Pedido ID])"
        ),
    ]
    resp = calculation_tools.create_calculated_fields_batch(
        single_workbook, "Vendas", fields, ctx=ctx
    )
    assert resp.success, resp.error
    assert resp.applied
    assert all(c.status == "created" for c in resp.changes)
    assert _formula_of(ctx, single_workbook, "Receita Total") == "SUM([Receita])"


def test_validate_formula_only(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.validate_tableau_formula(
        "SUM([Receita]) / COUNTD([Pedido ID])", single_workbook, "Vendas", ctx=ctx
    )
    assert resp.success
    assert resp.validation is not None
    assert resp.validation.is_valid


def test_multiline_formula(ctx: ToolContext, single_workbook: str) -> None:
    formula = "IF [Receita] > 0\nTHEN SUM([Receita])\nELSE 0\nEND"
    resp = calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Multi", formula, ctx=ctx
    )
    assert resp.success, resp.error
    assert _formula_of(ctx, single_workbook, "Multi") == formula


def test_multi_datasource_targeting(ctx: ToolContext, multi_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        multi_workbook, "Custos", "Margem", "SUM([Custo])", ctx=ctx
    )
    assert resp.success, resp.error
    fields = field_tools.list_fields(multi_workbook, "Custos", "all", ctx).fields
    assert "Margem" in {f.caption for f in fields}
    # Should not appear in the other datasource.
    vendas = field_tools.list_fields(multi_workbook, "Vendas", "all", ctx).fields
    assert "Margem" not in {f.caption for f in vendas}
