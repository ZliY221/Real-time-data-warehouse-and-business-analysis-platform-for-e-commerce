[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$KeepDataResources
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$runId = [DateTimeOffset]::UtcNow.ToString("yyyyMMddHHmmss")
$topic = "order-events-e2e-$runId"
$groupId = "ecommerce-e2e-$runId"
$database = "ecommerce_acceptance_$runId"
$businessStart = "2026-10-02T10:00:00Z"
$businessEnd = "2026-10-02T10:01:00Z"
$triggerStart = "2026-10-02T10:01:15Z"
$clickHouseStart = [DateTimeOffset]::Parse($businessStart).UtcDateTime.ToString(
    "yyyy-MM-dd HH:mm:ss.fff",
    [Globalization.CultureInfo]::InvariantCulture)
$clickHouseEnd = [DateTimeOffset]::Parse($businessEnd).UtcDateTime.ToString(
    "yyyy-MM-dd HH:mm:ss.fff",
    [Globalization.CultureInfo]::InvariantCulture)
$runDirectory = Join-Path $repoRoot "build\e2e\$runId"
$businessEvents = Join-Path $runDirectory "business_events.ndjson"
$triggerEvents = Join-Path $runDirectory "watermark_events.ndjson"
$expectedMetrics = Join-Path $runDirectory "expected_metrics.ndjson"
$actualMetrics = Join-Path $runDirectory "actual_metrics.ndjson"
$lateEvents = Join-Path $runDirectory "late_events.ndjson"
$jsonReport = Join-Path $runDirectory "report.json"
$markdownReport = Join-Path $runDirectory "report.md"
$manifestPath = Join-Path $runDirectory "manifest.json"
$flinkRuntimeJson = Join-Path $runDirectory "flink-runtime.json"
$flinkRuntimeMarkdown = Join-Path $runDirectory "flink-runtime.md"
$jobId = $null
$topicCreated = $false
$databaseCreated = $false
$previousPythonPath = $env:PYTHONPATH

if ($database -notmatch '^[a-z][a-z0-9_]{0,62}$') {
    throw "Generated acceptance database name is unsafe."
}
if ($topic -notmatch '^[a-zA-Z0-9._-]+$') {
    throw "Generated acceptance topic name is unsafe."
}
foreach ($command in @("docker", "flink", $runtimePython)) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command was not found: $command"
    }
}

[System.IO.Directory]::CreateDirectory($runDirectory) | Out-Null

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"

    & flink list | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "A reachable local Flink cluster is required before acceptance starts."
    }

    if (-not $SkipBuild) {
        & (Join-Path $PSScriptRoot "test-flink.ps1")
        if ($LASTEXITCODE -ne 0) {
            throw "The Flink job could not be built."
        }
    }

    & (Join-Path $PSScriptRoot "kafka-up.ps1")
    & (Join-Path $PSScriptRoot "clickhouse-up.ps1")

    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server kafka:29092 `
        --create `
        --topic $topic `
        --partitions 1 `
        --replication-factor 1
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated acceptance topic could not be created."
    }
    $topicCreated = $true

    $schemaPath = Join-Path $repoRoot "infra\clickhouse\init\001_schema.sql"
    $schema = Get-Content -LiteralPath $schemaPath -Raw
    $acceptanceSchema = $schema.Replace(
        "CREATE DATABASE IF NOT EXISTS ecommerce;",
        "CREATE DATABASE IF NOT EXISTS $database;").Replace(
        "ecommerce.",
        "$database.")
    docker compose exec -T clickhouse clickhouse-client `
        --query "CREATE DATABASE IF NOT EXISTS $database"
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated acceptance database could not be created."
    }
    $databaseCreated = $true
    docker compose exec -T clickhouse clickhouse-client `
        --multiquery --query $acceptanceSchema
    if ($LASTEXITCODE -ne 0) {
        throw "The isolated acceptance database could not be initialized."
    }

    & $runtimePython -m event_generator.cli `
        --count 20 --seed 2027 --start-time $businessStart --output $businessEvents
    if ($LASTEXITCODE -ne 0) {
        throw "Business acceptance events could not be generated."
    }
    & $runtimePython -m event_generator.cli `
        --count 3 --seed 9090 --start-time $triggerStart --output $triggerEvents
    if ($LASTEXITCODE -ne 0) {
        throw "Watermark advance events could not be generated."
    }
    & $runtimePython -m reconciliation.cli baseline `
        --events $businessEvents --output $expectedMetrics
    if ($LASTEXITCODE -ne 0) {
        throw "The acceptance baseline could not be generated."
    }
    $expectedMetricKeys = @(
        Get-Content -LiteralPath $expectedMetrics | Where-Object { $_.Trim() }
    ).Count

    $jobOutput = @(
        & (Join-Path $PSScriptRoot "submit-flink-job.ps1") `
            -Topic $topic `
            -GroupId $groupId `
            -StartingOffsets earliest `
            -Parallelism 1 `
            -ClickHouseUrl "jdbc:clickhouse://localhost:8123/$database" 2>&1
    )
    $jobOutput | ForEach-Object { Write-Host $_ }
    $jobMatch = [regex]::Match(
        ($jobOutput | Out-String),
        '(?i)JobID\s+([0-9a-f]{32})')
    if (-not $jobMatch.Success) {
        throw "The submitted Flink JobID could not be read from CLI output."
    }
    $jobId = $jobMatch.Groups[1].Value

    & (Join-Path $PSScriptRoot "kafka-produce-sample.ps1") `
        -InputPath $businessEvents -Topic $topic
    & (Join-Path $PSScriptRoot "kafka-produce-sample.ps1") `
        -InputPath $triggerEvents -Topic $topic

    $countQuery = @"
SELECT count()
FROM $database.minute_metrics FINAL
WHERE window_start >= {start:DateTime64(3, 'UTC')}
  AND window_start < {end:DateTime64(3, 'UTC')}
"@
    $observedMetricKeys = 0
    foreach ($attempt in 1..45) {
        $countOutput = docker compose exec -T clickhouse clickhouse-client `
            "--param_start=$clickHouseStart" `
            "--param_end=$clickHouseEnd" `
            --query $countQuery
        $countText = ($countOutput | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $countText -match '^\d+$') {
            $observedMetricKeys = [int]$countText
            if ($observedMetricKeys -eq $expectedMetricKeys) {
                break
            }
        }
        Start-Sleep -Seconds 2
    }
    if ($observedMetricKeys -ne $expectedMetricKeys) {
        throw "Expected $expectedMetricKeys metric keys, observed $observedMetricKeys."
    }

    & (Join-Path $PSScriptRoot "clickhouse-export-reconciliation.ps1") `
        -Start $businessStart `
        -End $businessEnd `
        -Database $database `
        -MetricsOutput $actualMetrics `
        -LateEventsOutput $lateEvents
    & (Join-Path $PSScriptRoot "reconcile-metrics.ps1") `
        -Events $businessEvents `
        -ActualMetrics $actualMetrics `
        -LateEvents $lateEvents `
        -JsonOutput $jsonReport `
        -MarkdownOutput $markdownReport

    & $runtimePython -m load_testing.cli collect `
        --job-id $jobId `
        --rest-url "http://127.0.0.1:8081" `
        --json-output $flinkRuntimeJson `
        --markdown-output $flinkRuntimeMarkdown
    if ($LASTEXITCODE -ne 0) {
        throw "The Flink runtime snapshot could not be collected."
    }

    $manifest = [ordered]@{
        run_id = $runId
        completed_at = [DateTimeOffset]::UtcNow.ToString("o")
        topic = $topic
        database = $database
        flink_job_id = $jobId
        business_start = $businessStart
        business_end = $businessEnd
        business_events = 20
        watermark_events = 3
        expected_metric_keys = $expectedMetricKeys
        observed_metric_keys = $observedMetricKeys
        report = $jsonReport
        flink_runtime = $flinkRuntimeJson
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($manifestPath, $manifest + "`n")
    Write-Host "End-to-end acceptance PASS. Evidence: $runDirectory"
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    if ($jobId) {
        try {
            & flink cancel $jobId 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "The Flink acceptance job may still be running: $jobId"
            }
        }
        catch {
            Write-Warning "The Flink acceptance job could not be cancelled: $($_.Exception.Message)"
        }
    }
    if (-not $KeepDataResources) {
        if ($topicCreated) {
            try {
                docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
                    --bootstrap-server kafka:29092 `
                    --delete `
                    --topic $topic 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "The acceptance topic may still exist: $topic"
                }
            }
            catch {
                Write-Warning "The acceptance topic could not be removed: $($_.Exception.Message)"
            }
        }
        if ($databaseCreated) {
            try {
                docker compose exec -T clickhouse clickhouse-client `
                    --query "DROP DATABASE IF EXISTS $database SYNC" 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Write-Warning "The acceptance database may still exist: $database"
                }
            }
            catch {
                Write-Warning (
                    "The acceptance database could not be removed: " +
                    $_.Exception.Message)
            }
        }
    }
    Pop-Location
}
