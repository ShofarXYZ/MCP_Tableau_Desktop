"""Recommend chart types for the analyses a dataset supports.

Each recommendation pairs a measure with a dimension (or time axis) and explains
why the chosen mark fits — line for trends, bar for category comparison, map for
geography, KPI for single headline numbers.
"""

from __future__ import annotations

from ..models import VisualizationSuggestion
from .field_index import FieldIndex


def suggest_visualizations(index: FieldIndex) -> list[VisualizationSuggestion]:
    """Return chart recommendations appropriate for the fields in ``index``."""
    suggestions: list[VisualizationSuggestion] = []

    rev = index.first_of("revenue")
    cost = index.first_of("cost")
    profit = index.first_of("profit")
    date = index.first_of("date")
    category = index.first_of("category")
    geo = index.first_of("geo")
    product = index.product_field()
    channel = index.channel_field()
    customer = index.customer_field()
    order = index.order_field()

    rev_label = rev.caption if rev else "Receita"

    if rev and date:
        suggestions.append(
            VisualizationSuggestion(
                title=f"{rev_label} Mensal",
                chart_type="line",
                rationale="Séries temporais revelam tendência e sazonalidade ao longo do tempo.",
                measures=[rev_label],
                dimensions=[date.caption],
            )
        )
    if rev and category:
        suggestions.append(
            VisualizationSuggestion(
                title=f"{rev_label} por Categoria",
                chart_type="bar",
                rationale="Barras comparam com precisão valores entre poucas categorias.",
                measures=[rev_label],
                dimensions=[category.caption],
            )
        )
    if rev and geo:
        suggestions.append(
            VisualizationSuggestion(
                title=f"{rev_label} por {geo.caption}",
                chart_type="map",
                rationale="Campos geográficos ganham contexto espacial em um mapa.",
                measures=[rev_label],
                dimensions=[geo.caption],
            )
        )
    if rev and product:
        suggestions.append(
            VisualizationSuggestion(
                title="Top Produtos",
                chart_type="horizontal_bar",
                rationale="Barras horizontais ordenam bem rankings com rótulos longos.",
                measures=[rev_label],
                dimensions=[product.caption],
            )
        )
    if rev and channel:
        suggestions.append(
            VisualizationSuggestion(
                title=f"{rev_label} por Canal",
                chart_type="bar",
                rationale="Comparação direta da contribuição de cada canal.",
                measures=[rev_label],
                dimensions=[channel.caption],
            )
        )
    if rev and order:
        suggestions.append(
            VisualizationSuggestion(
                title="Ticket Médio",
                chart_type="kpi",
                rationale="Número único de destaque; um KPI comunica de imediato.",
                measures=["Ticket Médio"],
            )
        )
    if customer:
        suggestions.append(
            VisualizationSuggestion(
                title="Clientes",
                chart_type="kpi",
                rationale="Contagem única de clientes é um indicador de topo (headline).",
                measures=["Clientes Únicos"],
            )
        )
    if profit or (rev and cost):
        suggestions.append(
            VisualizationSuggestion(
                title="Lucro",
                chart_type="area",
                rationale="Área enfatiza volume acumulado de lucro ao longo do tempo.",
                measures=["Lucro"],
                dimensions=[date.caption] if date else [],
            )
        )
    if rev and cost:
        suggestions.append(
            VisualizationSuggestion(
                title="Margem",
                chart_type="line",
                rationale="A evolução da margem percentual é melhor lida como linha.",
                measures=["Margem %"],
                dimensions=[date.caption] if date else [],
            )
        )

    return suggestions
