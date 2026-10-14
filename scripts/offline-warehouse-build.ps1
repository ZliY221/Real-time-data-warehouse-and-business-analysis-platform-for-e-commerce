[CmdletBinding()]
param(
    [string]$InputPath = "data/sample/order_events.ndjson",
    [string]$DatabasePath = "build/offline-warehouse/ecommerce.duckdb",
    [string]$JsonReportPath = "build/offline-warehouse/report.json",
    [string]$MarkdownReportPath = "build/offline-warehouse/report.md"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
. (Join-Path $PSScriptRoot "python-runtime.ps1")
$pythonRuntime = Resolve-ProjectPython -MinimumVersion "3.11" -RepoRoot $repoRoot
$runtimePython = $pythonRuntime.Executable
$runtimePythonArguments = @($pythonRuntime.Arguments)

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython @runtimePythonArguments -m offline_warehouse.cli `
        --input $InputPath `
        --database $DatabasePath
    if ($LASTEXITCODE -ne 0) {
        throw "The offline warehouse load failed."
    }

    & $runtimePython @runtimePythonArguments -m offline_warehouse.report `
        --database $DatabasePath `
        --json-output $JsonReportPath `
        --markdown-output $MarkdownReportPath
    if ($LASTEXITCODE -ne 0) {
        throw "The offline warehouse report could not be exported."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
