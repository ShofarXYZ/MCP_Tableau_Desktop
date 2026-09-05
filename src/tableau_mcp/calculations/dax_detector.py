"""Detection of Power BI / DAX syntax inside a (supposedly) Tableau formula.

Tableau formulas must never contain DAX. This module flags common DAX functions
and patterns while trying to avoid false positives (e.g. it only matches whole
words, ignoring content inside ``[bracketed field references]`` and quoted
strings).
"""

from __future__ import annotations

import re

#: DAX functions that do not exist in Tableau (or mean something different).
DAX_FUNCTIONS: frozenset[str] = frozenset(
    {
        "SUMX",
        "AVERAGEX",
        "COUNTX",
        "MINX",
        "MAXX",
        "CALCULATE",
        "CALCULATETABLE",
        "FILTER",
        "ALL",
        "ALLEXCEPT",
        "ALLSELECTED",
        "RELATED",
        "RELATEDTABLE",
        "DIVIDE",
        "DISTINCTCOUNT",
        "SELECTEDVALUE",
        "SWITCH",
        "VAR",
        "RETURN",
        "EARLIER",
        "EARLIEST",
        "VALUES",
        "SUMMARIZE",
        "ADDCOLUMNS",
        "RANKX",
        "TOPN",
        "KEEPFILTERS",
        "USERELATIONSHIP",
        "HASONEVALUE",
        "ISFILTERED",
        "ISINSCOPE",
    }
)

#: ``Table[Column]`` reference style is DAX, not Tableau. The identifier must be
#: immediately adjacent to '[' (no whitespace), which distinguishes it from a
#: Tableau expression like ``IF [Field] ...`` where a space precedes the bracket.
_TABLE_COLUMN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\[[^\]]+\]")

# Matches [bracketed references] and 'single' / "double" quoted strings so they
# can be stripped before scanning for function keywords.
_MASK_PATTERN = re.compile(r"\[[^\]]*\]|'[^']*'|\"[^\"]*\"")


def _mask_literals(formula: str) -> str:
    """Replace bracketed references and quoted strings with spaces of equal length."""
    return _MASK_PATTERN.sub(lambda m: " " * len(m.group(0)), formula)


def detect_dax_functions(formula: str) -> list[str]:
    """Return a sorted list of DAX function names found in ``formula``.

    Field references and string literals are masked first to avoid matching a
    DAX keyword that merely appears inside a field name (e.g. ``[All Regions]``).
    """
    masked = _mask_literals(formula)
    tokens = {t.upper() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", masked)}
    return sorted(tokens & DAX_FUNCTIONS)


def has_table_column_reference(formula: str) -> bool:
    """Return True if the formula uses DAX-style ``Table[Column]`` references.

    A Tableau reference is ``[Field]`` with no identifier immediately before the
    opening bracket, so we detect an identifier directly preceding ``[``.
    """
    for match in _TABLE_COLUMN_PATTERN.finditer(formula):
        start = match.start()
        # Ensure the char before the identifier isn't part of a longer bracket ref.
        if start == 0 or formula[start - 1] not in "]":
            return True
    return False
