"""Tests for atomic writing, backup, restore, and rollback behavior."""

from __future__ import annotations

import pytest

from tableau_mcp.exceptions import ValidationError
from tableau_mcp.tools import calculation_tools, workbook_tools
from tableau_mcp.tools.context import ToolContext
from tableau_mcp.workbook.inspector import WorkbookInspector


def test_backup_created_on_write(ctx: ToolContext, single_workbook: str) -> None:
    resp = calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "X", "SUM([Receita])", ctx=ctx
    )
    assert resp.success
    backups = ctx.backups.list_backups(single_workbook)
    assert len(backups) >= 1


def test_manual_backup(ctx: ToolContext, single_workbook: str) -> None:
    resp = workbook_tools.backup_workbook(single_workbook, ctx)
    assert resp.success
    assert resp.backup is not None
    assert (ctx.backups.backups_dir / resp.backup.relative_path).exists()


def test_backup_names_are_unique(ctx: ToolContext, single_workbook: str) -> None:
    path = ctx.reader.resolve(single_workbook)
    b1 = ctx.backups.create_backup(path)
    b2 = ctx.backups.create_backup(path)
    assert b1.relative_path != b2.relative_path


def test_restore_requires_confirmation(ctx: ToolContext, single_workbook: str) -> None:
    b = workbook_tools.backup_workbook(single_workbook, ctx).backup
    assert b is not None
    resp = workbook_tools.restore_workbook_backup(
        single_workbook, b.relative_path, confirm=False, ctx=ctx
    )
    assert not resp.success
    assert resp.error is not None and resp.error.code == "confirmation_required"


def test_restore_roundtrip(ctx: ToolContext, single_workbook: str) -> None:
    backup = workbook_tools.backup_workbook(single_workbook, ctx).backup
    assert backup is not None
    # Mutate the workbook.
    calculation_tools.create_calculated_field(
        single_workbook, "Vendas", "Temp", "SUM([Receita])", ctx=ctx
    )
    # Restore original (which had no 'Temp').
    resp = workbook_tools.restore_workbook_backup(
        single_workbook, backup.relative_path, confirm=True, ctx=ctx
    )
    assert resp.success, resp.error
    assert resp.pre_restore_backup is not None
    _, tree = ctx.reader.load_tree(single_workbook)
    captions = {f.caption for f in WorkbookInspector(tree).all_fields()}
    assert "Temp" not in captions


def test_rollback_on_bad_mutation(ctx: ToolContext, single_workbook: str) -> None:
    path = ctx.reader.resolve(single_workbook)
    original = path.read_bytes()

    def corrupt(tree: object) -> None:
        raise ValidationError("boom")

    with pytest.raises(ValidationError):
        ctx.writer.apply(path, corrupt)  # type: ignore[arg-type]
    # File must remain untouched (mutation raised before any write).
    assert path.read_bytes() == original
