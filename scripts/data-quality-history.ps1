[CmdletBinding()]
param(
    [string]$OutputDirectory = "build/data-quality",
    [string]$RuleId = "channel-share-drift",
    [ValidateRange(1, 500)]
    [int]$Limit = 50
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    python -m data_quality.history_cli `
        --database (Join-Path $OutputDirectory "history.db") `
        --limit $Limit `
        --rule-id $RuleId `
        --json-output (Join-Path $OutputDirectory "history.json") `
        --markdown-output (Join-Path $OutputDirectory "history.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Data-quality history export failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
