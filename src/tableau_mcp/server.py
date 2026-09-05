"""FastMCP server exposing Tableau workbook tools over the stdio transport.

Run with::

    python -m tableau_mcp.server

The server never prints to stdout (reserved for the MCP protocol); all logging
goes to stderr and the rotating log file.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .logging_config import configure_logging
from .models import (
    AnalyzeDatasetResponse,
    BackupResponse,
    BatchMutationResponse,
    CalculatedFieldSpec,
    InspectWorkbookResponse,
    ListCalculatedFieldsResponse,
    ListDatasourcesResponse,
    ListFieldsResponse,
    ListWorkbooksResponse,
    MutationResponse,
    RelationshipDefinition,
    RelationshipOperationsResponse,
    RelationshipReference,
    RestoreResponse,
    SuggestMetricsResponse,
    SuggestVisualizationsResponse,
    ValidateFormulaResponse,
)
from .models import (
    FieldTypeFilter as FieldTypeFilterT,
)
from .tools import (
    analytics_tools,
    calculation_tools,
    field_tools,
    relationship_tools,
    workbook_tools,
)

_settings = get_settings()
configure_logging(_settings.logs_path, _settings.log_level)

mcp = FastMCP("tableau-desktop-mcp")


# ---------------------------------------------------------------------------
# Workbook tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_workbooks() -> ListWorkbooksResponse:
    """List the .twb workbooks available in the authorized folder."""
    return workbook_tools.list_workbooks()


@mcp.tool()
def inspect_workbook(filename: str) -> InspectWorkbookResponse:
    """Inspect a workbook (datasources, worksheets, dashboards, fields) without changing it."""
    return workbook_tools.inspect_workbook(filename)


@mcp.tool()
def backup_workbook(filename: str) -> BackupResponse:
    """Create a manual timestamped backup of a workbook."""
    return workbook_tools.backup_workbook(filename)


@mcp.tool()
def restore_workbook_backup(
    filename: str, backup_name: str | None = None, confirm: bool = False
) -> RestoreResponse:
    """List backups (no backup_name) or restore one (requires confirm=true)."""
    return workbook_tools.restore_workbook_backup(filename, backup_name, confirm)


# ---------------------------------------------------------------------------
# Field tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_datasources(filename: str) -> ListDatasourcesResponse:
    """List the datasources of a workbook."""
    return field_tools.list_datasources(filename)


@mcp.tool()
def list_fields(
    filename: str, datasource_name: str, field_type: FieldTypeFilterT = "all"
) -> ListFieldsResponse:
    """List the fields of a datasource, optionally filtered by type/role."""
    return field_tools.list_fields(filename, datasource_name, field_type)


@mcp.tool()
def list_calculated_fields(filename: str) -> ListCalculatedFieldsResponse:
    """List all calculated fields across the workbook's datasources."""
    return field_tools.list_calculated_fields(filename)


# ---------------------------------------------------------------------------
# Calculation tools
# ---------------------------------------------------------------------------


@mcp.tool()
def validate_tableau_formula(
    formula: str, filename: str | None = None, datasource_name: str | None = None
) -> ValidateFormulaResponse:
    """Validate a Tableau formula (brackets, DAX, references) without modifying anything."""
    return calculation_tools.validate_tableau_formula(formula, filename, datasource_name)


@mcp.tool()
def create_calculated_field(
    filename: str,
    datasource_name: str,
    field_name: str,
    formula: str,
    datatype: str = "real",
    role: str = "measure",
    field_type: str = "quantitative",
    description: str | None = None,
) -> MutationResponse:
    """Create a calculated field using native Tableau syntax (backup + atomic write)."""
    return calculation_tools.create_calculated_field(
        filename, datasource_name, field_name, formula, datatype, role, field_type, description
    )


@mcp.tool()
def update_calculated_field(
    filename: str, datasource_name: str, field_name: str, formula: str
) -> MutationResponse:
    """Update an existing calculated field's formula (backup + before/after report)."""
    return calculation_tools.update_calculated_field(filename, datasource_name, field_name, formula)


@mcp.tool()
def delete_calculated_field(
    filename: str, datasource_name: str, field_name: str, confirm: bool = False
) -> MutationResponse:
    """Delete a calculated field only (physical columns are protected; requires confirm=true)."""
    return calculation_tools.delete_calculated_field(filename, datasource_name, field_name, confirm)


@mcp.tool()
def create_calculated_fields_batch(
    filename: str, datasource_name: str, fields: list[CalculatedFieldSpec]
) -> BatchMutationResponse:
    """Create several calculated fields atomically (all validated first, single backup)."""
    return calculation_tools.create_calculated_fields_batch(filename, datasource_name, fields)


# ---------------------------------------------------------------------------
# Analytics Copilot tools
# ---------------------------------------------------------------------------


@mcp.tool()
def analyze_dataset(filename: str, datasource_name: str | None = None) -> AnalyzeDatasetResponse:
    """Semantically analyze a dataset: classify fields and infer the business domain."""
    return analytics_tools.analyze_dataset(filename, datasource_name)


@mcp.tool()
def suggest_business_metrics(filename: str, datasource_name: str) -> SuggestMetricsResponse:
    """Suggest business KPIs (with native Tableau formulas and rationale) for a datasource."""
    return analytics_tools.suggest_business_metrics(filename, datasource_name)


@mcp.tool()
def create_recommended_metrics(filename: str, datasource_name: str) -> BatchMutationResponse:
    """Create all recommended, formula-backed metrics atomically (single backup)."""
    return analytics_tools.create_recommended_metrics(filename, datasource_name)


@mcp.tool()
def suggest_visualizations(filename: str, datasource_name: str) -> SuggestVisualizationsResponse:
    """Recommend the best chart types for a datasource, each with a justification."""
    return analytics_tools.suggest_visualizations(filename, datasource_name)


# ---------------------------------------------------------------------------
# Relationship (object-graph) tools
# ---------------------------------------------------------------------------


@mcp.tool()
def relationship_operations(
    filename: str,
    operation: str,
    datasource_name: str | None = None,
    references: list[RelationshipReference] | None = None,
    definitions: list[RelationshipDefinition] | None = None,
) -> RelationshipOperationsResponse:
    """List, inspect, or repair Relationships (object-graph) field bindings.

    operation is one of "List" (all relationships + validity), "Get"
    (filtered by references: [{from_object, to_object}]), or "Update" (apply
    definitions: [{from_object, to_object, from_field, to_field}], backup +
    atomic write, before/after report).
    """
    return relationship_tools.relationship_operations(
        filename, operation, datasource_name, references, definitions
    )


def main() -> None:
    """Entry point: run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
