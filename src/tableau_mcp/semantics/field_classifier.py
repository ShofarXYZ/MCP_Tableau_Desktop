"""Heuristic classification of physical fields into business (semantic) types.

Classification never relies on fixed column names. It combines:

* **keyword matching** on accent-free, camelCase-split tokens (Portuguese +
  English), e.g. ``ValorVenda`` -> {valor, venda} -> revenue;
* **datatype signals**, e.g. a ``date``/``datetime`` datatype implies a date;
* **role fallback**, mapping Tableau measure/dimension roles onto generic types.

Each result carries a confidence and a short human-readable reason.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from ..models import ClassifiedField, Confidence, FieldMetadata, SemanticType
from .normalization import normalize, tokens

# Ordered (type, keyword-set) rules. The first matching rule wins, so more
# specific financial concepts are listed before generic ones.
_KEYWORD_RULES: list[tuple[SemanticType, frozenset[str]]] = [
    (
        "discount",
        frozenset({"discount", "desconto", "desc", "abatimento", "rebate"}),
    ),
    (
        "profit",
        frozenset({"profit", "lucro", "resultado", "ganho", "netincome"}),
    ),
    (
        "cost",
        frozenset({"cost", "custo", "cogs", "cmv", "despesa", "expense", "gasto"}),
    ),
    (
        "revenue",
        frozenset(
            {
                "revenue",
                "receita",
                "sales",
                "sale",
                "venda",
                "vendas",
                "faturamento",
                "gmv",
                "amount",
                "montante",
                "valor",
                "valorvenda",
                "price",
                "preco",
                "ticket",
                "billing",
            }
        ),
    ),
    (
        "quantity",
        frozenset(
            {
                "quantity",
                "quantidade",
                "qtd",
                "qtde",
                "qty",
                "units",
                "unidades",
                "itens",
                "items",
                "volume",
            }
        ),
    ),
    (
        "percentage",
        frozenset(
            {
                "percent",
                "percentual",
                "pct",
                "perc",
                "taxa",
                "rate",
                "ratio",
                "margem",
                "margin",
                "share",
                "participacao",
            }
        ),
    ),
    (
        "geo",
        frozenset(
            {
                "estado",
                "state",
                "uf",
                "pais",
                "country",
                "city",
                "cidade",
                "municipio",
                "region",
                "regiao",
                "zip",
                "cep",
                "postal",
                "latitude",
                "longitude",
                "lat",
                "lng",
                "lon",
                "geo",
                "bairro",
                "endereco",
                "address",
                "continente",
                "continent",
            }
        ),
    ),
    (
        "category",
        frozenset(
            {
                "categoria",
                "category",
                "tipo",
                "type",
                "segment",
                "segmento",
                "canal",
                "channel",
                "produto",
                "product",
                "marca",
                "brand",
                "departamento",
                "department",
                "grupo",
                "group",
                "status",
                "classe",
                "class",
                "genero",
                "gender",
                "cliente",
                "customer",
                "client",
                "vendedor",
                "seller",
                "fornecedor",
                "supplier",
                "nome",
                "name",
            }
        ),
    ),
]

# Tokens that clearly indicate dates (checked with datatype as reinforcement).
_DATE_KEYWORDS: frozenset[str] = frozenset(
    {
        "date",
        "data",
        "dt",
        "dia",
        "day",
        "mes",
        "month",
        "ano",
        "year",
        "periodo",
        "period",
        "timestamp",
        "datetime",
        "hora",
        "time",
        "week",
        "semana",
        "trimestre",
        "quarter",
    }
)

_ID_KEYWORDS: frozenset[str] = frozenset(
    {"id", "key", "chave", "codigo", "code", "cod", "sku", "uuid", "guid"}
)

_DATE_DATATYPES: frozenset[str] = frozenset({"date", "datetime"})


def _is_identifier(field_tokens: list[str]) -> bool:
    return any(tok in _ID_KEYWORDS or (tok.endswith("id") and len(tok) > 2) for tok in field_tokens)


def _match_keyword_rule(field_tokens: list[str]) -> SemanticType | None:
    token_set = set(field_tokens)
    for semantic_type, keywords in _KEYWORD_RULES:
        if token_set & keywords:
            return semantic_type
    return None


def classify_field(field: FieldMetadata) -> ClassifiedField:
    """Classify a single field into a :class:`ClassifiedField`.

    Args:
        field: Field metadata from the inspector.

    Returns:
        The field annotated with a semantic type, confidence, and reason.
    """
    caption = field.caption or normalize(field.name) or field.name
    field_tokens = tokens(field.caption or field.name)
    datatype = (field.datatype or "").lower()

    semantic_type: SemanticType = "unknown"
    confidence: Confidence = "low"
    reason = ""

    # 1. Dates (name keyword, or datatype signal).
    if set(field_tokens) & _DATE_KEYWORDS or datatype in _DATE_DATATYPES:
        semantic_type = "date"
        confidence = "high" if datatype in _DATE_DATATYPES else "medium"
        reason = "Name/datatype indicates a date field."

    # 2. Identifiers (before financial, so 'OrderID' is an id, not revenue).
    elif _is_identifier(field_tokens):
        semantic_type = "identifier"
        confidence = "high"
        reason = "Name contains an id/key token."

    # 3. Keyword-based business concepts.
    else:
        matched = _match_keyword_rule(field_tokens)
        if matched is not None:
            semantic_type = matched
            confidence = "high"
            reason = f"Name keyword matches '{matched}'."

    # 4. Role-based fallback.
    if semantic_type == "unknown":
        if field.role == "measure":
            semantic_type = "generic_measure"
            confidence = "low"
            reason = "Tableau role is 'measure'."
        elif field.role == "dimension":
            semantic_type = "generic_dimension"
            confidence = "low"
            reason = "Tableau role is 'dimension'."

    return ClassifiedField(
        name=field.name,
        caption=caption,
        datatype=field.datatype,
        role=field.role,
        semantic_type=semantic_type,
        confidence=confidence,
        reason=reason,
    )


def classify_fields(fields: list[FieldMetadata]) -> list[ClassifiedField]:
    """Classify a list of fields (physical fields only are meaningful here)."""
    return [classify_field(f) for f in fields]


def name_similarity(a: str, b: str) -> float:
    """Return a 0..1 similarity ratio between two normalized names."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()
