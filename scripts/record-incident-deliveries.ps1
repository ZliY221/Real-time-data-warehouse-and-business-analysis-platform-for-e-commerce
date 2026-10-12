[CmdletBinding()]
param(
    [string]$Outbox = "build/load-experiment/notification-outbox.json",
    [string]$Receipts = "build/load-experiment/delivery-receipts.json",
    [string]$Ledger = "build/load-experiment/delivery-ledger.json",
    [string]$Output = "build/load-experiment/delivery-report.json"
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
    & $pythonExecutable @pythonArguments -m load_testing.cli record-notification-deliveries `
        --outbox $Outbox --receipts $Receipts --ledger $Ledger --output $Output
    if ($LASTEXITCODE -ne 0) { throw "Incident delivery receipt reconciliation failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
