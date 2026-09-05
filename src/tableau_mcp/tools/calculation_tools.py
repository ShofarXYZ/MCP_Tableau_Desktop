"""Tools that create, update, delete, and validate calculated fields."""

from __future__ import annotations

from lxml import etree

from ..calculations.element_builder import (
    attach_column,
    build_calculated_column,
    find_column_by_caption,
    generate_internal_name,
    is_calculated,
    references_field,
)
from ..calculations.validator import validate_formula
from ..exceptions import (
    ConfirmationRequiredError,
    DuplicateFieldError,
    FieldNotFoundError,
    FormulaValidationError,
    TableauMCPError,
)
from ..logging_config import get_logger
from ..models import (
    BatchMutationResponse,
    CalculatedFieldChange,
    CalculatedFieldSpec,
    ErrorInfo,
    FieldMetadata,
    MutationResponse,
    ValidateFormulaResponse,
)
from ..workbook.inspector import WorkbookInspector
from .context import ToolContext, get_context

logger = get_logger()


def _error(exc: TableauMCPError) -> ErrorInfo:
    return ErrorInfo(code=exc.code, message=exc.message)


# ---------------------------------------------------------------------------
# validate_tableau_formula
# ---------------------------------------------------------------------------


def validate_tableau_formula(
    formula: str,
    filename: str | None = None,
    datasource_name: str | None = None,
    ctx: ToolContext | None = None,
) -> ValidateFormulaResponse:
    """Validate a formula without modifying any workbook.

    If ``filename`` and ``datasource_name`` are given, field references are also
    checked against that datasource.
    """
    ctx = ctx or get_context()
    try:
        fields: list[FieldMetadata] | None = None
        if filename and datasource_name:
            _, tree = ctx.reader.load_tree(filename)
            inspector = WorkbookInspector(tree)
            ds = inspector.find_datasource(datasource_name)
            fields = inspector.fields_for_datasource(ds)
        result = validate_formula(formula, fields)
        return ValidateFormulaResponse(success=True, validation=result)
    except TableauMCPError as exc:
        logger.error("validate_tableau_formula failed", extra={"context": {"error": exc.code}})
        return ValidateFormulaResponse(success=False, error=_error(exc))


# ---------------------------------------------------------------------------
# create_calculated_field
# ---------------------------------------------------------------------------


def create_calculated_field(
    filename: str,
    datasource_name: str,
    field_name: str,
    formula: str,
    datatype: str = "real",
    role: str = "measure",
    field_type: str = "quantitative",
    description: str | None = None,
    ctx: ToolContext | None = None,
) -> MutationResponse:
    """Create a single calculated field using native Tableau syntax."""
    ctx = ctx or get_context()
    try:
        spec = CalculatedFieldSpec(
            field_name=field_name,
            formula=formula,
            datatype=datatype,
            role=role,  # type: ignore[arg-type]
            field_type=field_type,
            description=description,
        )
        path, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)
        fields = inspector.fields_for_datasource(ds)

        if find_column_by_caption(ds, field_name) is not None:
            raise DuplicateFieldError(
                f"A field named '{field_name}' already exists in datasource '{datasource_name}'."
            )

        validation = validate_formula(formula, fields)
        if not validation.is_valid:
            messages = "; ".join(i.message for i in validation.issues if i.severity == "error")
            return MutationResponse(
                success=False,
                filename=filename,
                validation=validation,
                error=ErrorInfo(code="formula_validation_error", message=messages),
                change=CalculatedFieldChange(
                    field_name=field_name,
                    datasource_name=datasource_name,
                    status="failed",
                    detail=messages,
                ),
            )

        internal_name = generate_internal_name(ds)

        def mutation(mutable_tree: etree._ElementTree) -> None:
            target_ds = WorkbookInspector(mutable_tree).find_datasource(datasource_name)
            column = build_calculated_column(target_ds, spec, internal_name)
            attach_column(target_ds, column)

        backup = ctx.writer.apply(path, mutation)
        logger.info(
            "create_calculated_field applied",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "field": field_name,
                    "internal_name": internal_name,
                    "backup": backup.relative_path,
                }
            },
        )
        return MutationResponse(
            success=True,
            filename=filename,
            backup=backup,
            validation=validation,
            change=CalculatedFieldChange(
                field_name=field_name,
                internal_name=internal_name,
                datasource_name=datasource_name,
                formula=formula,
                status="created",
            ),
        )
    except TableauMCPError as exc:
        logger.error(
            "create_calculated_field failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return MutationResponse(success=False, filename=filename, error=_error(exc))


# ---------------------------------------------------------------------------
# update_calculated_field
# ---------------------------------------------------------------------------


def update_calculated_field(
    filename: str,
    datasource_name: str,
    field_name: str,
    formula: str,
    ctx: ToolContext | None = None,
) -> MutationResponse:
    """Update the formula of an existing calculated field."""
    ctx = ctx or get_context()
    try:
        path, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)
        fields = inspector.fields_for_datasource(ds)

        column = find_column_by_caption(ds, field_name)
        if column is None or not is_calculated(column):
            raise FieldNotFoundError(
                f"Calculated field '{field_name}' not found in datasource '{datasource_name}'."
            )
        calc = column.find("calculation")
        assert calc is not None  # guaranteed by is_calculated
        previous_formula = calc.get("formula")

        validation = validate_formula(formula, fields)
        if not validation.is_valid:
            messages = "; ".join(i.message for i in validation.issues if i.severity == "error")
            return MutationResponse(
                success=False,
                filename=filename,
                validation=validation,
                error=ErrorInfo(code="formula_validation_error", message=messages),
                change=CalculatedFieldChange(
                    field_name=field_name,
                    datasource_name=datasource_name,
                    previous_formula=previous_formula,
                    status="failed",
                    detail=messages,
                ),
            )

        internal_name = column.get("name")

        def mutation(mutable_tree: etree._ElementTree) -> None:
            target_ds = WorkbookInspector(mutable_tree).find_datasource(datasource_name)
            target = find_column_by_caption(target_ds, field_name)
            if target is None:  # pragma: no cover - defensive
                raise FieldNotFoundError(f"Field '{field_name}' disappeared during update.")
            target_calc = target.find("calculation")
            assert target_calc is not None
            target_calc.set("formula", formula)

        backup = ctx.writer.apply(path, mutation)
        logger.info(
            "update_calculated_field applied",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "field": field_name,
                    "backup": backup.relative_path,
                }
            },
        )
        return MutationResponse(
            success=True,
            filename=filename,
            backup=backup,
            validation=validation,
            change=CalculatedFieldChange(
                field_name=field_name,
                internal_name=internal_name,
                datasource_name=datasource_name,
                formula=formula,
                previous_formula=previous_formula,
                status="updated",
            ),
        )
    except TableauMCPError as exc:
        logger.error(
            "update_calculated_field failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return MutationResponse(success=False, filename=filename, error=_error(exc))


# ---------------------------------------------------------------------------
# delete_calculated_field
# ---------------------------------------------------------------------------


def delete_calculated_field(
    filename: str,
    datasource_name: str,
    field_name: str,
    confirm: bool = False,
    ctx: ToolContext | None = None,
) -> MutationResponse:
    """Delete a calculated field only (never a physical/source column)."""
    ctx = ctx or get_context()
    try:
        path, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)

        column = find_column_by_caption(ds, field_name)
        if column is None:
            raise FieldNotFoundError(
                f"Field '{field_name}' not found in datasource '{datasource_name}'."
            )
        if not is_calculated(column):
            raise FieldNotFoundError(
                f"Field '{field_name}' is a physical/source column and cannot be deleted."
            )

        internal_name = column.get("name") or ""
        # Identify possible references to this field in other calculations.
        referencing: list[str] = []
        for other in ds.findall("column"):
            if other is column:
                continue
            other_calc = other.find("calculation")
            if other_calc is None:
                continue
            other_formula = other_calc.get("formula") or ""
            if references_field(other_formula, field_name, internal_name):
                referencing.append(other.get("caption") or other.get("name") or "?")

        if not confirm:
            detail = (
                "Deletion requires 'confirm=true'."
                if not referencing
                else f"Deletion requires 'confirm=true'. Referenced by: {', '.join(referencing)}."
            )
            raise ConfirmationRequiredError(detail)

        def mutation(mutable_tree: etree._ElementTree) -> None:
            target_ds = WorkbookInspector(mutable_tree).find_datasource(datasource_name)
            target = find_column_by_caption(target_ds, field_name)
            if target is None:  # pragma: no cover - defensive
                raise FieldNotFoundError(f"Field '{field_name}' disappeared during delete.")
            parent = target.getparent()
            assert parent is not None
            parent.remove(target)

        backup = ctx.writer.apply(path, mutation)
        logger.info(
            "delete_calculated_field applied",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "field": field_name,
                    "backup": backup.relative_path,
                    "referenced_by": referencing,
                }
            },
        )
        warn_detail: str | None = (
            f"Warning: field was referenced by {', '.join(referencing)}." if referencing else None
        )
        return MutationResponse(
            success=True,
            filename=filename,
            backup=backup,
            change=CalculatedFieldChange(
                field_name=field_name,
                internal_name=internal_name,
                datasource_name=datasource_name,
                status="deleted",
                detail=warn_detail,
            ),
        )
    except TableauMCPError as exc:
        logger.error(
            "delete_calculated_field failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return MutationResponse(success=False, filename=filename, error=_error(exc))


# ---------------------------------------------------------------------------
# create_calculated_fields_batch
# ---------------------------------------------------------------------------


def create_calculated_fields_batch(
    filename: str,
    datasource_name: str,
    fields: list[CalculatedFieldSpec],
    ctx: ToolContext | None = None,
) -> BatchMutationResponse:
    """Create several calculated fields atomically.

    Every field is validated first. If any is invalid or duplicated, no change
    is applied. On success, a single backup is created and a single atomic
    write persists all fields.
    """
    ctx = ctx or get_context()
    try:
        if not fields:
            raise FormulaValidationError("No fields were provided.")

        path, tree = ctx.reader.load_tree(filename)
        inspector = WorkbookInspector(tree)
        ds = inspector.find_datasource(datasource_name)
        existing_fields = inspector.fields_for_datasource(ds)

        # --- Pre-validate everything (no mutation yet) --------------------
        changes: list[CalculatedFieldChange] = []
        planned: list[tuple[CalculatedFieldSpec, str]] = []
        seen_captions: set[str] = set()
        has_error = False

        for spec in fields:
            caption_key = spec.field_name.strip().lower()
            if caption_key in seen_captions or find_column_by_caption(ds, spec.field_name):
                has_error = True
                changes.append(
                    CalculatedFieldChange(
                        field_name=spec.field_name,
                        datasource_name=datasource_name,
                        status="failed",
                        detail="Duplicate field caption.",
                    )
                )
                continue
            seen_captions.add(caption_key)

            validation = validate_formula(spec.formula, existing_fields)
            if not validation.is_valid:
                has_error = True
                messages = "; ".join(i.message for i in validation.issues if i.severity == "error")
                changes.append(
                    CalculatedFieldChange(
                        field_name=spec.field_name,
                        datasource_name=datasource_name,
                        status="failed",
                        detail=messages,
                    )
                )
                continue

            internal_name = generate_internal_name(ds)
            planned.append((spec, internal_name))
            changes.append(
                CalculatedFieldChange(
                    field_name=spec.field_name,
                    internal_name=internal_name,
                    datasource_name=datasource_name,
                    formula=spec.formula,
                    status="skipped",  # updated to "created" only if we apply
                )
            )

        if has_error:
            return BatchMutationResponse(
                success=False,
                filename=filename,
                changes=changes,
                applied=False,
                error=ErrorInfo(
                    code="batch_validation_error",
                    message="One or more fields are invalid; no changes were applied.",
                ),
            )

        # --- Single atomic write ------------------------------------------
        def mutation(mutable_tree: etree._ElementTree) -> None:
            target_ds = WorkbookInspector(mutable_tree).find_datasource(datasource_name)
            for spec, internal_name in planned:
                column = build_calculated_column(target_ds, spec, internal_name)
                attach_column(target_ds, column)

        backup = ctx.writer.apply(path, mutation)
        for change in changes:
            change.status = "created"

        logger.info(
            "create_calculated_fields_batch applied",
            extra={
                "context": {
                    "workbook": filename,
                    "datasource": datasource_name,
                    "count": len(planned),
                    "backup": backup.relative_path,
                }
            },
        )
        return BatchMutationResponse(
            success=True,
            filename=filename,
            changes=changes,
            backup=backup,
            applied=True,
        )
    except TableauMCPError as exc:
        logger.error(
            "create_calculated_fields_batch failed",
            extra={"context": {"workbook": filename, "error": exc.code}},
        )
        return BatchMutationResponse(success=False, filename=filename, error=_error(exc))
