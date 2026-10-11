[CmdletBinding()]
param(
    [string]$PlanPath = "build/load/plan.json",
    [string]$EvidenceRoot = "build/load",
    [string]$OutputPath = "build/load/summary.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    Push-Location $repoRoot
    & $runtimePython -m load_testing.cli summarize `
        --plan $PlanPath `
        --evidence-root $EvidenceRoot `
        --output $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "Load experiment summary failed." }
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
