# Runs lint (ruff) and type checking (mypy).
# Usage: powershell -ExecutionPolicy Bypass -File scripts\check.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = ".\.venv\Scripts\python.exe"

Write-Host "== ruff check =="
& $py -m ruff check src tests

Write-Host "== ruff format (check) =="
& $py -m ruff format --check src tests

Write-Host "== mypy =="
& $py -m mypy

Write-Host "All checks passed."
