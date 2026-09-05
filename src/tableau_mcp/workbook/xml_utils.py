"""Low-level XML and path-safety helpers.

This module centralizes two concerns:

* **Path safety** - resolving a caller-supplied filename to a real path that is
  guaranteed to live inside the authorized workbooks folder, with the correct
  extension, blocking path traversal and unexpected/temporary files.
* **XML parsing/serialization** - parsing ``.twb`` files with ``lxml`` using a
  hardened parser (no network access, no entity expansion) and serializing them
  back while preserving the original declaration and encoding.

No regular expressions are used to mutate XML; all edits go through lxml.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..config import ALLOWED_WORKBOOK_SUFFIXES
from ..exceptions import SecurityError, WorkbookNotFoundError, WorkbookParseError

# Suffixes that indicate temporary / editor / lock files we must never touch.
_BLOCKED_SUFFIXES: frozenset[str] = frozenset(
    {".tmp", ".temp", ".bak", ".swp", ".lock", ".~lock", ".twbx"}
)


def _hardened_parser() -> etree.XMLParser:
    """Return an lxml parser configured to avoid XXE / entity-expansion attacks."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        recover=False,
    )


def resolve_workbook_path(filename: str, workbooks_dir: Path) -> Path:
    """Resolve ``filename`` to a safe absolute path inside ``workbooks_dir``.

    Args:
        filename: User-supplied filename or relative path (never absolute input
            is trusted; it is still confined to the sandbox).
        workbooks_dir: The authorized root folder.

    Returns:
        The resolved absolute :class:`Path`.

    Raises:
        SecurityError: On path traversal, absolute escape, blocked/unexpected
            extension, or any target outside ``workbooks_dir``.
        WorkbookNotFoundError: If the resolved path does not exist or is not a file.
    """
    if not filename or not filename.strip():
        raise SecurityError("Empty filename is not allowed.")

    raw = filename.strip().replace("\\", "/")
    # Reject obvious traversal tokens early for a clear message.
    if ".." in Path(raw).parts:
        raise SecurityError(f"Path traversal is not allowed: '{filename}'.")

    root = workbooks_dir.resolve()
    candidate = (root / raw).resolve()

    # Confinement check: candidate must be inside the authorized root.
    if root != candidate and root not in candidate.parents:
        raise SecurityError(
            f"Access outside the authorized workbooks folder is not allowed: '{filename}'."
        )

    suffix = candidate.suffix.lower()
    if suffix in _BLOCKED_SUFFIXES:
        raise SecurityError(f"File extension '{suffix}' is not permitted.")
    if suffix not in ALLOWED_WORKBOOK_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_WORKBOOK_SUFFIXES))
        raise SecurityError(
            f"Unsupported extension '{suffix}'. Only {allowed} files are supported."
        )

    if not candidate.exists() or not candidate.is_file():
        raise WorkbookNotFoundError(f"Workbook not found: '{filename}'.")

    return candidate


def parse_workbook(path: Path) -> etree._ElementTree:
    """Parse a ``.twb`` file into an lxml ElementTree.

    Args:
        path: Absolute path to an existing, already path-validated ``.twb`` file.

    Returns:
        The parsed :class:`lxml.etree._ElementTree`.

    Raises:
        WorkbookParseError: If the file is not well-formed XML.
    """
    try:
        return etree.parse(str(path), parser=_hardened_parser())
    except etree.XMLSyntaxError as exc:
        raise WorkbookParseError(f"Invalid Tableau XML in '{path.name}': {exc}") from exc
    except OSError as exc:
        raise WorkbookParseError(f"Could not read workbook '{path.name}': {exc}") from exc


def parse_bytes(data: bytes) -> etree._ElementTree:
    """Parse XML from an in-memory byte string.

    Raises:
        WorkbookParseError: If the bytes are not well-formed XML.
    """
    try:
        root = etree.fromstring(data, parser=_hardened_parser())
    except etree.XMLSyntaxError as exc:
        raise WorkbookParseError(f"Invalid Tableau XML: {exc}") from exc
    return etree.ElementTree(root)


def serialize_tree(tree: etree._ElementTree) -> bytes:
    """Serialize an ElementTree back to UTF-8 bytes with an XML declaration."""
    return etree.tostring(
        tree,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )
