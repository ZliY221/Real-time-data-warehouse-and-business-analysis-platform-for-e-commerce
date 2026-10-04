[CmdletBinding()]
param(
    [string]$Start = "2026-10-02T10:00:00Z",
    [string]$End = "2026-10-02T10:01:00Z",
    [ValidatePattern("^[a-z][a-z0-9_]{0,62}$")]
    [string]$Database = "ecommerce",
    [string]$MetricsOutput = "build/reconciliation/actual_metrics.ndjson",
    [string]$LateEventsOutput = "build/reconciliation/late_events.ndjson"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Get-OutputPath([string]$Path) {
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}
$parsedStart = [DateTimeOffset]::MinValue
$parsedEnd = [DateTimeOffset]::MinValue
if (-not [DateTimeOffset]::TryParse($Start, [ref]$parsedStart) `
        -or -not [DateTimeOffset]::TryParse($End, [ref]$parsedEnd) `
        -or $parsedStart -ge $parsedEnd) {
    throw "Start and End must be valid timestamps and Start must be earlier than End."
}
if (($parsedEnd - $parsedStart).TotalDays -gt 7) {
    throw "The reconciliation export range must not exceed 7 days."
}
$clickHouseStart = $parsedStart.UtcDateTime.ToString(
    "yyyy-MM-dd HH:mm:ss.fff",
    [Globalization.CultureInfo]::InvariantCulture)
$clickHouseEnd = $parsedEnd.UtcDateTime.ToString(
    "yyyy-MM-dd HH:mm:ss.fff",
    [Globalization.CultureInfo]::InvariantCulture)

$metricsQuery = @"
SELECT
    formatDateTime(m.window_start, '%Y-%m-%dT%H:%i:%SZ', 'UTC') AS window_start,
    formatDateTime(m.window_end, '%Y-%m-%dT%H:%i:%SZ', 'UTC') AS window_end,
    m.region,
    m.channel,
    m.order_count,
    toString(m.gmv) AS gmv
FROM $Database.minute_metrics_latest AS m
WHERE m.window_start >= {start:DateTime64(3, 'UTC')}
  AND m.window_start < {end:DateTime64(3, 'UTC')}
ORDER BY window_start, region, channel
FORMAT JSONEachRow
"@

$lateEventsQuery = @"
SELECT event_id
FROM $Database.late_order_events FINAL
WHERE event_time >= {start:DateTime64(3, 'UTC')}
  AND event_time < {end:DateTime64(3, 'UTC')}
ORDER BY event_id
FORMAT JSONEachRow
"@

Push-Location $repoRoot
try {
    $metricsPath = Get-OutputPath $MetricsOutput
    $lateEventsPath = Get-OutputPath $LateEventsOutput
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($metricsPath)) |
        Out-Null
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($lateEventsPath)) |
        Out-Null

    $metrics = docker compose exec -T clickhouse clickhouse-client `
        "--param_start=$clickHouseStart" `
        "--param_end=$clickHouseEnd" `
        --query $metricsQuery
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse minute metrics could not be exported."
    }
    [System.IO.File]::WriteAllLines($metricsPath, [string[]]@($metrics))

    $lateEvents = docker compose exec -T clickhouse clickhouse-client `
        "--param_start=$clickHouseStart" `
        "--param_end=$clickHouseEnd" `
        --query $lateEventsQuery
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse late events could not be exported."
    }
    [System.IO.File]::WriteAllLines($lateEventsPath, [string[]]@($lateEvents))

    Write-Host "Exported reconciliation inputs to $metricsPath and $lateEventsPath."
}
finally {
    Pop-Location
}
