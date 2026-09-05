# Runs the MCP server over stdio.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_server.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& .\.venv\Scripts\python.exe -m tableau_mcp.server
