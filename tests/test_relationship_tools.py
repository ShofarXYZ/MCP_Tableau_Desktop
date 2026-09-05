"""Tests for relationship_operations (List / Get / Update on the object-graph)."""

from __future__ import annotations

from tableau_mcp.models import RelationshipDefinition, RelationshipReference
from tableau_mcp.tools import relationship_tools
from tableau_mcp.tools.context import ToolContext


def test_list_detects_the_broken_condition(
    ctx: ToolContext, relationships_workbook: str
) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook, "List", "GA4", ctx=ctx
    )
    assert resp.success, resp.error
    assert len(resp.relationships) == 1

    rel = resp.relationships[0]
    assert {rel.from_object, rel.to_object} == {"mart_a", "mart_b"}
    assert rel.is_valid is False
    assert len(rel.conditions) == 1

    condition = rel.conditions[0]
    assert condition.from_field == "[id]"
    assert condition.from_field_valid is True
    assert condition.to_field == "[does_not_exist]"
    assert condition.to_field_valid is False


def test_get_filters_by_reference(ctx: ToolContext, relationships_workbook: str) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook,
        "Get",
        "GA4",
        references=[RelationshipReference(from_object="mart_a", to_object="mart_b")],
        ctx=ctx,
    )
    assert resp.success, resp.error
    assert len(resp.relationships) == 1

    # A reference to a pair with no relationship returns an empty list, not an error.
    resp_empty = relationship_tools.relationship_operations(
        relationships_workbook,
        "Get",
        "GA4",
        references=[RelationshipReference(from_object="mart_a", to_object="mart_a")],
        ctx=ctx,
    )
    assert resp_empty.success
    assert resp_empty.relationships == []


def test_update_fixes_the_broken_field_and_persists(
    ctx: ToolContext, relationships_workbook: str
) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook,
        "Update",
        "GA4",
        definitions=[
            RelationshipDefinition(
                from_object="mart_a",
                to_object="mart_b",
                from_field="[id]",
                to_field="[id (mart_b)]",
            )
        ],
        ctx=ctx,
    )
    assert resp.success, resp.error
    assert resp.applied is True
    assert resp.backup is not None
    assert len(resp.changes) == 1

    change = resp.changes[0]
    assert change.status == "updated"
    assert change.previous_from_field == "[id]"
    assert change.previous_to_field == "[does_not_exist]"
    assert change.new_from_field == "[id]"
    assert change.new_to_field == "[id (mart_b)]"

    # Re-read from disk: the relationship must now validate cleanly.
    listed = relationship_tools.relationship_operations(
        relationships_workbook, "List", "GA4", ctx=ctx
    )
    assert listed.success
    rel = listed.relationships[0]
    assert rel.is_valid is True
    assert rel.conditions[0].to_field == "[id (mart_b)]"


def test_update_rejects_unknown_field_without_writing(
    ctx: ToolContext, relationships_workbook: str
) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook,
        "Update",
        "GA4",
        definitions=[
            RelationshipDefinition(
                from_object="mart_a",
                to_object="mart_b",
                from_field="[id]",
                to_field="[totally_made_up]",
            )
        ],
        ctx=ctx,
    )
    assert not resp.success
    assert resp.applied is False
    assert resp.error is not None
    assert "totally_made_up" in resp.error.message
    # Candidates are listed so the caller never has to guess.
    assert "[id (mart_b)]" in resp.error.message

    # Nothing was written: the relationship is still broken exactly as before.
    listed = relationship_tools.relationship_operations(
        relationships_workbook, "List", "GA4", ctx=ctx
    )
    rel = listed.relationships[0]
    assert rel.is_valid is False
    assert rel.conditions[0].to_field == "[does_not_exist]"


def test_update_with_explicit_condition_index_out_of_range(
    ctx: ToolContext, relationships_workbook: str
) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook,
        "Update",
        "GA4",
        definitions=[
            RelationshipDefinition(
                from_object="mart_a",
                to_object="mart_b",
                from_field="[id]",
                to_field="[id (mart_b)]",
                condition_index=5,
            )
        ],
        ctx=ctx,
    )
    assert not resp.success
    assert resp.error is not None
    assert "out of range" in resp.error.message


def test_unknown_operation_is_rejected(ctx: ToolContext, relationships_workbook: str) -> None:
    resp = relationship_tools.relationship_operations(
        relationships_workbook, "Delete", "GA4", ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None


def test_datasource_name_required_when_ambiguous(
    ctx: ToolContext, multi_workbook: str
) -> None:
    resp = relationship_tools.relationship_operations(multi_workbook, "List", ctx=ctx)
    assert not resp.success
    assert resp.error is not None
