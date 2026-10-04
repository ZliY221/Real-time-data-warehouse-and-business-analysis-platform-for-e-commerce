[CmdletBinding()]
param(
    [string]$InputPath = "data/sample/order_events.ndjson",
    [string]$Topic = "order-events"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$resolvedInput = if ([System.IO.Path]::IsPathRooted($InputPath)) {
    [System.IO.Path]::GetFullPath($InputPath)
}
else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $InputPath))
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found."
}
if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) {
    throw "Input file does not exist: $resolvedInput"
}

$records = @(Get-Content -LiteralPath $resolvedInput | Where-Object { $_.Trim().Length -gt 0 })
if ($records.Count -eq 0) {
    throw "Input file contains no records."
}

Push-Location $repoRoot
try {
    $records | docker compose exec -T kafka `
        /opt/kafka/bin/kafka-console-producer.sh `
        --bootstrap-server kafka:29092 `
        --topic $Topic `
        --producer-property acks=all
    if ($LASTEXITCODE -ne 0) {
        throw "Kafka producer failed."
    }
    Write-Host "Produced $($records.Count) records to $Topic."
}
finally {
    Pop-Location
}

