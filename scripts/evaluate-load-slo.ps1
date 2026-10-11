[CmdletBinding()]
param(
    [string]$Summary = "build/load-experiment/summary.json",
    [string]$Policy = "config/operational-slos.json",
    [string]$Output = "build/load-experiment/slo-report.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    py -3 -m load_testing.cli evaluate-slo `
        --summary $Summary `
        --policy $Policy `
        --output $Output
    if ($LASTEXITCODE -ne 0) {
        throw "Load SLO evaluation failed."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
