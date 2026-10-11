[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$SloReport,
    [Parameter(Mandatory)][string]$ObservedAt,
    [string]$State = "build/load-experiment/slo-incidents.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = if ($env:PYTHON) {
    $env:PYTHON
}
elseif (Test-Path -LiteralPath (Join-Path $repoRoot ".venv\Scripts\python.exe")) {
    Join-Path $repoRoot ".venv\Scripts\python.exe"
}
elseif (Get-Command "py" -ErrorAction SilentlyContinue) {
    "py"
}
else {
    "python"
}
$pythonArguments = if ($pythonExecutable -eq "py") { @("-3") } else { @() }
$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonExecutable @pythonArguments -m load_testing.cli reconcile-alerts `
        --slo-report $SloReport `
        --state $State `
        --observed-at $ObservedAt
    if ($LASTEXITCODE -ne 0) { throw "SLO incident reconciliation failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
