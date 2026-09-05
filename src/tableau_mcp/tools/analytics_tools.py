"""Analytics Copilot tools: semantic analysis, KPI/viz suggestions, and one-shot creation.

These tools sit on top of the existing inspection and calculated-field machinery.
``create_recommended_metrics`` reuses :func:`create_calculated_fields_batch`, so
the safe write flow (validate-all → single backup → atomic write) is not
duplicated here.
"""

from __future__ import annotations

from ..exceptions import TableauMCPError
from ..logging_config import get_logger
from ..models import (
    AnalyzeDatasetResponse,
    BatchMutationResponse,
    ErrorInfo,
    SuggestMetricsResponse,
    SuggestVisualizationsResponse,
)
from ..semantics.dataset_analyzer import analyze_datasource
from ..semantics.field_classifier import classify_fields
from ..semantics.field_index import FieldIndex
from ..semantics.metric_catalog import creatable_metrics, suggest_metrics
from ..semantics.visualization_advisor import suggest_visualizations as advise_visualizations
from ..workbook.inspector import WorkbookInspector
from .calculation_tools import create_calculated_fields_batch
from .context import ToolContext, get_context

logger = get_logger()


def _error(exc: TableauMCPError) -> ErrorInfo:
    return ErrorInfo(code=exc.code, message=exc.message)


def _physical_index(ctx: ToolContext, filename: str, datasource_name: str) -> FieldIndex:
    """Load a datasource and build a semantic index over its physical fields."""
    _, tree = ctx.reader.load_tree(filename)
    inspector = WorkbookInspector(tree)
    ds = inspector.find_datasource(datasource_name)
    physical = [f for f in inspector.fields_for_datasource(ds) if f.kind == "physical"]
    return FieldIndex(classify_fields(physical))


def analyze_dataset(
    filename: str,
    datasource_name: str | None = None,
    ctx: ToolContext | None = None,
) -> AnalyzeDatasetResponse:
    """Semantically analyze one or all datasources of a workbook.

    Args:
        filename: Workbook to analyze.
        datasource_name: Restrict to a single datasource; ``None`` analyzes all.
        ctx: Optional injected context (for tests).
    """
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        datasources = inspector.datasource_elements()
        if datasource_name is not None:
            datasources = [inspector.find_datasource(datasource_name)]

        analyses = [
            analyze_datasource(
                ds.get("name") or "",
                ds.get("caption"),
                inspector.fields_for_datasource(ds),
            )
            for ds in datasources
        ]
        logger.info(
            "analyze_dataset completed",
            extra={"context": {"workbook": filename, "datasources": len(analyses)}},
        )
        return AnalyzeDatasetResponse(success=True, filename=filename, analyses=analyses)
    except TableauMCPError as exc:
        logger.error(
            "analyze_dataset failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return AnalyzeDatasetResponse(success=False, filename=filename, error=_error(exc))


def suggest_business_metrics(
    filename: str,
    datasource_name: str,
    ctx: ToolContext | None = None,
) -> SuggestMetricsResponse:
    """Suggest business KPIs (with formulas and rationale) for a datasource."""
    ctx = ctx or get_context()
    try:
        index = _physical_index(ctx, filename, datasource_name)
        metrics = suggest_metrics(index)
        logger.info(
            "suggest_business_metrics completed",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "metrics": len(metrics),
                }
            },
        )
        return SuggestMetricsResponse(
            success=True, filename=filename, datasource_name=datasource_name, metrics=metrics
        )
    except TableauMCPError as exc:
        logger.error(
            "suggest_business_metrics failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return SuggestMetricsResponse(
            success=False, filename=filename, datasource_name=datasource_name, error=_error(exc)
        )


def create_recommended_metrics(
    filename: str,
    datasource_name: str,
    ctx: ToolContext | None = None,
) -> BatchMutationResponse:
    """Create every recommended, formula-backed metric in a single atomic batch.

    Metrics that already exist in the datasource are skipped to keep the call
    idempotent; the remaining ones are created via the shared batch tool.
    """
    ctx = ctx or get_context()
    try:
        _, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)
        existing_captions = {
            (f.caption or "").strip().lower() for f in inspector.fields_for_datasource(ds)
        }
        physical = [f for f in inspector.fields_for_datasource(ds) if f.kind == "physical"]
        index = FieldIndex(classify_fields(physical))

        specs = [
            metric.to_spec()
            for metric in creatable_metrics(suggest_metrics(index))
            if metric.name.strip().lower() not in existing_captions
        ]
        if not specs:
            return BatchMutationResponse(
                success=True,
                filename=filename,
                applied=False,
                changes=[],
                error=None,
            )

        logger.info(
            "create_recommended_metrics delegating to batch",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "count": len(specs),
                }
            },
        )
        return create_calculated_fields_batch(filename, datasource_name, specs, ctx=ctx)
    except TableauMCPError as exc:
        logger.error(
            "create_recommended_metrics failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return BatchMutationResponse(success=False, filename=filename, error=_error(exc))


def suggest_visualizations(
    filename: str,
    datasource_name: str,
    ctx: ToolContext | None = None,
) -> SuggestVisualizationsResponse:
    """Recommend chart types (with rationale) for a datasource's analyses."""
    ctx = ctx or get_context()
    try:
        index = _physical_index(ctx, filename, datasource_name)
        visualizations = advise_visualizations(index)
        logger.info(
            "suggest_visualizations completed",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "count": len(visualizations),
                }
            },
        )
        return SuggestVisualizationsResponse(
            success=True,
            filename=filename,
            datasource_name=datasource_name,
            visualizations=visualizations,
        )
    except TableauMCPError as exc:
        logger.error(
            "suggest_visualizations failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return SuggestVisualizationsResponse(
            success=False, filename=filename, datasource_name=datasource_name, error=_error(exc)
        )
