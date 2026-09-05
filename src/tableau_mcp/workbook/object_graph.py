"""Parsing and validation of a datasource's ``<object-graph>`` (Relationships model).

A federated Tableau datasource built with *Relationships* (not classic joins)
stores its physical tables as ``<object>`` entries and the links between them
as ``<relationship>`` entries, both inside ``<datasource><object-graph>``::

    <object-graph>
      <objects>
        <object caption='mart_ecommerce_sales' id='mart_ecommerce_sales (...)_ABC'>
          <properties context=''>
            <relation connection='databricks.xyz' name='mart_ecommerce_sales'
                      table='[ga4].[gold].[mart_ecommerce_sales]' type='table' />
          </properties>
        </object>
        ...
      </objects>
      <relationships>
        <relationship>
          <expression op='='>
            <expression op='[mart_ecommerce_sales].[item_id]' />
            <expression op='[mart_item_performance].[item_id]' />
          </expression>
          <first-end-point object-id='mart_ecommerce_sales (...)_ABC' />
          <second-end-point object-id='mart_item_performance (...)_DEF' />
        </relationship>
      </relationships>
    </object-graph>

A relationship's join expression is either a bare ``op='='`` (single
condition) or an ``op='AND'`` wrapping several ``op='='`` children (a
compound/multi-field join).

The authoritative list of *valid* physical field references for a given table
lives in the datasource-level ``<cols><map key='...' value='[table].[col]'/>``
table: every local (possibly disambiguated) field name is mapped to its
``[table].[column]`` physical origin. This module uses that map to tell a
relationship condition referencing a real column apart from one referencing a
column that no longer exists (the "unknown field" case Tableau reports after
a remote schema change).
"""

from __future__ import annotations

from lxml import etree

from ..exceptions import (
    AmbiguousFieldError,
    ObjectGraphNotFoundError,
    RelationshipNotFoundError,
    RelationshipObjectNotFoundError,
)
from ..models import RelationshipCondition, RelationshipInfo

# ---------------------------------------------------------------------------
# <objects> / <object>
# ---------------------------------------------------------------------------


def find_object_graph(ds: etree._Element) -> etree._Element | None:
    """Return the datasource's ``<object-graph>`` element, if it uses Relationships."""
    return ds.find("object-graph")


def list_graph_objects(ds: etree._Element) -> list[etree._Element]:
    """Return every ``<object>`` declared in the datasource's object-graph."""
    graph = find_object_graph(ds)
    if graph is None:
        return []
    objects = graph.find("objects")
    if objects is None:
        return []
    return objects.findall("object")


def object_caption(obj: etree._Element) -> str:
    """Return an ``<object>``'s display caption, falling back to its id."""
    return obj.get("caption") or obj.get("id") or ""


def find_object_by_id(ds: etree._Element, object_id: str | None) -> etree._Element | None:
    """Return the ``<object>`` with the given ``id``, or ``None`` if not found."""
    if not object_id:
        return None
    for obj in list_graph_objects(ds):
        if obj.get("id") == object_id:
            return obj
    return None


def find_object_by_caption(ds: etree._Element, caption: str) -> etree._Element:
    """Resolve a table caption to its ``<object>`` element.

    Raises:
        ObjectGraphNotFoundError: If the datasource has no object-graph.
        RelationshipObjectNotFoundError: If no object (or more than one) matches.
    """
    graph = find_object_graph(ds)
    if graph is None:
        raise ObjectGraphNotFoundError(
            f"Datasource '{ds.get('caption') or ds.get('name')}' has no <object-graph> "
            "(it is not built with Relationships)."
        )
    wanted = caption.strip().lower()
    matches = [o for o in list_graph_objects(ds) if object_caption(o).strip().lower() == wanted]
    if not matches:
        available = ", ".join(object_caption(o) for o in list_graph_objects(ds)) or "(none)"
        raise RelationshipObjectNotFoundError(
            f"Table '{caption}' not found in the object-graph. Available: {available}."
        )
    if len(matches) > 1:
        raise AmbiguousFieldError(
            f"Table caption '{caption}' matches {len(matches)} objects; captions are not unique."
        )
    return matches[0]


def relation_name_for_object(obj: etree._Element) -> str | None:
    """Return the physical ``<relation name='...'>`` backing an ``<object>``, if any."""
    relation = obj.find("properties/relation")
    if relation is None:
        return None
    return relation.get("name")


# ---------------------------------------------------------------------------
# <cols> map (local field name -> '[table].[remote column]')
# ---------------------------------------------------------------------------


def cols_map(ds: etree._Element) -> dict[str, str]:
    """Return the datasource's ``<cols>`` map: local field name -> physical origin.

    ``<cols>`` lives nested inside ``<connection class='federated'>``, not as a
    direct child of ``<datasource>``, so this searches at any depth.
    """
    result: dict[str, str] = {}
    cols = ds.find(".//cols")
    if cols is None:
        return result
    for entry in cols.findall("map"):
        key, value = entry.get("key"), entry.get("value")
        if key and value:
            result[key] = value
    return result


def valid_field_refs_for_relation(ds: etree._Element, relation_name: str) -> set[str]:
    """Return every field-reference spelling accepted for one physical table.

    Includes both the fully qualified ``[relation].[col]`` form and the local
    (possibly disambiguated) name Tableau actually assigned that column, as
    recorded by the ``<cols>`` map's ``key`` -> ``value`` pairs (e.g. a column
    named ``id`` on two related tables becomes local name ``[id]`` on one and
    ``[id (mart_b)]`` on the other -- never a synthesized/guessed spelling).
    """
    valid: set[str] = set()
    prefix = f"[{relation_name}]."
    for key, value in cols_map(ds).items():
        if value.startswith(prefix):
            valid.add(value)
            valid.add(key)
    return valid


def is_field_valid_for_relation(
    ds: etree._Element, relation_name: str | None, field_ref: str | None
) -> bool:
    """Return True if ``field_ref`` resolves to a real column of ``relation_name``."""
    if not relation_name or not field_ref:
        return False
    return field_ref in valid_field_refs_for_relation(ds, relation_name)


# ---------------------------------------------------------------------------
# <relationships> / <relationship>
# ---------------------------------------------------------------------------


def equality_leaves(expr: etree._Element | None) -> list[etree._Element]:
    """Flatten a join expression into its ``op='='`` leaves.

    Handles a bare ``op='='`` expression as well as an ``op='AND'`` wrapping
    several ``op='='`` children (a compound/multi-field join).
    """
    if expr is None:
        return []
    op = expr.get("op")
    if op == "AND":
        leaves: list[etree._Element] = []
        for child in expr.findall("expression"):
            leaves.extend(equality_leaves(child))
        return leaves
    if op == "=":
        return [expr]
    return []


def relationship_elements(ds: etree._Element) -> list[etree._Element]:
    """Return every ``<relationship>`` element in the datasource's object-graph."""
    graph = find_object_graph(ds)
    if graph is None:
        return []
    relationships = graph.find("relationships")
    if relationships is None:
        return []
    return relationships.findall("relationship")


def parse_relationship(ds: etree._Element, rel: etree._Element, index: int) -> RelationshipInfo:
    """Parse one ``<relationship>`` element into a :class:`RelationshipInfo`."""
    top_expr = rel.find("expression")
    fep = rel.find("first-end-point")
    sep = rel.find("second-end-point")
    from_id = fep.get("object-id") if fep is not None else None
    to_id = sep.get("object-id") if sep is not None else None

    from_obj = find_object_by_id(ds, from_id)
    to_obj = find_object_by_id(ds, to_id)
    from_caption = object_caption(from_obj) if from_obj is not None else (from_id or "?")
    to_caption = object_caption(to_obj) if to_obj is not None else (to_id or "?")
    from_relation = relation_name_for_object(from_obj) if from_obj is not None else None
    to_relation = relation_name_for_object(to_obj) if to_obj is not None else None

    conditions: list[RelationshipCondition] = []
    for leaf in equality_leaves(top_expr):
        sides = leaf.findall("expression")
        left = sides[0].get("op") if len(sides) > 0 else None
        right = sides[1].get("op") if len(sides) > 1 else None
        conditions.append(
            RelationshipCondition(
                from_field=left,
                to_field=right,
                from_field_valid=is_field_valid_for_relation(ds, from_relation, left),
                to_field_valid=is_field_valid_for_relation(ds, to_relation, right),
            )
        )

    is_valid = bool(conditions) and all(
        c.from_field_valid and c.to_field_valid for c in conditions
    )
    return RelationshipInfo(
        index=index,
        from_object=from_caption,
        to_object=to_caption,
        from_object_id=from_id or "",
        to_object_id=to_id or "",
        conditions=conditions,
        is_valid=is_valid,
    )


def list_relationships(ds: etree._Element) -> list[RelationshipInfo]:
    """Return every relationship of a datasource, parsed and validity-checked."""
    return [
        parse_relationship(ds, rel, i) for i, rel in enumerate(relationship_elements(ds))
    ]


def find_relationship_element(
    ds: etree._Element, from_object: str, to_object: str
) -> tuple[etree._Element, bool]:
    """Locate the ``<relationship>`` element connecting two table captions.

    The pair is order-insensitive: ``(A, B)`` matches a relationship stored as
    either ``first=A, second=B`` or ``first=B, second=A``.

    Returns:
        A tuple of ``(element, is_swapped)`` where ``is_swapped`` is True when
        the requested ``from_object`` matches the relationship's
        *second*-end-point (so callers know which expression side is which).

    Raises:
        RelationshipObjectNotFoundError: If either caption is not a known table.
        RelationshipNotFoundError: If no relationship connects the two tables.
    """
    from_obj = find_object_by_caption(ds, from_object)
    to_obj = find_object_by_caption(ds, to_object)
    from_id, to_id = from_obj.get("id"), to_obj.get("id")

    for rel in relationship_elements(ds):
        fep = rel.find("first-end-point")
        sep = rel.find("second-end-point")
        fep_id = fep.get("object-id") if fep is not None else None
        sep_id = sep.get("object-id") if sep is not None else None
        if fep_id == from_id and sep_id == to_id:
            return rel, False
        if fep_id == to_id and sep_id == from_id:
            return rel, True

    raise RelationshipNotFoundError(
        f"No relationship connects '{from_object}' and '{to_object}'."
    )
