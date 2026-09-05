"""Read-only access to workbook files and filesystem listing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lxml import etree

from ..config import ALLOWED_WORKBOOK_SUFFIXES
from ..exceptions import SecurityError, WorkbookParseError
from ..models import WorkbookMetadata
from .xml_utils import parse_workbook, resolve_workbook_path


class WorkbookReader:
    """Provides safe, read-only access to ``.twb`` files in the authorized folder."""

    def __init__(self, workbooks_dir: Path, max_file_size_bytes: int) -> None:
        """Initialize the reader.

        Args:
            workbooks_dir: Authorized folder that contains workbooks.
            max_file_size_bytes: Maximum size a workbook may have to be opened.
        """
        self._workbooks_dir = workbooks_dir.resolve()
        self._max_file_size_bytes = max_file_size_bytes

    @property
    def workbooks_dir(self) -> Path:
        """The authorized workbooks folder."""
        return self._workbooks_dir

    def list_workbooks(self) -> list[WorkbookMetadata]:
        """List all ``.twb`` files directly inside the authorized folder.

        Returns:
            Metadata for each workbook, sorted by filename.
        """
        results: list[WorkbookMetadata] = []
        if not self._workbooks_dir.exists():
            return results

        for path in sorted(self._workbooks_dir.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ALLOWED_WORKBOOK_SUFFIXES:
                continue
            stat = path.stat()
            results.append(
                WorkbookMetadata(
                    filename=path.name,
                    relative_path=path.relative_to(self._workbooks_dir).as_posix(),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                )
            )
        return results

    def resolve(self, filename: str) -> Path:
        """Resolve a filename to a safe absolute path (see :func:`resolve_workbook_path`)."""
        return resolve_workbook_path(filename, self._workbooks_dir)

    def load_tree(self, filename: str) -> tuple[Path, etree._ElementTree]:
        """Resolve, size-check, and parse a workbook.

        Returns:
            A tuple of the resolved path and the parsed ElementTree.

        Raises:
            SecurityError: If the file exceeds the configured maximum size.
        """
        path = self.resolve(filename)
        size = path.stat().st_size
        if size > self._max_file_size_bytes:
            raise SecurityError(
                f"Workbook '{filename}' ({size} bytes) exceeds the maximum allowed size "
                f"({self._max_file_size_bytes} bytes)."
            )
        tree = parse_workbook(path)
        return path, tree

    def read_bytes(self, filename: str) -> tuple[Path, bytes]:
        """Read raw bytes of a workbook after path/size validation."""
        path = self.resolve(filename)
        size = path.stat().st_size
        if size > self._max_file_size_bytes:
            raise SecurityError(
                f"Workbook '{filename}' ({size} bytes) exceeds the maximum allowed size."
            )
        try:
            return path, path.read_bytes()
        except OSError as exc:  # pragma: no cover - filesystem dependent
            raise WorkbookParseError(f"Could not read '{filename}': {exc}") from exc
