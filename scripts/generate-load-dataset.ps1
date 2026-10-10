[CmdletBinding()]
param(
    [ValidateRange(1, 1000000)]
    [int]$Count = 10000,
    [ValidateRange(1, 100000)]
    [int]$EventTimeRate = 1000,
    [ValidatePattern('^[A-Za-z0-9-]{1,50}$')]
    [string]$Profile = "baseline",
    [int]$Seed = 2027,
    [string]$StartTime = "2026-10-02T10:00:00Z",
    [string]$OutputDirectory = "build/load"
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
$profileDirectory = Join-Path $resolvedOutput $Profile
$eventsPath = Join-Path $profileDirectory "events.ndjson"
$manifestPath = Join-Path $profileDirectory "manifest.json"
$previousPythonPath = $env:PYTHONPATH

if (-not (Get-Command $runtimePython -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Set the PYTHON environment variable if needed."
}

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython -m load_testing.cli generate `
        --count $Count `
        --seed $Seed `
        --event-time-rate $EventTimeRate `
        --profile $Profile `
        --start-time $StartTime `
        --output $eventsPath `
        --manifest-output $manifestPath
    if ($LASTEXITCODE -ne 0) {
        throw "The load dataset could not be generated."
    }
    Write-Host "Load dataset: $eventsPath"
    Write-Host "Generation manifest: $manifestPath"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
