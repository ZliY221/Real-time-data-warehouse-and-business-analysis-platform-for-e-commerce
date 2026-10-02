[CmdletBinding()]
param(
    [switch]$RemoveData
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found."
}

Push-Location $repoRoot
try {
    if ($RemoveData) {
        docker compose down --volumes
    }
    else {
        docker compose down
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose shutdown failed."
    }
}
finally {
    Pop-Location
}

