[CmdletBinding()]
param(
    [ValidateRange(1, 1000000)]
    [int]$Events = 50000,
    [ValidateRange(1, 20)]
    [int]$Trials = 5,
    [int]$Seed = 2027,
    [string]$OutputDirectory = "build/offline-warehouse"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = $null
$runtimePythonArguments = @()
if ($env:PYTHON) {
    if (-not (Get-Command $env:PYTHON -ErrorAction SilentlyContinue)) {
        throw "The Python executable configured in the PYTHON environment variable was not found."
    }
    $runtimePython = $env:PYTHON
}
else {
    foreach ($candidate in @("python", "python3", "py")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            $runtimePython = $candidate
            if ($candidate -eq "py") {
                $runtimePythonArguments = @("-3")
            }
            break
        }
    }
}
if (-not $runtimePython) {
    throw "Python 3 was not found. Set the PYTHON environment variable if needed."
}

$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython @runtimePythonArguments -m offline_warehouse.benchmark `
        --events $Events `
        --trials $Trials `
        --seed $Seed `
        --json-output (Join-Path $OutputDirectory "benchmark.json") `
        --markdown-output (Join-Path $OutputDirectory "benchmark.md")
    if ($LASTEXITCODE -ne 0) {
        throw "The offline warehouse benchmark failed."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
