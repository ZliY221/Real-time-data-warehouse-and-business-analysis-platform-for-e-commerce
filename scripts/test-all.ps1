[CmdletBinding()]
param()

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
    & $runtimePython @runtimePythonArguments -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Python tests failed."
    }

    & $runtimePython @runtimePythonArguments -m data_quality.cli `
        --input "data/sample/order_events.ndjson" `
        --config "config/data-quality-rules.json" `
        --json-output "build/data-quality/report.json" `
        --markdown-output "build/data-quality/report.md"
    if ($LASTEXITCODE -ne 0) {
        throw "The reference data-quality gate failed."
    }

    if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
        throw "Node.js 20 or newer is required for dashboard tests."
    }

    & node --test (Join-Path $repoRoot "dashboard\tests\data.test.mjs")
    if ($LASTEXITCODE -ne 0) {
        throw "Dashboard tests failed."
    }

    & (Join-Path $PSScriptRoot "test-flink.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Java and Flink tests failed."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}

