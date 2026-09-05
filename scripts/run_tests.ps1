# Runs the test suite.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& .\.venv\Scripts\python.exe -m pytest
