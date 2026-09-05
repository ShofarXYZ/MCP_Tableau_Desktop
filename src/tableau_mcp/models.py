"""Pydantic models for structured tool inputs, metadata, and responses.

Every MCP tool returns a model derived from :class:`BaseResponse` so callers
receive a predictable, typed structure instead of loose strings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerated string literals
# ---------------------------------------------------------------------------

FieldRole = Literal["dimension", "measure", "unknown"]
FieldKind = Literal["physical", "calculated", "parameter"]
FieldTypeFilter = Literal["all", "dimension", "measure", "parameter", "calculated"]
ValidationSeverity = Literal["error", "warning", "info"]

#: Inferred business meaning of a field (semantic layer / copilot).
SemanticType = Literal[
    "identifier",
    "date",
    "revenue",
    "cost",
    "profit",
    "discount",
    "quantity",
    "percentage",
    "geo",
    "category",
    "generic_measure",
    "generic_dimension",
    "unknown",
]

#: Confidence buckets used across the semantic layer.
Confidence = Literal["high", "medium", "low"]

#: Chart types the visualization advisor can recommend.
ChartType = Literal[
    "line", "bar", "horizontal_bar", "map", "kpi", "area", "scatter", "pie", "table"
]


# ---------------------------------------------------------------------------
# Metadata models
# ---------------------------------------------------------------------------


class WorkbookMetadata(BaseModel):
    """Basic filesystem metadata about a workbook."""

    filename: str
    relative_path: str
    size_bytes: int
    modified_at: datetime


class DatasourceMetadata(BaseModel):
    """Metadata describing a single ``<datasource>`` element."""

    name: str = Field(description="Internal datasource name attribute.")
    caption: str | None = Field(default=None, description="Human-friendly caption, if any.")
    connection_type: str | None = Field(default=None, description="Connection class, if present.")
    is_federated: bool = False
    field_count: int = 0
    calculated_field_count: int = 0


class FieldMetadata(BaseModel):
    """Metadata describing a ``<column>`` (physical, calculated, or parameter)."""

    name: str = Field(description="Internal Tableau field name, e.g. '[Receita]'.")
    caption: str | None = Field(default=None, description="Display caption, if any.")
    datatype: str | None = None
    role: FieldRole = "unknown"
    kind: FieldKind = "physical"
    field_type: str | None = Field(default=None, description="Tableau 'type' attribute.")
    formula: str | None = Field(default=None, description="Formula for calculated fields.")
    datasource_name: str | None = None


class CalculatedField(BaseModel):
    """A calculated field definition as listed by the inspection tools."""

    name: str
    caption: str | None = None
    formula: str
    datatype: str | None = None
    role: FieldRole = "measure"
    datasource_name: str | None = None


class BackupMetadata(BaseModel):
    """Information about a created backup file."""

    relative_path: str
    original_filename: str
    created_at: datetime
    size_bytes: int


# ---------------------------------------------------------------------------
# Formula validation
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single validation finding (error, warning, or informational note)."""

    severity: ValidationSeverity
    code: str
    message: str
    suggestion: str | None = None


class FieldReferenceReport(BaseModel):
    """Result of matching field references in a formula against a datasource."""

    found: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    ambiguous: list[str] = Field(default_factory=list)
    suggestions: dict[str, list[str]] = Field(default_factory=dict)


class FormulaValidationResult(BaseModel):
    """Structured result of validating a Tableau formula."""

    is_valid: bool
    formula: str
    issues: list[ValidationIssue] = Field(default_factory=list)
    references: FieldReferenceReport = Field(default_factory=FieldReferenceReport)
    dax_functions_detected: list[str] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """True if any issue has ``error`` severity."""
        return any(issue.severity == "error" for issue in self.issues)


# ---------------------------------------------------------------------------
# Tool input models
# ---------------------------------------------------------------------------


RelationshipOperationName = Literal["List", "Get", "Update"]


class RelationshipReference(BaseModel):
    """Identifies one relationship by the two table captions it connects (order-insensitive)."""

    from_object: str = Field(description="Caption of one table in the relationship.")
    to_object: str = Field(description="Caption of the other table in the relationship.")


class RelationshipDefinition(BaseModel):
    """A single relationship field-binding fix to apply."""

    from_object: str = Field(description="Caption of the first table.")
    to_object: str = Field(description="Caption of the second table.")
    from_field: str = Field(
        min_length=1, description="New physical field reference for the from_object side."
    )
    to_field: str = Field(
        min_length=1, description="New physical field reference for the to_object side."
    )
    condition_index: int | None = Field(
        default=None,
        description=(
            "Which equality condition to update when the relationship has more than one "
            "(e.g. a compound AND join). Defaults to the first broken condition found."
        ),
    )


class RelationshipCondition(BaseModel):
    """One '=' equality leaf inside a relationship's join expression."""

    from_field: str | None = None
    to_field: str | None = None
    from_field_valid: bool = False
    to_field_valid: bool = False


class RelationshipInfo(BaseModel):
    """A parsed ``<relationship>`` entry from a datasource's ``<object-graph>``."""

    index: int
    from_object: str = Field(description="Caption of the first-end-point table.")
    to_object: str = Field(description="Caption of the second-end-point table.")
    from_object_id: str = ""
    to_object_id: str = ""
    conditions: list[RelationshipCondition] = Field(default_factory=list)
    is_valid: bool = Field(
        description="True only if every condition's from_field and to_field resolve to a "
        "real physical column on their respective table."
    )


class RelationshipChange(BaseModel):
    """Report of a single relationship field-binding update."""

    from_object: str
    to_object: str
    condition_index: int | None = None
    previous_from_field: str | None = None
    previous_to_field: str | None = None
    new_from_field: str | None = None
    new_to_field: str | None = None
    status: Literal["updated", "failed", "skipped"]
    detail: str | None = None


class CalculatedFieldSpec(BaseModel):
    """Specification used to create a calculated field (single or batch)."""

    field_name: str = Field(min_length=1, description="Display caption of the new field.")
    formula: str = Field(min_length=1, description="Native Tableau formula.")
    datatype: str = Field(default="real")
    role: FieldRole = Field(default="measure")
    field_type: str = Field(default="quantitative")
    description: str | None = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ErrorInfo(BaseModel):
    """Structured error payload embedded in failed responses."""

    code: str
    message: str


class BaseResponse(BaseModel):
    """Common shape for every tool response."""

    success: bool
    error: ErrorInfo | None = None


class ListWorkbooksResponse(BaseResponse):
    """Response for ``list_workbooks``."""

    workbooks: list[WorkbookMetadata] = Field(default_factory=list)


class InspectWorkbookResponse(BaseResponse):
    """Response for ``inspect_workbook``."""

    filename: str | None = None
    datasources: list[DatasourceMetadata] = Field(default_factory=list)
    worksheets: list[str] = Field(default_factory=list)
    dashboards: list[str] = Field(default_factory=list)
    fields: list[FieldMetadata] = Field(default_factory=list)


class ListDatasourcesResponse(BaseResponse):
    """Response for ``list_datasources``."""

    filename: str | None = None
    datasources: list[DatasourceMetadata] = Field(default_factory=list)


class ListFieldsResponse(BaseResponse):
    """Response for ``list_fields``."""

    filename: str | None = None
    datasource_name: str | None = None
    fields: list[FieldMetadata] = Field(default_factory=list)


class ListCalculatedFieldsResponse(BaseResponse):
    """Response for ``list_calculated_fields``."""

    filename: str | None = None
    calculated_fields: list[CalculatedField] = Field(default_factory=list)


class CalculatedFieldChange(BaseModel):
    """Report of a single created / updated / deleted calculated field."""

    field_name: str
    internal_name: str | None = None
    datasource_name: str | None = None
    formula: str | None = None
    previous_formula: str | None = None
    status: Literal["created", "updated", "deleted", "skipped", "failed"]
    detail: str | None = None


class MutationResponse(BaseResponse):
    """Response for single-field create / update / delete operations."""

    filename: str | None = None
    change: CalculatedFieldChange | None = None
    backup: BackupMetadata | None = None
    validation: FormulaValidationResult | None = None


class BatchMutationResponse(BaseResponse):
    """Response for ``create_calculated_fields_batch``."""

    filename: str | None = None
    changes: list[CalculatedFieldChange] = Field(default_factory=list)
    backup: BackupMetadata | None = None
    applied: bool = False


class ValidateFormulaResponse(BaseResponse):
    """Response for ``validate_tableau_formula``."""

    validation: FormulaValidationResult | None = None


class BackupResponse(BaseResponse):
    """Response for ``backup_workbook``."""

    backup: BackupMetadata | None = None


class RestoreResponse(BaseResponse):
    """Response for ``restore_workbook_backup``."""

    restored_from: str | None = None
    pre_restore_backup: BackupMetadata | None = None
    available_backups: list[BackupMetadata] = Field(default_factory=list)


class RelationshipOperationsResponse(BaseResponse):
    """Response for ``relationship_operations`` (List / Get / Update)."""

    filename: str | None = None
    datasource_name: str | None = None
    operation: str | None = Field(
        default=None,
        description="Echoes the requested operation ('List'/'Get'/'Update'), even if invalid.",
    )
    relationships: list[RelationshipInfo] = Field(default_factory=list)
    changes: list[RelationshipChange] = Field(default_factory=list)
    backup: BackupMetadata | None = None
    applied: bool = False


# ---------------------------------------------------------------------------
# Semantic layer / Analytics Copilot
# ---------------------------------------------------------------------------


class ClassifiedField(BaseModel):
    """A physical field annotated with its inferred business meaning."""

    name: str = Field(description="Internal Tableau field name.")
    caption: str = Field(description="Display name used to reference the field in formulas.")
    datatype: str | None = None
    role: FieldRole = "unknown"
    semantic_type: SemanticType = "unknown"
    confidence: Confidence = "low"
    reason: str = Field(default="", description="Why the field was classified this way.")


class DatasetAnalysis(BaseModel):
    """Semantic interpretation of a single datasource."""

    datasource_name: str
    datasource_caption: str | None = None
    inferred_domain: str = Field(description="Best guess of the business domain, e.g. 'Vendas'.")
    domain_confidence: Confidence = "low"
    fields: list[ClassifiedField] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    identifiers: list[str] = Field(default_factory=list)
    geo_fields: list[str] = Field(default_factory=list)
    possible_metrics: list[str] = Field(default_factory=list)
    possible_dimensions: list[str] = Field(default_factory=list)


class MetricSuggestion(BaseModel):
    """A suggested business KPI, with a ready-to-use Tableau formula when possible."""

    name: str
    formula: str | None = Field(
        default=None,
        description="Native Tableau formula, or None if the metric is conceptual only.",
    )
    rationale: str
    datatype: str = "real"
    role: FieldRole = "measure"
    field_type: str = "quantitative"
    category: str = Field(default="general", description="e.g. financial, count, ratio, time.")
    requires_view_context: bool = Field(
        default=False,
        description="True for table calcs (Running Total, MoM, YoY) that depend on the view.",
    )

    def to_spec(self) -> CalculatedFieldSpec:
        """Convert to a :class:`CalculatedFieldSpec` (only valid when ``formula`` is set)."""
        if not self.formula:
            raise ValueError(f"Metric '{self.name}' has no concrete formula to create.")
        return CalculatedFieldSpec(
            field_name=self.name,
            formula=self.formula,
            datatype=self.datatype,
            role=self.role,
            field_type=self.field_type,
            description=self.rationale,
        )


class VisualizationSuggestion(BaseModel):
    """A recommended chart for a given analysis."""

    title: str
    chart_type: ChartType
    rationale: str
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)


class AnalyzeDatasetResponse(BaseResponse):
    """Response for ``analyze_dataset``."""

    filename: str | None = None
    analyses: list[DatasetAnalysis] = Field(default_factory=list)


class SuggestMetricsResponse(BaseResponse):
    """Response for ``suggest_business_metrics``."""

    filename: str | None = None
    datasource_name: str | None = None
    metrics: list[MetricSuggestion] = Field(default_factory=list)


class SuggestVisualizationsResponse(BaseResponse):
    """Response for ``suggest_visualizations``."""

    filename: str | None = None
    datasource_name: str | None = None
    visualizations: list[VisualizationSuggestion] = Field(default_factory=list)
