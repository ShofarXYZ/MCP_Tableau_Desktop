"""Construction and location of Tableau ``<column>`` calculated-field elements.

All XML manipulation goes through lxml; no regex is used to edit the document.
Internal field names are generated to be unique and collision-free without
relying on a fixed name like ``[Calculation_1]``.
"""

from __future__ import annotations

import uuid

from lxml import etree

from ..models import CalculatedFieldSpec

CALCULATION_CLASS = "tableau"


def _existing_names(datasource: etree._Element) -> set[str]:
    return {c.get("name") or "" for c in datasource.findall("column")}


def _existing_captions(datasource: etree._Element) -> dict[str, etree._Element]:
    """Map lower-cased caption -> column element for quick duplicate lookup."""
    result: dict[str, etree._Element] = {}
    for column in datasource.findall("column"):
        caption = column.get("caption")
        if caption:
            result[caption.lower()] = column
    return result


def find_column_by_caption(datasource: etree._Element, caption: str) -> etree._Element | None:
    """Return the column whose caption matches ``caption`` (case-insensitive), if any."""
    return _existing_captions(datasource).get(caption.strip().lower())


def is_calculated(column: etree._Element) -> bool:
    """Return True if the column carries a ``<calculation>`` child."""
    return column.find("calculation") is not None


def generate_internal_name(datasource: etree._Element) -> str:
    """Generate a unique internal field name for a new calculated field.

    The name follows Tableau's ``[Calculation_<hex>]`` convention but uses a
    random hex suffix, checked against existing column names to avoid collisions.
    """
    existing = _existing_names(datasource)
    while True:
        candidate = f"[Calculation_{uuid.uuid4().hex[:16]}]"
        if candidate not in existing:
            return candidate


def build_calculated_column(
    datasource: etree._Element, spec: CalculatedFieldSpec, internal_name: str
) -> etree._Element:
    """Build a ``<column>`` element for a calculated field (not yet attached).

    Args:
        datasource: The target datasource element (for context, not modified).
        spec: The calculated field specification.
        internal_name: Pre-generated unique internal name.

    Returns:
        A new detached ``<column>`` element with a ``<calculation>`` child.
    """
    column = etree.Element("column")
    column.set("caption", spec.field_name)
    column.set("datatype", spec.datatype)
    column.set("name", internal_name)
    column.set("role", spec.role)
    column.set("type", spec.field_type)

    calculation = etree.SubElement(column, "calculation")
    calculation.set("class", CALCULATION_CLASS)
    calculation.set("formula", spec.formula)

    if spec.description:
        desc = etree.SubElement(column, "desc")
        formatted = etree.SubElement(desc, "formatted-text")
        run = etree.SubElement(formatted, "run")
        run.text = spec.description

    return column


def attach_column(datasource: etree._Element, column: etree._Element) -> None:
    """Insert a ``<column>`` element after the last existing column in the datasource.

    If the datasource has no columns yet, the column is appended at the end.
    """
    columns = datasource.findall("column")
    if columns:
        last = columns[-1]
        last.addnext(column)
    else:
        datasource.append(column)


def references_field(formula: str, caption: str, internal_name: str) -> bool:
    """Return True if ``formula`` references a field by caption or internal name."""
    targets = {f"[{caption}]".lower()}
    stripped = internal_name.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        targets.add(stripped.lower())
    lowered = formula.lower()
    return any(target in lowered for target in targets)
