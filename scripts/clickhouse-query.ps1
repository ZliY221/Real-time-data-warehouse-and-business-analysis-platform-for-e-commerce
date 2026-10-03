[CmdletBinding()]
param(
    [ValidateRange(1, 1000)]
    [int]$Limit = 20
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

$query = @"
SELECT
    window_start,
    region,
    channel,
    order_count,
    gmv,
    average_order_value,
    processed_at
FROM ecommerce.minute_metrics_latest
ORDER BY window_start DESC, region, channel
LIMIT $Limit
FORMAT PrettyCompact
"@

Push-Location $repoRoot
try {
    docker compose exec -T clickhouse clickhouse-client --query $query
    if ($LASTEXITCODE -ne 0) {
        throw "The ClickHouse metrics query failed."
    }
}
finally {
    Pop-Location
}
