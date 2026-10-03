[CmdletBinding()]
param(
    [string]$OutputDirectory = "build/data-quality"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    python -m data_quality.cli `
        --input "data/quality/order_events_with_quality_issues.ndjson" `
        --config "config/data-quality-rules.json" `
        --json-output (Join-Path $OutputDirectory "failed-report.json") `
        --markdown-output (Join-Path $OutputDirectory "failed-report.md") `
        --history-db (Join-Path $OutputDirectory "history.db")
    $qualityExitCode = $LASTEXITCODE
    if ($qualityExitCode -ne 1) {
        throw "Expected the demonstration batch to fail quality rules with exit code 1, got $qualityExitCode."
    }
    Write-Host "Expected quality failure recorded successfully."
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
