"""Workbook-level XML validation (well-formedness and basic Tableau structure)."""

from __future__ import annotations

from lxml import etree

from ..exceptions import ValidationError
from .xml_utils import parse_bytes


def validate_workbook_bytes(data: bytes) -> etree._ElementTree:
    """Validate that ``data`` is well-formed XML with a Tableau root element.

    Args:
        data: Serialized workbook bytes.

    Returns:
        The parsed ElementTree on success.

    Raises:
        ValidationError: If the bytes are not well-formed or lack a ``<workbook>`` root.
    """
    try:
        tree = parse_bytes(data)
    except Exception as exc:
        raise ValidationError(f"Serialized workbook is not valid XML: {exc}") from exc

    root = tree.getroot()
    if root.tag != "workbook":
        raise ValidationError(f"Unexpected root element '{root.tag}'; expected '<workbook>'.")
    return tree


def validate_tree_structure(tree: etree._ElementTree) -> None:
    """Perform light structural sanity checks on a parsed workbook tree.

    Raises:
        ValidationError: If the root element is not ``<workbook>``.
    """
    root = tree.getroot()
    if root.tag != "workbook":
        raise ValidationError(f"Unexpected root element '{root.tag}'; expected '<workbook>'.")
