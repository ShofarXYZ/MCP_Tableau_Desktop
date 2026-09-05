"""Tools for listing datasources, fields, and calculated fields (read-only)."""

from __future__ import annotations

from ..exceptions import TableauMCPError
from ..logging_config import get_logger
from ..models import (
    ErrorInfo,
    FieldMetadata,
    FieldTypeFilter,
    ListCalculatedFieldsResponse,
    ListDatasourcesResponse,
    ListFieldsResponse,
)
from ..workbook.inspector import WorkbookInspector
from .context import ToolContext, get_context

logger = get_logger()


def _error(exc: TableauMCPError) -> ErrorInfo:
    return ErrorInfo(code=exc.code, message=exc.message)


def list_datasources(filename: str, ctx: ToolContext | None = None) -> ListDatasourcesResponse:
    """List the datasources of a workbook with their metadata."""
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        return ListDatasourcesResponse(
            success=True, filename=filename, datasources=inspector.datasource_metadata()
        )
    except TableauMCPError as exc:
        logger.error(
            "list_datasources failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return ListDatasourcesResponse(success=False, filename=filename, error=_error(exc))


def _matches_filter(field: FieldMetadata, field_type: FieldTypeFilter) -> bool:
    if field_type == "all":
        return True
    if field_type == "calculated":
        return field.kind == "calculated"
    if field_type == "parameter":
        return field.kind == "parameter"
    if field_type == "dimension":
        return field.role == "dimension"
    if field_type == "measure":
        return field.role == "measure"
    return True


def list_fields(
    filename: str,
    datasource_name: str,
    field_type: FieldTypeFilter = "all",
    ctx: ToolContext | None = None,
) -> ListFieldsResponse:
    """List the fields of one datasource, optionally filtered by type/role."""
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)
        fields = [f for f in inspector.fields_for_datasource(ds) if _matches_filter(f, field_type)]
        return ListFieldsResponse(
            success=True,
            filename=filename,
            datasource_name=datasource_name,
            fields=fields,
        )
    except TableauMCPError as exc:
        logger.error(
            "list_fields failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return ListFieldsResponse(
            success=False, filename=filename, datasource_name=datasource_name, error=_error(exc)
        )


def list_calculated_fields(
    filename: str, ctx: ToolContext | None = None
) -> ListCalculatedFieldsResponse:
    """List every calculated field across all datasources of a workbook."""
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        return ListCalculatedFieldsResponse(
            success=True, filename=filename, calculated_fields=inspector.calculated_fields()
        )
    except TableauMCPError as exc:
        logger.error(
            "list_calculated_fields failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return ListCalculatedFieldsResponse(success=False, filename=filename, error=_error(exc))
