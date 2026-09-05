"""One-off script: add KPI-card and chart worksheets to GA4 - Wide.twb.

Follows the exact <worksheet>/<window> shape already proven to work in
space_dashboard_1.twb (reverse-engineered from a real Tableau-saved file,
not guessed), to avoid repeating the failures hit with the object-graph
relationships XML.
"""

from __future__ import annotations

import uuid

from lxml import etree

from tableau_mcp.tools.context import get_context

FILENAME = "GA4 - Wide.twb"
DS_CAPTION = "Marketing Wide"
DS_NAME = "federated.mktgwide"


def _uuid() -> str:
    return "{" + str(uuid.uuid4()).upper() + "}"


def _column(caption: str, datatype: str, name: str, role: str, field_type: str) -> etree._Element:
    return etree.Element(
        "column", caption=caption, datatype=datatype, name=name, role=role, type=field_type
    )


def _kpi_worksheet(name: str, field_name: str, field_caption: str, datatype: str) -> etree._Element:
    """A single-value 'KPI card' worksheet: one measure on the Text shelf, no rows/cols."""
    ws = etree.Element("worksheet", name=name)
    table = etree.SubElement(ws, "table")
    view = etree.SubElement(table, "view")
    datasources = etree.SubElement(view, "datasources")
    etree.SubElement(datasources, "datasource", caption=DS_CAPTION, name=DS_NAME)
    deps = etree.SubElement(view, "datasource-dependencies", datasource=DS_NAME)
    deps.append(_column(field_caption, datatype, field_name, "measure", "quantitative"))
    etree.SubElement(view, "aggregation", value="true")
    etree.SubElement(table, "style")
    panes = etree.SubElement(table, "panes")
    pane = etree.SubElement(panes, "pane", **{"selection-relaxation-option": "selection-relaxation-allow"})
    pane_view = etree.SubElement(pane, "view")
    etree.SubElement(pane_view, "breakdown", value="auto")
    etree.SubElement(pane, "mark", **{"class": "Text"})
    encodings = etree.SubElement(pane, "encodings")
    etree.SubElement(encodings, "text", column=f"[{DS_NAME}].[{field_name.strip('[]')}]")
    etree.SubElement(table, "rows")
    etree.SubElement(table, "cols")
    etree.SubElement(ws, "simple-id", uuid=_uuid())
    return ws


def _line_worksheet() -> etree._Element:
    """Sessions by day: [event_date] on Cols, [sessions] on Rows, Line mark."""
    ws = etree.Element("worksheet", name="Sessões por Dia")
    table = etree.SubElement(ws, "table")
    view = etree.SubElement(table, "view")
    datasources = etree.SubElement(view, "datasources")
    etree.SubElement(datasources, "datasource", caption=DS_CAPTION, name=DS_NAME)
    deps = etree.SubElement(view, "datasource-dependencies", datasource=DS_NAME)
    deps.append(_column("Sessions", "integer", "[sessions]", "measure", "quantitative"))
    deps.append(_column("Event Date", "date", "[event_date]", "dimension", "ordinal"))
    etree.SubElement(view, "aggregation", value="true")
    etree.SubElement(table, "style")
    panes = etree.SubElement(table, "panes")
    pane = etree.SubElement(panes, "pane", **{"selection-relaxation-option": "selection-relaxation-allow"})
    pane_view = etree.SubElement(pane, "view")
    etree.SubElement(pane_view, "breakdown", value="auto")
    etree.SubElement(pane, "mark", **{"class": "Line"})
    etree.SubElement(table, "rows").text = f"[{DS_NAME}].[sessions]"
    etree.SubElement(table, "cols").text = f"[{DS_NAME}].[event_date]"
    etree.SubElement(ws, "simple-id", uuid=_uuid())
    return ws


def _channel_bar_worksheet() -> etree._Element:
    """Revenue by traffic source: [traffic_source] on Rows, [revenue_usd] on Cols (horizontal bar)."""
    ws = etree.Element("worksheet", name="Receita por Canal")
    table = etree.SubElement(ws, "table")
    view = etree.SubElement(table, "view")
    datasources = etree.SubElement(view, "datasources")
    etree.SubElement(datasources, "datasource", caption=DS_CAPTION, name=DS_NAME)
    deps = etree.SubElement(view, "datasource-dependencies", datasource=DS_NAME)
    deps.append(_column("Revenue Usd", "real", "[revenue_usd]", "measure", "quantitative"))
    deps.append(_column("Traffic Source", "string", "[traffic_source]", "dimension", "nominal"))
    etree.SubElement(view, "aggregation", value="true")
    etree.SubElement(table, "style")
    panes = etree.SubElement(table, "panes")
    pane = etree.SubElement(panes, "pane", **{"selection-relaxation-option": "selection-relaxation-allow"})
    pane_view = etree.SubElement(pane, "view")
    etree.SubElement(pane_view, "breakdown", value="auto")
    etree.SubElement(pane, "mark", **{"class": "Bar"})
    etree.SubElement(table, "rows").text = f"[{DS_NAME}].[traffic_source]"
    etree.SubElement(table, "cols").text = f"[{DS_NAME}].[revenue_usd]"
    etree.SubElement(ws, "simple-id", uuid=_uuid())
    return ws


def _window_for(worksheet_name: str) -> etree._Element:
    window = etree.Element("window", **{"class": "worksheet", "name": worksheet_name})
    cards = etree.SubElement(window, "cards")
    left = etree.SubElement(cards, "edge", name="left")
    strip = etree.SubElement(left, "strip", size="160")
    etree.SubElement(strip, "card", type="pages")
    etree.SubElement(strip, "card", type="filters")
    etree.SubElement(strip, "card", type="marks")
    top = etree.SubElement(cards, "edge", name="top")
    strip_cols = etree.SubElement(top, "strip", size="2147483647")
    etree.SubElement(strip_cols, "card", type="columns")
    strip_rows = etree.SubElement(top, "strip", size="2147483647")
    etree.SubElement(strip_rows, "card", type="rows")
    strip_title = etree.SubElement(top, "strip", size="31")
    etree.SubElement(strip_title, "card", type="title")
    etree.SubElement(window, "simple-id", uuid=_uuid())
    return window


KPI_FIELDS = [
    ("KPI - Sessões", "[sessions]", "Sessions", "integer"),
    ("KPI - Usuários", "[users]", "Users", "integer"),
    ("KPI - Compras", "[purchase]", "Purchase", "integer"),
    ("KPI - Taxa de Conversão", "[pct_view_to_purchase]", "Pct View To Purchase", "real"),
    ("KPI - Sessões Engajadas", "[pct_engaged_sessions]", "Pct Engaged Sessions", "real"),
    ("KPI - Receita", "[revenue_usd]", "Revenue Usd", "real"),
]


def mutation(mutable_tree: etree._ElementTree) -> None:
    root = mutable_tree.getroot()
    worksheets_el = root.find("worksheets")
    if worksheets_el is None:
        worksheets_el = etree.SubElement(root, "worksheets")

    names: list[str] = []
    for name, field_name, caption, datatype in KPI_FIELDS:
        worksheets_el.append(_kpi_worksheet(name, field_name, caption, datatype))
        names.append(name)
    worksheets_el.append(_line_worksheet())
    names.append("Sessões por Dia")
    worksheets_el.append(_channel_bar_worksheet())
    names.append("Receita por Canal")

    windows_el = root.find("windows")
    if windows_el is None:
        windows_el = etree.SubElement(root, "windows")
    for name in names:
        windows_el.append(_window_for(name))


def main() -> None:
    ctx = get_context()
    path = ctx.reader.resolve(FILENAME)
    backup = ctx.writer.apply(path, mutation)
    print("Applied. Backup:", backup.relative_path)


if __name__ == "__main__":
    main()
