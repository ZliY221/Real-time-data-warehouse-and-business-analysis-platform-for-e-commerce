[CmdletBinding()]
param(
    [string]$OutputPath = "build/load/plan.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    [System.IO.Path]::GetFullPath($OutputPath)
}
else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputPath))
}
$previousPythonPath = $env:PYTHONPATH

try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython -m load_testing.cli plan --output $resolvedOutput
    if ($LASTEXITCODE -ne 0) { throw "Load plan generation failed." }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}
