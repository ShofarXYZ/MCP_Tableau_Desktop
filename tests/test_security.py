"""Security tests: path traversal, sandbox escape, extension checks."""

from __future__ import annotations

import pytest

from tableau_mcp.config import Settings
from tableau_mcp.exceptions import SecurityError, WorkbookNotFoundError
from tableau_mcp.tools import workbook_tools
from tableau_mcp.tools.context import ToolContext
from tableau_mcp.workbook.xml_utils import resolve_workbook_path


def test_path_traversal_blocked(sandbox: Settings) -> None:
    with pytest.raises(SecurityError):
        resolve_workbook_path("../secret.twb", sandbox.workbooks_path)


def test_absolute_escape_blocked(sandbox: Settings, tmp_path: object) -> None:
    with pytest.raises(SecurityError):
        resolve_workbook_path("C:/Windows/system.twb", sandbox.workbooks_path)


def test_nested_traversal_blocked(sandbox: Settings) -> None:
    with pytest.raises(SecurityError):
        resolve_workbook_path("sub/../../escape.twb", sandbox.workbooks_path)


def test_invalid_extension_blocked(sandbox: Settings) -> None:
    (sandbox.workbooks_path / "data.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SecurityError):
        resolve_workbook_path("data.txt", sandbox.workbooks_path)


def test_twbx_blocked(sandbox: Settings) -> None:
    (sandbox.workbooks_path / "packaged.twbx").write_text("x", encoding="utf-8")
    with pytest.raises(SecurityError):
        resolve_workbook_path("packaged.twbx", sandbox.workbooks_path)


def test_temp_extension_blocked(sandbox: Settings) -> None:
    with pytest.raises(SecurityError):
        resolve_workbook_path("work.tmp", sandbox.workbooks_path)


def test_missing_file_raises(sandbox: Settings) -> None:
    with pytest.raises(WorkbookNotFoundError):
        resolve_workbook_path("does_not_exist.twb", sandbox.workbooks_path)


def test_empty_filename_blocked(sandbox: Settings) -> None:
    with pytest.raises(SecurityError):
        resolve_workbook_path("   ", sandbox.workbooks_path)


def test_tool_reports_security_error(ctx: ToolContext) -> None:
    resp = workbook_tools.inspect_workbook("../../etc/passwd.twb", ctx)
    assert not resp.success
    assert resp.error is not None and resp.error.code == "security_error"
