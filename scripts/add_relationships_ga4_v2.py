"""One-off script: add the 5 GA4 gold-mart relationships to a clean ga4_v2.twb.

Uses the same backup + atomic-write + validate + rollback pipeline as every
other mutation in this codebase (ctx.writer.apply), so a failure never leaves
the workbook corrupted.
"""

from __future__ import annotations

from lxml import etree

from tableau_mcp.tools.context import get_context
from tableau_mcp.workbook.inspector import WorkbookInspector

FILENAME = "ga4_v2.twb"
DATASOURCE_NAME = "federated.18fni8u0ih03l818a6ip01b6pli0"

OBJECT_IDS = {
    "mart_customer_ltv": "mart_customer_ltv (ga4.gold.mart_customer_ltv)_51EB485EF4D4497697E59ECB12A38959",
    "mart_device_geo": "mart_device_geo (ga4.gold.mart_device_geo)_CCAD884F2E944648B4E8977D2E1C2FA4",
    "mart_ecommerce_sales": "mart_ecommerce_sales (ga4.gold.mart_ecommerce_sales)_12F4022A025D4D0F9939FC99A587AB99",
    "mart_funnel_conversion": "mart_funnel_conversion (ga4.gold.mart_funnel_conversion)_E067FD0B523D46358E1D72E2E46FCCEC",
    "mart_item_performance": "mart_item_performance (ga4.gold.mart_item_performance)_3C65856E843B44C4B9B6B720A8D55B76",
    "mart_traffic_acquisition": "mart_traffic_acquisition (ga4.gold.mart_traffic_acquisition)_5835128773094F858E7980A4C7A54AF4",
    "mart_user_engagement": "mart_user_engagement (ga4.gold.mart_user_engagement)_F4BB5A5A075443A49DFDFC6CC7199B05",
}

# (from_table, to_table, [(from_field, to_field), ...])
RELATIONSHIPS = [
    ("mart_ecommerce_sales", "mart_item_performance", [("item_id", "item_id")]),
    ("mart_ecommerce_sales", "mart_funnel_conversion", [("event_date", "event_date")]),
    (
        "mart_funnel_conversion",
        "mart_traffic_acquisition",
        [
            ("event_date", "event_date"),
            ("traffic_source", "traffic_source"),
            ("traffic_medium", "traffic_medium"),
        ],
    ),
    ("mart_traffic_acquisition", "mart_device_geo", [("event_date", "event_date")]),
    ("mart_user_engagement", "mart_customer_ltv", [("user_pseudo_id", "user_pseudo_id")]),
]


def build_relationship(from_table: str, to_table: str, fields: list[tuple[str, str]]) -> etree._Element:
    rel = etree.Element("relationship")
    if len(fields) == 1:
        from_field, to_field = fields[0]
        expr = etree.SubElement(rel, "expression", op="=")
        etree.SubElement(expr, "expression", op=f"[{from_table}].[{from_field}]")
        etree.SubElement(expr, "expression", op=f"[{to_table}].[{to_field}]")
    else:
        expr = etree.SubElement(rel, "expression", op="AND")
        for from_field, to_field in fields:
            eq = etree.SubElement(expr, "expression", op="=")
            etree.SubElement(eq, "expression", op=f"[{from_table}].[{from_field}]")
            etree.SubElement(eq, "expression", op=f"[{to_table}].[{to_field}]")
    etree.SubElement(rel, "first-end-point", **{"object-id": OBJECT_IDS[from_table]})
    etree.SubElement(rel, "second-end-point", **{"object-id": OBJECT_IDS[to_table]})
    return rel


def mutation(mutable_tree: etree._ElementTree) -> None:
    ds = WorkbookInspector(mutable_tree).find_datasource(DATASOURCE_NAME)
    graph = ds.find("object-graph")
    assert graph is not None
    relationships = etree.SubElement(graph, "relationships")
    for from_table, to_table, fields in RELATIONSHIPS:
        relationships.append(build_relationship(from_table, to_table, fields))


def main() -> None:
    ctx = get_context()
    path = ctx.reader.resolve(FILENAME)
    backup = ctx.writer.apply(path, mutation)
    print("Applied. Backup:", backup.relative_path)


if __name__ == "__main__":
    main()
