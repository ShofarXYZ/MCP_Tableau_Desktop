"""Rule-based validation of Tableau formulas.

This validator is intentionally conservative: it detects common, high-confidence
problems (unbalanced brackets, DAX syntax, empty formulas, unknown references,
naive division-by-zero, simple aggregate/non-aggregate mixing) and returns
structured issues. It does not replace Tableau's real compiler.
"""

from __future__ import annotations

import re

from ..models import (
    FieldMetadata,
    FormulaValidationResult,
    ValidationIssue,
)
from .dax_detector import detect_dax_functions, has_table_column_reference
from .field_reference_parser import match_references
from .formula_templates import AGGREGATE_FUNCTIONS

# Identifiers followed by '(' outside of strings/brackets are treated as calls.
_FUNC_CALL_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_STRING_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")
_BRACKET_PATTERN = re.compile(r"\[[^\[\]]*\]")


def _strip_masked(formula: str) -> str:
    """Blank out quoted strings and bracketed references for structural scans."""
    without_strings = _STRING_PATTERN.sub(lambda m: " " * len(m.group(0)), formula)
    return _BRACKET_PATTERN.sub(lambda m: " " * len(m.group(0)), without_strings)


def _check_balanced(formula: str, issues: list[ValidationIssue]) -> None:
    """Check balanced parentheses, brackets, and quotes."""
    # Quotes first (unbalanced quotes make bracket scanning unreliable).
    if formula.count("'") % 2 != 0:
        issues.append(
            ValidationIssue(
                severity="error",
                code="unbalanced_single_quote",
                message="Unbalanced single quotes in formula.",
            )
        )
    if formula.count('"') % 2 != 0:
        issues.append(
            ValidationIssue(
                severity="error",
                code="unbalanced_double_quote",
                message="Unbalanced double quotes in formula.",
            )
        )

    masked = _strip_masked(formula)
    for open_ch, close_ch, code in (("(", ")", "paren"), ("[", "]", "bracket")):
        depth = 0
        balanced = True
        for char in formula if open_ch == "[" else masked:
            if char == open_ch:
                depth += 1
            elif char == close_ch:
                depth -= 1
                if depth < 0:
                    balanced = False
                    break
        if not balanced or depth != 0:
            issues.append(
                ValidationIssue(
                    severity="error",
                    code=f"unbalanced_{code}",
                    message=f"Unbalanced '{open_ch}{close_ch}' in formula.",
                )
            )


def _check_dax(formula: str, issues: list[ValidationIssue]) -> list[str]:
    """Detect DAX functions and Table[Column] references."""
    dax = detect_dax_functions(formula)
    for func in dax:
        issues.append(
            ValidationIssue(
                severity="error",
                code="dax_function",
                message=f"'{func}' is DAX/Power BI syntax and is not valid in Tableau.",
                suggestion="Use a native Tableau function instead (e.g. COUNTD, SUM, IF).",
            )
        )
    if has_table_column_reference(formula):
        issues.append(
            ValidationIssue(
                severity="error",
                code="dax_table_reference",
                message="'Table[Column]' style references are DAX; Tableau uses '[Field]'.",
            )
        )
    return dax


def _function_calls(formula: str) -> list[str]:
    masked = _strip_masked(formula)
    return [m.group(1).upper() for m in _FUNC_CALL_PATTERN.finditer(masked)]


def _check_division_by_zero(formula: str, issues: list[ValidationIssue]) -> None:
    masked = _strip_masked(formula)
    # A '/' directly followed by a literal 0 (with optional spaces) is suspicious.
    if re.search(r"/\s*0(?![\d.])", masked):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="division_by_zero",
                message="Possible division by a literal zero.",
                suggestion="Guard it with IIF(denom = 0, NULL, num / denom) to avoid errors.",
            )
        )
    elif "/" in masked:
        issues.append(
            ValidationIssue(
                severity="info",
                code="division_present",
                message="Formula performs division.",
                suggestion="Guard it with IIF(denom = 0, NULL, num / denom) if it can be zero.",
            )
        )


def _check_aggregation_mix(formula: str, calls: list[str], issues: list[ValidationIssue]) -> None:
    """Warn on a naive mix of aggregated and raw (non-aggregated) field references.

    Heuristic: if the formula contains at least one aggregate call AND at least
    one field reference that is not enclosed by any function call, Tableau will
    usually reject it ("Cannot mix aggregate and non-aggregate").
    """
    has_aggregate = any(c in AGGREGATE_FUNCTIONS for c in calls)
    if not has_aggregate:
        return
    # Remove every "FUNC( ... )" span, then see if bare [refs] remain.
    stripped = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\s*\([^()]*\)", " ", formula)
    # Repeat to peel nested calls a couple of times.
    for _ in range(3):
        stripped = re.sub(r"[A-Za-z_][A-Za-z0-9_]*\s*\([^()]*\)", " ", stripped)
    if _BRACKET_PATTERN.search(stripped):
        issues.append(
            ValidationIssue(
                severity="warning",
                code="aggregate_mix",
                message="Formula may mix aggregated and non-aggregated fields.",
                suggestion="Wrap raw field references in an aggregate (e.g. SUM/ATTR/MIN).",
            )
        )


def _check_comments(formula: str, issues: list[ValidationIssue]) -> None:
    if "//" in formula or "/*" in formula:
        issues.append(
            ValidationIssue(
                severity="info",
                code="contains_comment",
                message="Formula contains a comment; it will be stored verbatim.",
            )
        )


def validate_formula(
    formula: str, fields: list[FieldMetadata] | None = None
) -> FormulaValidationResult:
    """Validate a Tableau formula against a rule set.

    Args:
        formula: The formula text to validate.
        fields: Optional list of datasource fields for reference checking. When
            omitted, reference existence is not verified.

    Returns:
        A structured :class:`FormulaValidationResult`.
    """
    issues: list[ValidationIssue] = []
    stripped = formula.strip()

    if not stripped:
        issues.append(
            ValidationIssue(severity="error", code="empty_formula", message="Formula is empty.")
        )
        return FormulaValidationResult(is_valid=False, formula=formula, issues=issues)

    _check_balanced(formula, issues)
    dax = _check_dax(formula, issues)
    calls = _function_calls(formula)
    _check_division_by_zero(formula, issues)
    _check_aggregation_mix(formula, calls, issues)
    _check_comments(formula, issues)

    result = FormulaValidationResult(
        is_valid=True, formula=formula, issues=issues, dax_functions_detected=dax
    )

    if fields is not None:
        report = match_references(formula, fields)
        result.references = report
        for missing in report.missing:
            suggestion = None
            if missing in report.suggestions:
                suggestion = "Did you mean: " + ", ".join(report.suggestions[missing]) + "?"
            result.issues.append(
                ValidationIssue(
                    severity="error",
                    code="unknown_reference",
                    message=f"Referenced field '[{missing}]' was not found in the datasource.",
                    suggestion=suggestion,
                )
            )
        for ambiguous in report.ambiguous:
            result.issues.append(
                ValidationIssue(
                    severity="warning",
                    code="ambiguous_reference",
                    message=f"Field reference '[{ambiguous}]' matches more than one field.",
                )
            )

    result.is_valid = not result.has_errors
    return result
