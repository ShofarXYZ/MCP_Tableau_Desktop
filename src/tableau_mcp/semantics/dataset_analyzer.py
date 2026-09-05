"""Turn a datasource's fields into a semantic :class:`DatasetAnalysis`."""

from __future__ import annotations

from ..models import (
    ClassifiedField,
    Confidence,
    DatasetAnalysis,
    FieldMetadata,
)
from .field_classifier import classify_fields
from .field_index import FieldIndex
from .metric_catalog import suggest_metrics

# Semantic types that read as "measures" vs. "dimensions" for reporting.
_MEASURE_TYPES = frozenset(
    {"revenue", "cost", "profit", "discount", "quantity", "percentage", "generic_measure"}
)
_DIMENSION_TYPES = frozenset({"geo", "category", "generic_dimension"})


def _infer_domain(index: FieldIndex) -> tuple[str, Confidence]:
    """Infer a coarse business domain and a confidence from the field mix."""
    has_revenue = index.has("revenue")
    has_order = index.order_field() is not None
    has_quantity = index.has("quantity")
    if has_revenue and (has_order or has_quantity):
        return "Vendas", "high"
    if has_revenue:
        return "Vendas / Financeiro", "medium"
    if index.has("date") and (index.has("category") or index.has("generic_measure")):
        return "Séries temporais", "low"
    return "Genérico", "low"


def _only_physical(fields: list[FieldMetadata]) -> list[FieldMetadata]:
    """Keep physical fields (calculated fields and parameters are excluded)."""
    return [f for f in fields if f.kind == "physical"]


def _captions(classified: list[ClassifiedField]) -> list[str]:
    return [c.caption for c in classified]


def analyze_datasource(
    datasource_name: str,
    datasource_caption: str | None,
    fields: list[FieldMetadata],
) -> DatasetAnalysis:
    """Produce a :class:`DatasetAnalysis` for one datasource.

    Args:
        datasource_name: Internal datasource name.
        datasource_caption: Display caption, if any.
        fields: All fields of the datasource (physical ones are classified).

    Returns:
        The semantic analysis, including inferred domain and suggested labels.
    """
    classified = classify_fields(_only_physical(fields))
    index = FieldIndex(classified)
    domain, confidence = _infer_domain(index)

    dimensions = [c.caption for c in classified if c.semantic_type in _DIMENSION_TYPES]
    measures = [c.caption for c in classified if c.semantic_type in _MEASURE_TYPES]
    dates = _captions(index.all_of("date"))
    identifiers = _captions(index.all_of("identifier"))
    geo_fields = _captions(index.all_of("geo"))

    possible_metrics = [m.name for m in suggest_metrics(index)]

    # Suggested dimensions include date parts when a date is present.
    possible_dimensions = list(dict.fromkeys(dimensions))
    if dates:
        possible_dimensions.extend(["Ano", "Mês", "Semana"])

    return DatasetAnalysis(
        datasource_name=datasource_name,
        datasource_caption=datasource_caption,
        inferred_domain=domain,
        domain_confidence=confidence,
        fields=classified,
        dimensions=dimensions,
        measures=measures,
        dates=dates,
        identifiers=identifiers,
        geo_fields=geo_fields,
        possible_metrics=possible_metrics,
        possible_dimensions=possible_dimensions,
    )
