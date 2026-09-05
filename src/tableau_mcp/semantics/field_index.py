"""An index over classified fields for convenient, meaning-based lookups.

Both the metric catalog and the visualization advisor query fields by semantic
type or by business role (customer, order, product, channel) without assuming
any fixed column name.
"""

from __future__ import annotations

from ..models import ClassifiedField, SemanticType
from .normalization import tokens

# Business-role keyword sets used to pick representative fields for KPIs.
_CUSTOMER_KEYWORDS = frozenset({"cliente", "customer", "client", "comprador", "consumidor"})
_ORDER_KEYWORDS = frozenset({"pedido", "order", "venda", "sale", "nota", "invoice", "transacao"})
_PRODUCT_KEYWORDS = frozenset({"produto", "product", "item", "sku", "mercadoria"})
_CHANNEL_KEYWORDS = frozenset({"canal", "channel", "origem", "source", "midia", "media"})


class FieldIndex:
    """Groups classified fields and offers meaning-based accessors."""

    def __init__(self, fields: list[ClassifiedField]) -> None:
        """Build the index from already-classified fields."""
        self.fields = fields
        self.by_type: dict[SemanticType, list[ClassifiedField]] = {}
        for field in fields:
            self.by_type.setdefault(field.semantic_type, []).append(field)

    def all_of(self, semantic_type: SemanticType) -> list[ClassifiedField]:
        """Return every field of a given semantic type."""
        return self.by_type.get(semantic_type, [])

    def first_of(self, semantic_type: SemanticType) -> ClassifiedField | None:
        """Return the first field of a semantic type, if any."""
        items = self.by_type.get(semantic_type)
        return items[0] if items else None

    def has(self, semantic_type: SemanticType) -> bool:
        """Return True if at least one field of that semantic type exists."""
        return bool(self.by_type.get(semantic_type))

    def _find_by_keywords(self, keywords: frozenset[str]) -> ClassifiedField | None:
        """Find a field whose tokens intersect ``keywords``.

        Identifiers are preferred (e.g. an explicit OrderID over a free-text
        order description) because they count cleanly with COUNTD.
        """
        candidates = [f for f in self.fields if set(tokens(f.caption or f.name)) & keywords]
        if not candidates:
            return None
        candidates.sort(key=lambda f: 0 if f.semantic_type == "identifier" else 1)
        return candidates[0]

    def customer_field(self) -> ClassifiedField | None:
        """Return the field that best represents a customer."""
        return self._find_by_keywords(_CUSTOMER_KEYWORDS)

    def order_field(self) -> ClassifiedField | None:
        """Return the field that best represents an order/transaction."""
        found = self._find_by_keywords(_ORDER_KEYWORDS)
        if found is not None:
            return found
        # Fall back to any identifier if no explicit order field exists.
        return self.first_of("identifier")

    def product_field(self) -> ClassifiedField | None:
        """Return the field that best represents a product."""
        return self._find_by_keywords(_PRODUCT_KEYWORDS)

    def channel_field(self) -> ClassifiedField | None:
        """Return the field that best represents a sales channel."""
        return self._find_by_keywords(_CHANNEL_KEYWORDS)
