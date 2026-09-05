[CmdletBinding()]
param(
    [switch]$RemoveRuntimeData
)

$ErrorActionPreference = 'Stop'
$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) {
    throw 'codex was not found in PATH.'
}

$serverName = 'keyboard-control'
& $codex.Source mcp get $serverName --json *> $null
if ($LASTEXITCODE -eq 0) {
    & $codex.Source mcp remove $serverName
    if ($LASTEXITCODE -ne 0) {
        throw "Could not remove '$serverName'."
    }
    Write-Host "Removed MCP server '$serverName'."
} else {
    Write-Host "MCP server '$serverName' is not installed."
}

if ($RemoveRuntimeData) {
    $runtimePath = Join-Path $env:LOCALAPPDATA 'CodexKeyboardMCP'
    $resolvedParent = (Resolve-Path -LiteralPath $env:LOCALAPPDATA).Path
    if (Test-Path -LiteralPath $runtimePath) {
        $resolvedRuntime = (Resolve-Path -LiteralPath $runtimePath).Path
        if (-not $resolvedRuntime.StartsWith($resolvedParent + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected runtime path: $resolvedRuntime"
        }
        Remove-Item -LiteralPath $resolvedRuntime -Recurse -Force
        Write-Host "Removed runtime data at '$resolvedRuntime'. This cannot be recovered from the script."
    }
}

