"""Diagnose and repair broken Relationships (object-graph) field bindings.

When a remote table's schema changes (a column renamed, or newly disambiguated
by Tableau because two tables now share a column name), a datasource built
with Relationships can end up with a ``<relationship>`` whose join expression
points at a field that no longer exists on one side. Tableau then shows
"Este relacionamento faz referência a um campo desconhecido" for that pair of
tables. This module lets that be listed and fixed without hand-editing XML.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..exceptions import TableauMCPError
from ..logging_config import get_logger
from ..models import (
    ErrorInfo,
    RelationshipChange,
    RelationshipCondition,
    RelationshipDefinition,
    RelationshipInfo,
    RelationshipOperationsResponse,
    RelationshipReference,
)
from ..workbook.inspector import WorkbookInspector
from ..workbook.object_graph import (
    equality_leaves,
    find_relationship_element,
    list_relationships,
    valid_field_refs_for_relation,
)
from .context import ToolContext, get_context

logger = get_logger()


def _error(exc: TableauMCPError) -> ErrorInfo:
    return ErrorInfo(code=exc.code, message=exc.message)


def _resolve_datasource_name(
    inspector: WorkbookInspector, datasource_name: str | None
) -> str:
    """Return the datasource name to operate on, requiring an explicit name when ambiguous."""
    if datasource_name:
        return inspector.find_datasource(datasource_name).get("name") or datasource_name

    datasources = inspector.datasource_elements()
    if len(datasources) == 1:
        return datasources[0].get("name") or ""

    labels = ", ".join(ds.get("caption") or ds.get("name") or "(unnamed)" for ds in datasources)
    raise TableauMCPError(
        f"'datasource_name' is required: workbook has {len(datasources)} datasources "
        f"({labels})."
    )


def _matches_reference(info: RelationshipInfo, ref: RelationshipReference) -> bool:
    a, b = ref.from_object.strip().lower(), ref.to_object.strip().lower()
    x, y = info.from_object.strip().lower(), info.to_object.strip().lower()
    return {a, b} == {x, y}


def _relation_names_for_pair(
    ds: etree._Element, from_object: str, to_object: str
) -> tuple[str | None, str | None]:
    """Resolve the physical relation names backing two table captions."""
    from ..workbook.object_graph import find_object_by_caption, relation_name_for_object

    from_obj = find_object_by_caption(ds, from_object)
    to_obj = find_object_by_caption(ds, to_object)
    return relation_name_for_object(from_obj), relation_name_for_object(to_obj)


def relationship_operations(
    filename: str,
    operation: str,
    datasource_name: str | None = None,
    references: list[RelationshipReference] | None = None,
    definitions: list[RelationshipDefinition] | None = None,
    ctx: ToolContext | None = None,
) -> RelationshipOperationsResponse:
    """List, inspect, or repair Relationships (object-graph) field bindings.

    Args:
        filename: The ``.twb`` workbook to operate on.
        operation: One of ``"List"``, ``"Get"``, ``"Update"``.
        datasource_name: Required when the workbook has more than one datasource.
        references: For ``"Get"`` — pairs of table captions to filter to.
        definitions: For ``"Update"`` — the field-binding fixes to apply.
    """
    ctx = ctx or get_context()
    op = (operation or "").strip()
    try:
        if op not in ("List", "Get", "Update"):
            raise TableauMCPError(
                f"Unknown operation '{operation}'. Expected 'List', 'Get', or 'Update'."
            )

        path, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        resolved_name = _resolve_datasource_name(inspector, datasource_name)
        ds = inspector.find_datasource(resolved_name)

        if op == "List":
            return RelationshipOperationsResponse(
                success=True,
                filename=filename,
                datasource_name=resolved_name,
                operation="List",
                relationships=list_relationships(ds),
            )

        if op == "Get":
            if not references:
                raise TableauMCPError("'references' is required for the 'Get' operation.")
            all_rels = list_relationships(ds)
            selected = [
                info
                for info in all_rels
                if any(_matches_reference(info, ref) for ref in references)
            ]
            return RelationshipOperationsResponse(
                success=True,
                filename=filename,
                datasource_name=resolved_name,
                operation="Get",
                relationships=selected,
            )

        # -- Update ----------------------------------------------------------
        if not definitions:
            raise TableauMCPError("'definitions' is required for the 'Update' operation.")

        return _apply_updates(ctx, path, filename, resolved_name, ds, definitions)

    except TableauMCPError as exc:
        logger.error(
            "relationship_operations failed",
            extra={"context": {"workbook": filename, "operation": operation, "error": exc.code}},
        )
        return RelationshipOperationsResponse(
            success=False, filename=filename, operation=op or None, error=_error(exc)
        )


def _plan_update(
    ds: etree._Element, definition: RelationshipDefinition
) -> tuple[etree._Element, bool, int, RelationshipCondition]:
    """Locate the relationship + condition targeted by one definition, without mutating.

    Raises:
        TableauMCPError subclasses on any unresolved object, relationship,
        out-of-range condition, or invalid new field name (never guessed).
    """
    rel_el, swapped = find_relationship_element(ds, definition.from_object, definition.to_object)
    from_relation, to_relation = _relation_names_for_pair(
        ds, definition.from_object, definition.to_object
    )
    # is_swapped means from_object is actually the relationship's second end-point.
    from_relation_side, to_relation_side = (
        (to_relation, from_relation) if swapped else (from_relation, to_relation)
    )

    leaves = equality_leaves(rel_el.find("expression"))
    if not leaves:
        raise TableauMCPError(
            f"Relationship '{definition.from_object}' <-> '{definition.to_object}' has no "
            "equality conditions to update."
        )

    condition_index = definition.condition_index
    if condition_index is None:
        for i, leaf in enumerate(leaves):
            sides = leaf.findall("expression")
            left = sides[0].get("op") if len(sides) > 0 else None
            right = sides[1].get("op") if len(sides) > 1 else None
            left_ok = left in valid_field_refs_for_relation(ds, from_relation_side or "")
            right_ok = right in valid_field_refs_for_relation(ds, to_relation_side or "")
            if not (left_ok and right_ok):
                condition_index = i
                break
        if condition_index is None:
            raise TableauMCPError(
                f"Relationship '{definition.from_object}' <-> '{definition.to_object}' has no "
                "broken condition; pass 'condition_index' explicitly to force an update."
            )
    elif condition_index < 0 or condition_index >= len(leaves):
        raise TableauMCPError(
            f"'condition_index' {condition_index} is out of range "
            f"(relationship has {len(leaves)} condition(s))."
        )

    # Validate the new field values against the *real* physical table each
    # side belongs to. Never guess: list the real candidates on failure.
    if from_relation_side and definition.from_field not in valid_field_refs_for_relation(
        ds, from_relation_side
    ):
        candidates = sorted(valid_field_refs_for_relation(ds, from_relation_side))
        raise TableauMCPError(
            f"'{definition.from_field}' is not a known column of '{definition.from_object}'. "
            f"Candidates: {', '.join(candidates) or '(none)'}."
        )
    if to_relation_side and definition.to_field not in valid_field_refs_for_relation(
        ds, to_relation_side
    ):
        candidates = sorted(valid_field_refs_for_relation(ds, to_relation_side))
        raise TableauMCPError(
            f"'{definition.to_field}' is not a known column of '{definition.to_object}'. "
            f"Candidates: {', '.join(candidates) or '(none)'}."
        )

    leaf = leaves[condition_index]
    sides = leaf.findall("expression")
    left = sides[0].get("op") if len(sides) > 0 else None
    right = sides[1].get("op") if len(sides) > 1 else None
    previous = RelationshipCondition(
        from_field=(right if swapped else left),
        to_field=(left if swapped else right),
    )
    return rel_el, swapped, condition_index, previous


def _apply_updates(
    ctx: ToolContext,
    path: Path,
    filename: str,
    datasource_name: str,
    ds: etree._Element,
    definitions: list[RelationshipDefinition],
) -> RelationshipOperationsResponse:
    from ..exceptions import TableauMCPError as _Err

    changes: list[RelationshipChange] = []
    planned: list[tuple[RelationshipDefinition, int, bool]] = []

    # --- Pre-validate everything (no mutation yet) --------------------------
    for definition in definitions:
        try:
            _rel_el, swapped, condition_index, previous = _plan_update(ds, definition)
        except _Err as exc:
            return RelationshipOperationsResponse(
                success=False,
                filename=filename,
                datasource_name=datasource_name,
                operation="Update",
                error=_error(exc),
                changes=[
                    RelationshipChange(
                        from_object=definition.from_object,
                        to_object=definition.to_object,
                        condition_index=definition.condition_index,
                        status="failed",
                        detail=exc.message,
                    )
                ],
                applied=False,
            )
        planned.append((definition, condition_index, swapped))
        changes.append(
            RelationshipChange(
                from_object=definition.from_object,
                to_object=definition.to_object,
                condition_index=condition_index,
                previous_from_field=previous.from_field,
                previous_to_field=previous.to_field,
                new_from_field=definition.from_field,
                new_to_field=definition.to_field,
                status="skipped",  # flipped to "updated" only after the write succeeds
            )
        )

    # --- Single atomic write -------------------------------------------------
    def mutation(mutable_tree: etree._ElementTree) -> None:
        target_ds = WorkbookInspector(mutable_tree).find_datasource(datasource_name)
        for definition, condition_index, swapped in planned:
            rel_el, _ = find_relationship_element(
                target_ds, definition.from_object, definition.to_object
            )
            leaves = equality_leaves(rel_el.find("expression"))
            leaf = leaves[condition_index]
            sides = leaf.findall("expression")
            left_new, right_new = (
                (definition.to_field, definition.from_field)
                if swapped
                else (definition.from_field, definition.to_field)
            )
            sides[0].set("op", left_new)
            sides[1].set("op", right_new)

    backup = ctx.writer.apply(path, mutation)
    for change in changes:
        change.status = "updated"

    logger.info(
        "relationship_operations Update applied",
        extra={
            "context": {
                "workbook": filename,
                "datasource": datasource_name,
                "count": len(planned),
                "backup": backup.relative_path,
            }
        },
    )
    return RelationshipOperationsResponse(
        success=True,
        filename=filename,
        datasource_name=datasource_name,
        operation="Update",
        changes=changes,
        backup=backup,
        applied=True,
    )
