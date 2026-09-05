"""Dependency container shared by all tool functions.

Centralizing the reader/backup/writer construction here keeps the individual
tool modules thin and makes them trivially testable by injecting a context that
points at a temporary directory.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import Settings, get_settings
from ..workbook.backup import BackupManager
from ..workbook.reader import WorkbookReader
from ..workbook.writer import WorkbookWriter


class ToolContext:
    """Holds the collaborators tools need: settings, reader, backup, writer."""

    def __init__(self, settings: Settings) -> None:
        """Build a context and ensure runtime directories exist."""
        settings.ensure_directories()
        self.settings = settings
        self.reader = WorkbookReader(
            workbooks_dir=settings.workbooks_path,
            max_file_size_bytes=settings.max_file_size_bytes,
        )
        self.backups = BackupManager(backups_dir=settings.backups_path)
        self.writer = WorkbookWriter(backup_manager=self.backups)


@lru_cache(maxsize=1)
def get_context() -> ToolContext:
    """Return a cached process-wide :class:`ToolContext`."""
    return ToolContext(get_settings())
