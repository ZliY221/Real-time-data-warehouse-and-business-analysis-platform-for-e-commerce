[CmdletBinding()]
param(
    [string]$State = "build/load-experiment/slo-incidents.json",
    [string]$Policy = "config/incident-routing.json",
    [string]$DeliveryLedger = "build/load-experiment/delivery-ledger.json",
    [string]$Output = "build/load-experiment/notification-outbox.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = if ($env:PYTHON) { $env:PYTHON } elseif (
    Test-Path -LiteralPath (Join-Path $repoRoot ".venv\Scripts\python.exe")
) { Join-Path $repoRoot ".venv\Scripts\python.exe" } elseif (
    Get-Command "py" -ErrorAction SilentlyContinue
) { "py" } else { "python" }
$pythonArguments = if ($pythonExecutable -eq "py") { @("-3") } else { @() }
$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $pythonExecutable @pythonArguments -m load_testing.cli plan-notifications `
        --state $State --policy $Policy --delivery-ledger $DeliveryLedger --output $Output
    if ($LASTEXITCODE -ne 0) { throw "Incident notification planning failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
