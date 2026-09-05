"""Normalization helpers for name-based heuristics.

Field names arrive in many shapes (``ValorVenda``, ``valor_venda``, ``[Order ID]``,
``RECEITA``). These helpers reduce them to a comparable, accent-free token set so
the classifier can match keywords regardless of casing, separators, or language.
"""

from __future__ import annotations

import re
import unicodedata

# Split on camelCase boundaries and non-alphanumeric separators.
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_SEPARATORS = re.compile(r"[^0-9A-Za-zÀ-ÿ]+")


def strip_accents(text: str) -> str:
    """Return ``text`` with diacritics removed (``Região`` -> ``Regiao``)."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def strip_brackets(name: str) -> str:
    """Remove the surrounding Tableau brackets from an internal field name."""
    trimmed = name.strip()
    if trimmed.startswith("[") and trimmed.endswith("]"):
        return trimmed[1:-1]
    return trimmed


def normalize(name: str) -> str:
    """Return a lowercase, accent-free, space-collapsed form of ``name``."""
    base = strip_accents(strip_brackets(name))
    base = _CAMEL_BOUNDARY.sub(" ", base)
    base = _SEPARATORS.sub(" ", base)
    return base.strip().lower()


def tokens(name: str) -> list[str]:
    """Return the normalized whitespace-separated tokens of ``name``."""
    normalized = normalize(name)
    return [t for t in normalized.split(" ") if t]
