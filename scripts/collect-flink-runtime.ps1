[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[0-9a-fA-F]{32}$')]
    [string]$JobId,
    [string]$RestUrl = "http://127.0.0.1:8081",
    [string]$OutputDirectory = "build/load/runtime",
    [ValidateRange(0, 120)]
    [int]$MetricsWaitSeconds = 20
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
}
else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
}
$previousPythonPath = $env:PYTHONPATH

if (-not (Get-Command $runtimePython -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Set the PYTHON environment variable if needed."
}

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython -m load_testing.cli collect `
        --job-id $JobId `
        --rest-url $RestUrl `
        --metrics-wait-seconds $MetricsWaitSeconds `
        --json-output (Join-Path $resolvedOutput "flink-runtime.json") `
        --markdown-output (Join-Path $resolvedOutput "flink-runtime.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Flink runtime evidence could not be collected."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
