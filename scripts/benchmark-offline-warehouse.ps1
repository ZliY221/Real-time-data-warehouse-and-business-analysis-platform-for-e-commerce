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
. (Join-Path $PSScriptRoot "python-runtime.ps1")
$pythonRuntime = Resolve-ProjectPython -MinimumVersion "3.11" -RepoRoot $repoRoot
$runtimePython = $pythonRuntime.Executable
$runtimePythonArguments = @($pythonRuntime.Arguments)

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
