[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
. (Join-Path $PSScriptRoot "python-runtime.ps1")
$pythonRuntime = Resolve-ProjectPython -MinimumVersion "3.11" -RepoRoot $repoRoot
$pythonExecutable = $pythonRuntime.Executable
$pythonArguments = @($pythonRuntime.Arguments)

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    $arguments = @(
        "-m", "uvicorn",
        "metrics_api.app:app",
        "--host", "127.0.0.1",
        "--port", $Port
    )
    if ($Reload) {
        $arguments += "--reload"
    }

    & $pythonExecutable @pythonArguments @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "The metrics API stopped with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
