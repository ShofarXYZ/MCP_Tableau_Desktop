"""Atomic, backup-protected writing of workbook files.

The write flow strictly follows:

    read original -> validate -> backup -> mutate in memory -> write temp file
    -> validate temp XML -> atomically replace original -> validate final -> log

If any step fails, the original file is never left in a corrupt state: mutation
happens on an in-memory tree and the real file is only swapped in after the
serialized bytes have been validated.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from lxml import etree

from ..exceptions import ValidationError
from ..logging_config import get_logger
from ..models import BackupMetadata
from .backup import BackupManager
from .validator import validate_tree_structure, validate_workbook_bytes
from .xml_utils import parse_workbook, serialize_tree

logger = get_logger()

#: A mutation receives the parsed tree and edits it in place.
Mutation = Callable[[etree._ElementTree], None]


class WorkbookWriter:
    """Applies in-memory mutations to a workbook and persists them atomically."""

    def __init__(self, backup_manager: BackupManager) -> None:
        """Initialize with a :class:`BackupManager` used before every write."""
        self._backups = backup_manager

    def apply(self, path: Path, mutation: Mutation) -> BackupMetadata:
        """Apply ``mutation`` to the workbook at ``path`` and save it safely.

        Args:
            path: Absolute path to the (already path-validated) workbook.
            mutation: Callable that edits the parsed tree in place.

        Returns:
            Metadata of the backup created before the write.

        Raises:
            ValidationError: If serialized or final XML fails validation. The
                original file is restored from backup in this case.
        """
        # 1-2. Read + validate original.
        tree = parse_workbook(path)
        validate_tree_structure(tree)

        # 3. Backup before touching anything.
        backup = self._backups.create_backup(path)

        # 4. Mutate in memory.
        mutation(tree)

        # 5. Serialize + 6. validate serialized bytes.
        data = serialize_tree(tree)
        validate_workbook_bytes(data)

        # 7. Write temp file in the same directory, then atomic replace.
        try:
            self._atomic_write(path, data)
        except OSError as exc:
            self._restore(path, backup)
            raise ValidationError(
                f"Failed to write workbook '{path.name}'; restored from backup: {exc}"
            ) from exc

        # 8. Validate the final on-disk file; roll back on failure.
        try:
            final_tree = parse_workbook(path)
            validate_tree_structure(final_tree)
        except Exception as exc:
            self._restore(path, backup)
            raise ValidationError(
                f"Final workbook validation failed for '{path.name}'; restored from backup: {exc}"
            ) from exc

        # 9. Log.
        logger.info(
            "Workbook write applied",
            extra={"context": {"workbook": path.name, "backup": backup.relative_path}},
        )
        return backup

    def write_validated_bytes(self, path: Path, data: bytes) -> None:
        """Validate ``data`` as a workbook and atomically write it to ``path``.

        Used for restoring a backup: the bytes are validated before replacing
        the target file.

        Raises:
            ValidationError: If ``data`` is not a valid workbook.
        """
        validate_workbook_bytes(data)
        self._atomic_write(path, data)

    def _atomic_write(self, path: Path, data: bytes) -> None:
        """Write ``data`` to a temp file in ``path``'s directory and replace atomically."""
        directory = path.parent
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(directory))
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)  # atomic on Windows and POSIX
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _restore(self, path: Path, backup: BackupMetadata) -> None:
        """Restore ``path`` from a previously created backup after a failed write."""
        source = self._backups.resolve_backup(backup.relative_path)
        data = source.read_bytes()
        self._atomic_write(path, data)
        logger.warning(
            "Workbook restored from backup after failed write",
            extra={"context": {"workbook": path.name, "backup": backup.relative_path}},
        )
