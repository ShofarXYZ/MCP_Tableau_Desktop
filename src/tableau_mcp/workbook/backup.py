"""Backup creation and restoration for workbook files.

Backups live in the configured backups directory and are named with a UTC
timestamp plus a short unique identifier, e.g.::

    dashboard_vendas.20260718T130501Z.a1b2c3d4.twb

Timestamps are timezone-aware (UTC) and unique ids are derived without leaking
sensitive data.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ..exceptions import BackupError
from ..models import BackupMetadata


class BackupManager:
    """Creates and restores timestamped backups of workbook files."""

    def __init__(self, backups_dir: Path) -> None:
        """Initialize with the backups directory (created if missing)."""
        self._backups_dir = backups_dir
        self._backups_dir.mkdir(parents=True, exist_ok=True)

    @property
    def backups_dir(self) -> Path:
        """The backups directory."""
        return self._backups_dir

    def _make_backup_name(self, original: Path, when: datetime) -> str:
        stamp = when.strftime("%Y%m%dT%H%M%SZ")
        unique = uuid.uuid4().hex[:8]
        return f"{original.stem}.{stamp}.{unique}{original.suffix}"

    def create_backup(self, source: Path, when: datetime | None = None) -> BackupMetadata:
        """Copy ``source`` into the backups directory with a unique timestamped name.

        Args:
            source: Absolute path to an existing workbook.
            when: Optional timestamp (defaults to now, UTC). Injectable for tests.

        Returns:
            Metadata describing the created backup.

        Raises:
            BackupError: If the copy fails.
        """
        if not source.exists():
            raise BackupError(f"Cannot back up missing file: '{source}'.")
        moment = when or datetime.now(tz=UTC)
        target = self._backups_dir / self._make_backup_name(source, moment)
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            raise BackupError(f"Failed to create backup of '{source.name}': {exc}") from exc
        return BackupMetadata(
            relative_path=target.name,
            original_filename=source.name,
            created_at=moment,
            size_bytes=target.stat().st_size,
        )

    def list_backups(self, original_filename: str | None = None) -> list[BackupMetadata]:
        """List available backups, optionally filtered to one original filename."""
        results: list[BackupMetadata] = []
        stem_filter = Path(original_filename).stem if original_filename else None
        for path in sorted(self._backups_dir.iterdir()):
            if not path.is_file():
                continue
            if stem_filter is not None and not path.name.startswith(f"{stem_filter}."):
                continue
            stat = path.stat()
            results.append(
                BackupMetadata(
                    relative_path=path.name,
                    original_filename=path.name.split(".")[0] + path.suffix,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    size_bytes=stat.st_size,
                )
            )
        return results

    def resolve_backup(self, backup_name: str) -> Path:
        """Resolve a backup filename to a safe path inside the backups directory.

        Raises:
            BackupError: On traversal or a missing backup.
        """
        if "/" in backup_name or "\\" in backup_name or ".." in backup_name:
            raise BackupError(f"Invalid backup name: '{backup_name}'.")
        path = (self._backups_dir / backup_name).resolve()
        root = self._backups_dir.resolve()
        if root != path and root not in path.parents:
            raise BackupError(f"Backup is outside the backups folder: '{backup_name}'.")
        if not path.exists() or not path.is_file():
            raise BackupError(f"Backup not found: '{backup_name}'.")
        return path
