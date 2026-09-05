"""Structural inspection of a parsed Tableau workbook.

The inspector translates the raw lxml tree into typed metadata models. It makes
no assumptions that every workbook shares an identical structure: missing
captions, multiple datasources, parameter datasources, calculated vs physical
columns, and version differences are all tolerated.
"""

from __future__ import annotations

from lxml import etree

from ..exceptions import DatasourceNotFoundError
from ..models import (
    CalculatedField,
    DatasourceMetadata,
    FieldKind,
    FieldMetadata,
    FieldRole,
)

#: Tableau's internal datasource that holds parameters.
PARAMETERS_DATASOURCE_NAME = "Parameters"


def _normalize_role(raw: str | None) -> FieldRole:
    """Map a Tableau ``role`` attribute onto our :data:`FieldRole` literal."""
    if raw == "dimension":
        return "dimension"
    if raw == "measure":
        return "measure"
    return "unknown"


def _is_parameter_column(column: etree._Element) -> bool:
    """Return True if a ``<column>`` element represents a parameter."""
    return column.get("param-domain-type") is not None


def _calculation_element(column: etree._Element) -> etree._Element | None:
    """Return the child ``<calculation>`` element of a column, if present."""
    return column.find("calculation")


class WorkbookInspector:
    """Extracts datasources, fields, worksheets, and dashboards from a workbook tree."""

    def __init__(self, tree: etree._ElementTree) -> None:
        """Initialize with a parsed workbook ElementTree."""
        self._tree = tree
        self._root = tree.getroot()

    # -- datasources -------------------------------------------------------

    def datasource_elements(self) -> list[etree._Element]:
        """Return every top-level ``<datasource>`` element in document order.

        Only the workbook's own ``<datasources>`` block is considered. Tableau
        also emits lightweight ``<datasources><datasource .../></datasources>``
        *dependency* stubs inside ``<worksheet>``/``<view>`` elements (name +
        caption only, no ``<column>`` children) to record which datasources a
        sheet uses. Using ``.//datasources/datasource`` picked those up too,
        producing duplicate, empty-looking datasources for every worksheet.
        """
        return self._root.findall("datasources/datasource")

    def find_datasource(self, name_or_caption: str) -> etree._Element:
        """Locate a datasource by internal name or caption (case-insensitive).

        Raises:
            DatasourceNotFoundError: If no datasource matches.
        """
        wanted = name_or_caption.strip().lower()
        for ds in self.datasource_elements():
            if (ds.get("name") or "").lower() == wanted:
                return ds
            if (ds.get("caption") or "").lower() == wanted:
                return ds
        available = ", ".join(self._datasource_labels()) or "(none)"
        raise DatasourceNotFoundError(
            f"Datasource '{name_or_caption}' not found. Available: {available}."
        )

    def _datasource_labels(self) -> list[str]:
        labels: list[str] = []
        for ds in self.datasource_elements():
            labels.append(ds.get("caption") or ds.get("name") or "(unnamed)")
        return labels

    def datasource_metadata(self) -> list[DatasourceMetadata]:
        """Return metadata for every datasource."""
        result: list[DatasourceMetadata] = []
        for ds in self.datasource_elements():
            columns = ds.findall("column")
            calc_count = sum(1 for c in columns if _calculation_element(c) is not None)
            connection = ds.find(".//connection")
            connection_class = connection.get("class") if connection is not None else None
            result.append(
                DatasourceMetadata(
                    name=ds.get("name") or "",
                    caption=ds.get("caption"),
                    connection_type=connection_class,
                    is_federated=(connection_class == "federated"),
                    field_count=len(columns),
                    calculated_field_count=calc_count,
                )
            )
        return result

    # -- fields ------------------------------------------------------------

    def _column_to_field(self, column: etree._Element, datasource_name: str) -> FieldMetadata:
        calc = _calculation_element(column)
        kind: FieldKind
        if _is_parameter_column(column):
            kind = "parameter"
        elif calc is not None:
            kind = "calculated"
        else:
            kind = "physical"
        return FieldMetadata(
            name=column.get("name") or "",
            caption=column.get("caption"),
            datatype=column.get("datatype"),
            role=_normalize_role(column.get("role")),
            kind=kind,
            field_type=column.get("type"),
            formula=(calc.get("formula") if calc is not None else None),
            datasource_name=datasource_name,
        )

    def fields_for_datasource(self, ds: etree._Element) -> list[FieldMetadata]:
        """Return all fields declared as ``<column>`` in a datasource."""
        ds_name = ds.get("name") or ""
        return [self._column_to_field(c, ds_name) for c in ds.findall("column")]

    def all_fields(self) -> list[FieldMetadata]:
        """Return fields across every datasource."""
        fields: list[FieldMetadata] = []
        for ds in self.datasource_elements():
            fields.extend(self.fields_for_datasource(ds))
        return fields

    def calculated_fields(self) -> list[CalculatedField]:
        """Return every calculated field across all datasources."""
        result: list[CalculatedField] = []
        for ds in self.datasource_elements():
            ds_name = ds.get("name") or ""
            for column in ds.findall("column"):
                calc = _calculation_element(column)
                if calc is None:
                    continue
                formula = calc.get("formula")
                if formula is None:
                    continue
                result.append(
                    CalculatedField(
                        name=column.get("name") or "",
                        caption=column.get("caption"),
                        formula=formula,
                        datatype=column.get("datatype"),
                        role=_normalize_role(column.get("role")),
                        datasource_name=ds_name,
                    )
                )
        return result

    # -- worksheets / dashboards ------------------------------------------

    def worksheet_names(self) -> list[str]:
        """Return the names of all worksheets."""
        return [
            ws.get("name") or ""
            for ws in self._root.findall(".//worksheets/worksheet")
            if ws.get("name")
        ]

    def dashboard_names(self) -> list[str]:
        """Return the names of all dashboards."""
        return [
            db.get("name") or ""
            for db in self._root.findall(".//dashboards/dashboard")
            if db.get("name")
        ]
