[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$serverPath = (Resolve-Path -LiteralPath (Join-Path $projectRoot 'run_server.py')).Path

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonLauncher) {
    throw 'Python launcher py.exe was not found. Install Python 3.11 or newer first.'
}

& $pythonLauncher.Source -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.11 or newer is required.'
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) {
    throw 'codex was not found in PATH. Install or open Codex CLI first.'
}

$serverName = 'keyboard-control'
& $codex.Source mcp get $serverName --json *> $null
$alreadyInstalled = $LASTEXITCODE -eq 0
if ($alreadyInstalled -and -not $Force) {
    throw "MCP server '$serverName' already exists. Re-run with -Force to replace it."
}
if ($alreadyInstalled) {
    & $codex.Source mcp remove $serverName
    if ($LASTEXITCODE -ne 0) {
        throw "Could not remove the existing '$serverName' MCP configuration."
    }
}

& $codex.Source mcp add $serverName -- $pythonLauncher.Source -3 $serverPath
if ($LASTEXITCODE -ne 0) {
    throw 'codex mcp add failed.'
}

Write-Host "Installed MCP server '$serverName'. Restart Codex, then call keyboard_status."

