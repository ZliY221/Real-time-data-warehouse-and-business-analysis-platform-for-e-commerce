[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$testTable = "ecommerce.minute_metrics_smoke"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

$setupSql = @"
DROP TABLE IF EXISTS $testTable;
CREATE TABLE $testTable AS ecommerce.minute_metrics;
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
"@

$verifySql = @"
SELECT order_count, gmv, version
FROM $testTable FINAL
WHERE window_start = toDateTime64('2026-10-02 10:00:00.000', 3, 'UTC')
  AND region = '辽宁'
  AND channel = 'app'
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

    Write-Host "ClickHouse replacement smoke test passed."
}
finally {
    docker compose exec -T clickhouse clickhouse-client `
        --query "DROP TABLE IF EXISTS $testTable" 2>$null | Out-Null
    Pop-Location
}
