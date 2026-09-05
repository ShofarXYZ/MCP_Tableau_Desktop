"""Parsing and matching of ``[Field]`` references inside Tableau formulas."""

from __future__ import annotations

import re
from difflib import get_close_matches

from ..models import FieldMetadata, FieldReferenceReport

# A Tableau field reference is any text between square brackets, e.g. [Receita].
# Field names may contain spaces, accents, and most punctuation except ']'.
_REFERENCE_PATTERN = re.compile(r"\[([^\[\]]+)\]")

# Quoted strings are masked first so a ']' inside a string literal is ignored.
_STRING_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")


def _mask_strings(formula: str) -> str:
    return _STRING_PATTERN.sub(lambda m: " " * len(m.group(0)), formula)


def extract_references(formula: str) -> list[str]:
    """Return the distinct field names referenced in ``formula`` (order-preserving)."""
    masked = _mask_strings(formula)
    seen: dict[str, None] = {}
    for match in _REFERENCE_PATTERN.finditer(masked):
        seen.setdefault(match.group(1).strip(), None)
    return list(seen.keys())


def _field_labels(fields: list[FieldMetadata]) -> tuple[dict[str, int], list[str]]:
    """Build a case-insensitive label->count map and a display label list.

    A field is addressable by its caption (preferred) or by its internal name
    with the surrounding brackets stripped.
    """
    counts: dict[str, int] = {}
    labels: list[str] = []
    for field in fields:
        for label in _addressable_labels(field):
            key = label.lower()
            counts[key] = counts.get(key, 0) + 1
            labels.append(label)
    return counts, labels


def _addressable_labels(field: FieldMetadata) -> list[str]:
    labels: list[str] = []
    if field.caption:
        labels.append(field.caption)
    internal = field.name.strip()
    if internal.startswith("[") and internal.endswith("]"):
        internal = internal[1:-1]
    if internal and internal not in labels:
        labels.append(internal)
    return labels


def match_references(formula: str, fields: list[FieldMetadata]) -> FieldReferenceReport:
    """Match formula references against the fields available in a datasource.

    Args:
        formula: The Tableau formula to inspect.
        fields: All fields (physical, calculated, parameter) of the datasource.

    Returns:
        A :class:`FieldReferenceReport` categorizing each reference as found,
        missing, or ambiguous, with similarity-based suggestions for missing ones.
    """
    counts, all_labels = _field_labels(fields)
    report = FieldReferenceReport()
    for ref in extract_references(formula):
        occurrences = counts.get(ref.lower(), 0)
        if occurrences == 1:
            report.found.append(ref)
        elif occurrences > 1:
            report.ambiguous.append(ref)
        else:
            report.missing.append(ref)
            matches = get_close_matches(ref, all_labels, n=3, cutoff=0.6)
            if matches:
                report.suggestions[ref] = matches
    return report
