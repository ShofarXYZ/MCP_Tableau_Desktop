"""Rule-based catalog that turns a classified dataset into suggested KPIs.

Given the fields present (revenue, cost, discount, quantity, dates, ids, …) it
proposes business metrics with native Tableau formulas and a rationale. Formulas
are always self-contained (they reference physical fields only, never other
suggested metrics) so they can be created together in a single batch.
"""

from __future__ import annotations

from ..models import ClassifiedField, MetricSuggestion
from .field_index import FieldIndex


def _ref(field: ClassifiedField) -> str:
    """Return the bracketed reference used inside a Tableau formula."""
    return f"[{field.caption}]"


def suggest_metrics(index: FieldIndex) -> list[MetricSuggestion]:
    """Return the KPIs that make sense for the fields available in ``index``.

    Args:
        index: A :class:`FieldIndex` over the classified fields of a datasource.

    Returns:
        Ordered list of :class:`MetricSuggestion`. Metrics whose formula is
        ``None`` are conceptual (they need a filter/set or view context that a
        calculated field alone cannot express).
    """
    metrics: list[MetricSuggestion] = []

    rev = index.first_of("revenue")
    cost = index.first_of("cost")
    disc = index.first_of("discount")
    qty = index.first_of("quantity")
    profit = index.first_of("profit")
    date = index.first_of("date")
    order = index.order_field()
    customer = index.customer_field()
    product = index.product_field()
    channel = index.channel_field()
    category = index.first_of("category")
    geo = index.first_of("geo")

    def add(
        name: str,
        formula: str | None,
        rationale: str,
        category_label: str,
        *,
        requires_view_context: bool = False,
        datatype: str = "real",
    ) -> None:
        metrics.append(
            MetricSuggestion(
                name=name,
                formula=formula,
                rationale=rationale,
                category=category_label,
                requires_view_context=requires_view_context,
                datatype=datatype,
            )
        )

    # -- Core financial metrics -------------------------------------------
    if rev:
        add(
            "Receita Bruta",
            f"SUM({_ref(rev)})",
            f"Soma total de {rev.caption}; base de qualquer análise de vendas.",
            "financial",
        )
    if rev and disc:
        add(
            "Receita Líquida",
            f"SUM({_ref(rev)}) - SUM({_ref(disc)})",
            "Receita descontando os abatimentos aplicados.",
            "financial",
        )

    # Profit: prefer an explicit profit field, else derive from revenue - cost.
    if profit:
        add("Lucro", f"SUM({_ref(profit)})", "Soma do lucro informado no dataset.", "financial")
    elif rev and cost:
        add(
            "Lucro",
            f"SUM({_ref(rev)}) - SUM({_ref(cost)})",
            "Lucro estimado como receita menos custo.",
            "financial",
        )

    # Margin %.
    if rev and cost:
        add(
            "Margem %",
            f"IIF(SUM({_ref(rev)}) = 0, NULL, "
            f"(SUM({_ref(rev)}) - SUM({_ref(cost)})) / SUM({_ref(rev)}))",
            "Percentual de lucro sobre a receita (guardado contra divisão por zero).",
            "ratio",
        )
    elif rev and profit:
        add(
            "Margem %",
            f"IIF(SUM({_ref(rev)}) = 0, NULL, SUM({_ref(profit)}) / SUM({_ref(rev)}))",
            "Lucro informado dividido pela receita.",
            "ratio",
        )

    # -- Counts and averages ----------------------------------------------
    if order:
        add("Pedidos", f"COUNTD({_ref(order)})", f"Contagem distinta de {order.caption}.", "count")
    if customer:
        add(
            "Clientes Únicos",
            f"COUNTD({_ref(customer)})",
            f"Número de {customer.caption} distintos.",
            "count",
        )
    if qty:
        add(
            "Itens Vendidos",
            f"SUM({_ref(qty)})",
            f"Soma de {qty.caption}.",
            "count",
        )
    if rev and order:
        add(
            "Ticket Médio",
            f"IIF(COUNTD({_ref(order)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(order)}))",
            "Receita média por pedido.",
            "ratio",
        )
    if disc:
        add("Desconto Médio", f"AVG({_ref(disc)})", f"Média de {disc.caption}.", "financial")

    # -- Revenue per dimension (average revenue per distinct member) -------
    if rev and customer:
        add(
            "Receita por Cliente",
            f"IIF(COUNTD({_ref(customer)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(customer)}))",
            "Receita média gerada por cliente.",
            "ratio",
        )
    if rev and product:
        add(
            "Receita por Produto",
            f"IIF(COUNTD({_ref(product)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(product)}))",
            "Receita média por produto distinto.",
            "ratio",
        )
    if rev and category:
        add(
            "Receita por Categoria",
            f"IIF(COUNTD({_ref(category)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(category)}))",
            "Receita média por categoria distinta.",
            "ratio",
        )
    if rev and channel:
        add(
            "Receita por Canal",
            f"IIF(COUNTD({_ref(channel)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(channel)}))",
            "Receita média por canal distinto.",
            "ratio",
        )
    if rev and geo:
        add(
            "Receita por Estado",
            f"IIF(COUNTD({_ref(geo)}) = 0, NULL, SUM({_ref(rev)}) / COUNTD({_ref(geo)}))",
            f"Receita média por {geo.caption} distinto.",
            "ratio",
        )

    # -- Time intelligence (table calcs; need a date in the view) ---------
    if rev:
        add(
            "Running Total",
            f"RUNNING_SUM(SUM({_ref(rev)}))",
            "Receita acumulada; ordene por data na visualização.",
            "time",
            requires_view_context=True,
        )
    if rev and date:
        add(
            "MoM",
            f"IIF(LOOKUP(SUM({_ref(rev)}), -1) = 0, NULL, "
            f"(SUM({_ref(rev)}) - LOOKUP(SUM({_ref(rev)}), -1)) "
            f"/ ABS(LOOKUP(SUM({_ref(rev)}), -1)))",
            "Variação mês a mês; use com o eixo temporal ordenado por mês.",
            "time",
            requires_view_context=True,
        )
        add(
            "YoY",
            f"IIF(LOOKUP(SUM({_ref(rev)}), -12) = 0, NULL, "
            f"(SUM({_ref(rev)}) - LOOKUP(SUM({_ref(rev)}), -12)) "
            f"/ ABS(LOOKUP(SUM({_ref(rev)}), -12)))",
            "Variação ano a ano; use com granularidade mensal.",
            "time",
            requires_view_context=True,
        )

    # -- Participation and rankings ---------------------------------------
    if rev:
        add(
            "Participação %",
            f"SUM({_ref(rev)}) / TOTAL(SUM({_ref(rev)}))",
            "Participação de cada membro no total (percent of total).",
            "ratio",
            requires_view_context=True,
        )
        add(
            "Top N",
            None,
            "Ranking dos maiores contribuintes; implemente com um Set ou filtro Top N.",
            "ranking",
        )
        add(
            "Bottom N",
            None,
            "Ranking dos menores contribuintes; implemente com um Set ou filtro Bottom N.",
            "ranking",
        )

    return metrics


def creatable_metrics(metrics: list[MetricSuggestion]) -> list[MetricSuggestion]:
    """Filter to metrics that have a concrete formula and can be created."""
    return [m for m in metrics if m.formula]
