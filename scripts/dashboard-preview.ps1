[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    Write-Host "Preview data only. Open http://127.0.0.1:$Port/dashboard"
    python -m uvicorn metrics_api.preview:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "The dashboard preview stopped with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
