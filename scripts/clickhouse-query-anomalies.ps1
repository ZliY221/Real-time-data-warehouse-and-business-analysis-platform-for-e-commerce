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

$summaryQuery = @"
SELECT minute_start, anomaly_type, reason, anomaly_count
FROM ecommerce.event_anomaly_summary
ORDER BY minute_start DESC, anomaly_type, reason
LIMIT $Limit
FORMAT PrettyCompact
"@

$recentQuery = @"
SELECT
    detected_at,
    anomaly_type,
    anomaly_key,
    reason,
    payload_size_bytes
FROM
(
    SELECT
        detected_at,
        'rejected' AS anomaly_type,
        rejection_id AS anomaly_key,
        error_type AS reason,
        payload_size_bytes
    FROM ecommerce.rejected_order_events FINAL

    UNION ALL

    SELECT
        detected_at,
        'late' AS anomaly_type,
        event_id AS anomaly_key,
        'window_late' AS reason,
        toUInt32(0) AS payload_size_bytes
    FROM ecommerce.late_order_events FINAL
)
ORDER BY detected_at DESC, anomaly_type, anomaly_key
LIMIT $Limit
FORMAT PrettyCompact
"@

Push-Location $repoRoot
try {
    Write-Host "Anomaly counts by minute and reason"
    docker compose exec -T clickhouse clickhouse-client --query $summaryQuery
    if ($LASTEXITCODE -ne 0) {
        throw "The ClickHouse anomaly summary query failed."
    }

    Write-Host "Recent distinct anomaly records"
    docker compose exec -T clickhouse clickhouse-client --query $recentQuery
    if ($LASTEXITCODE -ne 0) {
        throw "The ClickHouse anomaly detail query failed."
    }
}
finally {
    Pop-Location
}
