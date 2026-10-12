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
$runtimePython = $null
$runtimePythonArguments = @()

if ($env:PYTHON) {
    if (-not (Get-Command $env:PYTHON -ErrorAction SilentlyContinue)) {
        throw "The Python executable configured in the PYTHON environment variable was not found."
    }
    & $env:PYTHON -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "The configured Python executable must be Python 3.11 or newer."
    }
    $runtimePython = $env:PYTHON
}
else {
    foreach ($candidate in @("python", "python3", "py")) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            $candidateArguments = @()
            if ($candidate -eq "py") { $candidateArguments = @("-3") }
            & $candidate @candidateArguments -c `
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) {
                $runtimePython = $candidate
                $runtimePythonArguments = $candidateArguments
                break
            }
        }
    }
}

if (-not $runtimePython) {
    throw "Python 3 was not found. Set the PYTHON environment variable if needed."
}

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
