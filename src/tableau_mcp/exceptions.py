"""Custom exception hierarchy for tableau-desktop-mcp.

All application errors derive from :class:`TableauMCPError` so tools can catch
a single base type and convert it into a structured error response without ever
resorting to a bare ``except Exception``.
"""

from __future__ import annotations


class TableauMCPError(Exception):
    """Base class for every error raised by this package.

    Attributes:
        message: Human-readable description safe to surface to the caller.
        code: Short machine-readable error code used in structured responses.
    """

    code: str = "tableau_mcp_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigurationError(TableauMCPError):
    """Raised when the server configuration is invalid or incomplete."""

    code = "configuration_error"


class SecurityError(TableauMCPError):
    """Raised on path traversal, disallowed extension, or out-of-sandbox access."""

    code = "security_error"


class WorkbookNotFoundError(TableauMCPError):
    """Raised when a requested workbook does not exist in the authorized folder."""

    code = "workbook_not_found"


class WorkbookParseError(TableauMCPError):
    """Raised when a .twb file cannot be parsed as valid XML."""

    code = "workbook_parse_error"


class DatasourceNotFoundError(TableauMCPError):
    """Raised when the requested datasource cannot be located in the workbook."""

    code = "datasource_not_found"


class FieldNotFoundError(TableauMCPError):
    """Raised when a referenced field cannot be located in the datasource."""

    code = "field_not_found"


class DuplicateFieldError(TableauMCPError):
    """Raised when creating a field whose caption already exists."""

    code = "duplicate_field"


class FormulaValidationError(TableauMCPError):
    """Raised when a formula fails validation and the operation must abort."""

    code = "formula_validation_error"


class ValidationError(TableauMCPError):
    """Raised when written XML fails post-write validation (triggers rollback)."""

    code = "validation_error"


class BackupError(TableauMCPError):
    """Raised when a backup could not be created or restored."""

    code = "backup_error"


class ConfirmationRequiredError(TableauMCPError):
    """Raised when a destructive operation is attempted without explicit confirmation."""

    code = "confirmation_required"


class ObjectGraphNotFoundError(TableauMCPError):
    """Raised when a datasource has no ``<object-graph>`` (not a relationships model)."""

    code = "object_graph_not_found"


class RelationshipObjectNotFoundError(TableauMCPError):
    """Raised when a table caption cannot be resolved to an ``<object>`` in the object-graph."""

    code = "relationship_object_not_found"


class RelationshipNotFoundError(TableauMCPError):
    """Raised when no ``<relationship>`` connects the requested pair of objects."""

    code = "relationship_not_found"


class AmbiguousFieldError(TableauMCPError):
    """Raised when a field name cannot be resolved unambiguously; never guessed."""

    code = "ambiguous_field"
