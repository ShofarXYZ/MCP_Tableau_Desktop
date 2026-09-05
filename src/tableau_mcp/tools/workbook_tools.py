"""Tools that operate on whole workbooks: listing, inspection, backup, restore."""

from __future__ import annotations

from ..exceptions import BackupError, ConfirmationRequiredError, TableauMCPError
from ..logging_config import get_logger
from ..models import (
    BackupResponse,
    ErrorInfo,
    InspectWorkbookResponse,
    ListWorkbooksResponse,
    RestoreResponse,
)
from ..workbook.inspector import WorkbookInspector
from .context import ToolContext, get_context

logger = get_logger()


def _error(exc: TableauMCPError) -> ErrorInfo:
    return ErrorInfo(code=exc.code, message=exc.message)


def list_workbooks(ctx: ToolContext | None = None) -> ListWorkbooksResponse:
    """List the ``.twb`` files available in the authorized folder."""
    ctx = ctx or get_context()
    try:
        workbooks = ctx.reader.list_workbooks()
        return ListWorkbooksResponse(success=True, workbooks=workbooks)
    except TableauMCPError as exc:
        logger.error("list_workbooks failed", extra={"context": {"error": exc.code}})
        return ListWorkbooksResponse(success=False, error=_error(exc))


def inspect_workbook(filename: str, ctx: ToolContext | None = None) -> InspectWorkbookResponse:
    """Inspect a workbook without modifying it."""
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        return InspectWorkbookResponse(
            success=True,
            filename=filename,
            datasources=inspector.datasource_metadata(),
            worksheets=inspector.worksheet_names(),
            dashboards=inspector.dashboard_names(),
            fields=inspector.all_fields(),
        )
    except TableauMCPError as exc:
        logger.error(
            "inspect_workbook failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return InspectWorkbookResponse(success=False, filename=filename, error=_error(exc))


def backup_workbook(filename: str, ctx: ToolContext | None = None) -> BackupResponse:
    """Create a manual, timestamped backup of a workbook."""
    ctx = ctx or get_context()
    try:
        path = ctx.reader.resolve(filename)
        backup = ctx.backups.create_backup(path)
        logger.info(
            "backup_workbook created",
            extra={"context": {"workbook": filename, "backup": backup.relative_path}},
        )
        return BackupResponse(success=True, backup=backup)
    except TableauMCPError as exc:
        logger.error(
            "backup_workbook failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return BackupResponse(success=False, error=_error(exc))


def restore_workbook_backup(
    filename: str,
    backup_name: str | None = None,
    confirm: bool = False,
    ctx: ToolContext | None = None,
) -> RestoreResponse:
    """Restore a workbook from a backup.

    If ``backup_name`` is omitted, the available backups are listed instead of
    restoring. Restoration requires ``confirm=True`` and first snapshots the
    current state into a new backup.
    """
    ctx = ctx or get_context()
    try:
        available = ctx.backups.list_backups(filename)
        if backup_name is None:
            return RestoreResponse(success=True, available_backups=available)

        if not confirm:
            raise ConfirmationRequiredError(
                "Restoration requires 'confirm=true'. This overwrites the current workbook."
            )

        target_path = ctx.reader.resolve(filename)
        source = ctx.backups.resolve_backup(backup_name)

        # Snapshot current state before overwriting.
        pre_restore = ctx.backups.create_backup(target_path)

        data = source.read_bytes()
        ctx.writer.write_validated_bytes(target_path, data)  # validate + atomic replace
        logger.info(
            "restore_workbook_backup applied",
            extra={
                "context": {
                    "workbook": filename,
                    "restored_from": backup_name,
                    "pre_restore_backup": pre_restore.relative_path,
                }
            },
        )
        return RestoreResponse(
            success=True,
            restored_from=backup_name,
            pre_restore_backup=pre_restore,
            available_backups=available,
        )
    except (TableauMCPError, BackupError) as exc:
        logger.error(
            "restore_workbook_backup failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return RestoreResponse(success=False, error=_error(exc))
