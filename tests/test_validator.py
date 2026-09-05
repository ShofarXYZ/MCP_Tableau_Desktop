"""Tests for the rule-based formula validator and DAX detector."""

from __future__ import annotations

from tableau_mcp.calculations.dax_detector import (
    detect_dax_functions,
    has_table_column_reference,
)
from tableau_mcp.calculations.validator import validate_formula
from tableau_mcp.models import FieldMetadata

FIELDS = [
    FieldMetadata(name="[Receita]", caption="Receita", role="measure"),
    FieldMetadata(name="[Pedido ID]", caption="Pedido ID", role="dimension"),
]


def test_empty_formula_is_invalid() -> None:
    result = validate_formula("")
    assert not result.is_valid
    assert any(i.code == "empty_formula" for i in result.issues)


def test_balanced_parentheses() -> None:
    result = validate_formula("SUM([Receita]")
    assert not result.is_valid
    assert any(i.code == "unbalanced_paren" for i in result.issues)


def test_dax_detection_flags_calculate() -> None:
    assert "CALCULATE" in detect_dax_functions("CALCULATE(SUM([Receita]))")
    result = validate_formula("CALCULATE(SUM([Receita]))")
    assert not result.is_valid
    assert any(i.code == "dax_function" for i in result.issues)


def test_dax_false_positive_avoided_in_field_name() -> None:
    # 'ALL' appears inside a bracketed field name and must NOT be flagged.
    assert detect_dax_functions("SUM([All Regions])") == []


def test_table_column_reference_detected() -> None:
    assert has_table_column_reference("Sales[Revenue]")
    assert not has_table_column_reference("SUM([Revenue])")


def test_unknown_reference_with_suggestion() -> None:
    result = validate_formula("SUM([Receit])", FIELDS)
    assert not result.is_valid
    assert "Receit" in result.references.missing
    assert "Receita" in result.references.suggestions.get("Receit", [])


def test_valid_ratio_formula() -> None:
    result = validate_formula("SUM([Receita]) / COUNTD([Pedido ID])", FIELDS)
    assert result.is_valid


def test_division_by_zero_warning() -> None:
    result = validate_formula("SUM([Receita]) / 0", FIELDS)
    assert any(i.code == "division_by_zero" for i in result.issues)


def test_aggregate_mix_warning() -> None:
    result = validate_formula("SUM([Receita]) + [Receita]", FIELDS)
    assert any(i.code == "aggregate_mix" for i in result.issues)
