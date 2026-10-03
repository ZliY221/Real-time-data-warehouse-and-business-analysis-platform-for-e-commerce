[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$testTable = "ecommerce.minute_metrics_smoke"
$rejectedTestTable = "ecommerce.rejected_order_events_smoke"
$lateTestTable = "ecommerce.late_order_events_smoke"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

$setupSql = @"
DROP TABLE IF EXISTS $testTable;
DROP TABLE IF EXISTS $rejectedTestTable;
DROP TABLE IF EXISTS $lateTestTable;
CREATE TABLE $testTable AS ecommerce.minute_metrics;
CREATE TABLE $rejectedTestTable AS ecommerce.rejected_order_events;
CREATE TABLE $lateTestTable AS ecommerce.late_order_events;
INSERT INTO $testTable
    (window_start, window_end, region, channel, order_count, gmv, version, processed_at)
VALUES
    (toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC'),
     toDateTime64('2026-10-02 10:01:00.000', 3, 'UTC'),
     '辽宁', 'app', 1, 10.00, 1,
     toDateTime64('2026-10-02 10:01:01.000', 3, 'UTC')),
    (toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC'),
     toDateTime64('2026-10-02 10:01:00.000', 3, 'UTC'),
     '辽宁', 'app', 2, 30.00, 2,
     toDateTime64('2026-10-02 10:01:02.000', 3, 'UTC'));
INSERT INTO $rejectedTestTable
    (rejection_id, error_type, payload_size_bytes, detected_at, version)
VALUES
    ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
     'malformed_json', 12,
     toDateTime64('2026-10-02 10:01:01.000', 3, 'UTC'), 1),
    ('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
     'malformed_json', 18,
     toDateTime64('2026-10-02 10:01:02.000', 3, 'UTC'), 2);
INSERT INTO $lateTestTable
    (event_id, order_id, event_time, ingest_time, region, channel,
     total_amount, detected_at, version)
VALUES
    ('evt-late-smoke', 'ord-late-smoke',
     toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC'),
     toDateTime64('2026-10-02 10:00:04.000', 3, 'UTC'),
     '辽宁', 'app', 10.00,
     toDateTime64('2026-10-02 10:02:01.000', 3, 'UTC'), 1),
    ('evt-late-smoke', 'ord-late-smoke',
     toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC'),
     toDateTime64('2026-10-02 10:00:04.000', 3, 'UTC'),
     '辽宁', 'app', 10.00,
     toDateTime64('2026-10-02 10:02:02.000', 3, 'UTC'), 2);
"@

$verifySql = @"
SELECT order_count, gmv, version
FROM $testTable FINAL
WHERE window_start = toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC')
  AND region = '辽宁'
  AND channel = 'app'
FORMAT JSONEachRow
"@

$verifyRejectedSql = @"
SELECT count() AS row_count, max(version) AS version, any(payload_size_bytes) AS payload_size_bytes
FROM $rejectedTestTable FINAL
FORMAT JSONEachRow
"@

$verifyLateSql = @"
SELECT count() AS row_count, max(version) AS version, any(total_amount) AS total_amount
FROM $lateTestTable FINAL
FORMAT JSONEachRow
"@

Push-Location $repoRoot
try {
    docker compose exec -T clickhouse clickhouse-client --multiquery --query $setupSql
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse smoke-test fixtures could not be created."
    }

    $output = docker compose exec -T clickhouse clickhouse-client --query $verifySql
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse smoke-test query failed."
    }
    $rows = @($output | Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
    if ($rows.Count -ne 1) {
        throw "Expected one deduplicated metric row, found $($rows.Count)."
    }
    $row = $rows[0]
    if ([long]$row.order_count -ne 2L -or [decimal]$row.gmv -ne [decimal]30 -or [long]$row.version -ne 2L) {
        throw "ClickHouse did not retain the latest metric version."
    }

    $rejectedOutput = docker compose exec -T clickhouse clickhouse-client --query $verifyRejectedSql
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse rejected-event smoke-test query failed."
    }
    $rejectedRow = $rejectedOutput | ConvertFrom-Json
    if ([long]$rejectedRow.row_count -ne 1L `
            -or [long]$rejectedRow.version -ne 2L `
            -or [long]$rejectedRow.payload_size_bytes -ne 18L) {
        throw "ClickHouse did not replace the replayed rejected-event record."
    }

    $lateOutput = docker compose exec -T clickhouse clickhouse-client --query $verifyLateSql
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse late-event smoke-test query failed."
    }
    $lateRow = $lateOutput | ConvertFrom-Json
    if ([long]$lateRow.row_count -ne 1L `
            -or [long]$lateRow.version -ne 2L `
            -or [decimal]$lateRow.total_amount -ne [decimal]10) {
        throw "ClickHouse did not replace the replayed late-event record."
    }

    Write-Host "ClickHouse metric and anomaly replacement smoke test passed."
}
finally {
    $cleanupSql = @"
DROP TABLE IF EXISTS $testTable;
DROP TABLE IF EXISTS $rejectedTestTable;
DROP TABLE IF EXISTS $lateTestTable;
"@
    docker compose exec -T clickhouse clickhouse-client `
        --multiquery --query $cleanupSql 2>$null | Out-Null
    Pop-Location
}
