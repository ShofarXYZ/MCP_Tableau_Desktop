# Quickly inspects a workbook from the command line (no MCP client needed).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\inspect_workbook.ps1 dashboard_vendas.twb
param(
    [Parameter(Mandatory = $true)]
    [string]$Filename
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& .\.venv\Scripts\python.exe -c "import json, sys; from tableau_mcp.tools import workbook_tools; print(workbook_tools.inspect_workbook(sys.argv[1]).model_dump_json(indent=2))" $Filename
