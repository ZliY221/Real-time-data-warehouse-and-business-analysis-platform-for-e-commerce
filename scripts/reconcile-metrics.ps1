[CmdletBinding()]
param(
    [string]$Events = "data/sample/order_events.ndjson",
    [string]$ActualMetrics = "build/reconciliation/actual_metrics.ndjson",
    [string]$LateEvents = "build/reconciliation/late_events.ndjson",
    [string]$JsonOutput = "build/reconciliation/report.json",
    [string]$MarkdownOutput = "build/reconciliation/report.md"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }

if (-not (Get-Command $runtimePython -ErrorAction SilentlyContinue)) {
    throw "Python 3 was not found. Set the PYTHON environment variable if needed."
}

$arguments = @(
    "-m", "reconciliation.cli", "compare",
    "--events", $Events,
    "--actual", $ActualMetrics,
    "--json-output", $JsonOutput,
    "--markdown-output", $MarkdownOutput
)

$previousPythonPath = $env:PYTHONPATH
Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    $lateEventsPath = if ([System.IO.Path]::IsPathRooted($LateEvents)) {
        $LateEvents
    }
    else {
        Join-Path $repoRoot $LateEvents
    }
    if (Test-Path -LiteralPath $lateEventsPath -PathType Leaf) {
        $arguments += @("--late-events", $LateEvents)
    }
    & $runtimePython @arguments
    if ($LASTEXITCODE -eq 1) {
        throw "Batch and stream metrics do not match. Review $MarkdownOutput."
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Metric reconciliation could not be completed."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
