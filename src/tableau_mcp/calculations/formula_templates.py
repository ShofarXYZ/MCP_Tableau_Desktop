"""Known Tableau function names and reusable formula templates.

These lists are intentionally non-exhaustive; they power heuristics (e.g.
"is this an aggregate?") rather than a full compiler.
"""

from __future__ import annotations

#: Common Tableau aggregate functions.
AGGREGATE_FUNCTIONS: frozenset[str] = frozenset(
    {
        "SUM",
        "AVG",
        "MEDIAN",
        "COUNT",
        "COUNTD",
        "MIN",
        "MAX",
        "STDEV",
        "STDEVP",
        "VAR",
        "VARP",
        "ATTR",
        "PERCENTILE",
        "CORR",
        "COVAR",
        "COVARP",
    }
)

#: Common Tableau non-aggregate / scalar functions (subset).
SCALAR_FUNCTIONS: frozenset[str] = frozenset(
    {
        "ABS",
        "CEILING",
        "FLOOR",
        "ROUND",
        "SQRT",
        "SQUARE",
        "POWER",
        "EXP",
        "LN",
        "LOG",
        "SIGN",
        "LEN",
        "LEFT",
        "RIGHT",
        "MID",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "UPPER",
        "LOWER",
        "CONTAINS",
        "STARTSWITH",
        "ENDSWITH",
        "FIND",
        "REPLACE",
        "SPLIT",
        "IF",
        "IIF",
        "CASE",
        "WHEN",
        "THEN",
        "ELSE",
        "ELSEIF",
        "END",
        "ISNULL",
        "IFNULL",
        "ZN",
        "AND",
        "OR",
        "NOT",
        "DATEPART",
        "DATEADD",
        "DATEDIFF",
        "DATENAME",
        "DATETRUNC",
        "TODAY",
        "NOW",
        "YEAR",
        "MONTH",
        "DAY",
        "STR",
        "INT",
        "FLOAT",
        "MAKEDATE",
        "MAKETIME",
    }
)

#: Level-of-detail keywords (reserved for future LOD support).
LOD_KEYWORDS: frozenset[str] = frozenset({"FIXED", "INCLUDE", "EXCLUDE"})

#: Ready-to-use formula templates keyed by a short slug.
FORMULA_TEMPLATES: dict[str, str] = {
    "sum": "SUM([{field}])",
    "average": "AVG([{field}])",
    "distinct_count": "COUNTD([{field}])",
    "ratio": "SUM([{numerator}]) / SUM([{denominator}])",
    "safe_ratio": "IIF(SUM([{denominator}]) = 0, NULL, SUM([{numerator}]) / SUM([{denominator}]))",
    "average_per_id": "SUM([{value}]) / COUNTD([{id}])",
}


def render_template(slug: str, **fields: str) -> str:
    """Render a named template with ``field`` placeholders.

    Raises:
        KeyError: If the template slug is unknown.
    """
    return FORMULA_TEMPLATES[slug].format(**fields)
