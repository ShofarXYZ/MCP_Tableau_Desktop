"""Centralized configuration for tableau-desktop-mcp.

Configuration is loaded from environment variables (optionally from a ``.env``
file in the project root). No absolute paths are hard-coded in the core logic;
everything flows through :class:`Settings`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError

# Project root = three levels up from this file (src/tableau_mcp/config.py).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

#: Only workbooks with these extensions may be opened in this version.
ALLOWED_WORKBOOK_SUFFIXES: frozenset[str] = frozenset({".twb"})


class Settings(BaseSettings):
    """Runtime settings resolved from environment / ``.env``.

    Relative paths are resolved against :data:`PROJECT_ROOT`.
    """

    model_config = SettingsConfigDict(
        env_prefix="TABLEAU_MCP_",
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    workbooks_dir: Path = Field(default=Path("workbooks"))
    backups_dir: Path = Field(default=Path("backups"))
    logs_dir: Path = Field(default=Path("logs"))
    log_level: str = Field(default="INFO")
    max_file_size_bytes: int = Field(default=52_428_800)

    def _resolve(self, value: Path) -> Path:
        """Resolve a possibly-relative path against the project root."""
        return value if value.is_absolute() else (PROJECT_ROOT / value)

    @property
    def workbooks_path(self) -> Path:
        """Absolute path of the authorized workbooks folder."""
        return self._resolve(self.workbooks_dir)

    @property
    def backups_path(self) -> Path:
        """Absolute path of the backups folder."""
        return self._resolve(self.backups_dir)

    @property
    def logs_path(self) -> Path:
        """Absolute path of the logs folder."""
        return self._resolve(self.logs_dir)

    def ensure_directories(self) -> None:
        """Create the runtime directories if they do not yet exist."""
        for path in (self.workbooks_path, self.backups_path, self.logs_path):
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:  # pragma: no cover - filesystem dependent
                raise ConfigurationError(
                    f"Could not create required directory '{path}': {exc}"
                ) from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
