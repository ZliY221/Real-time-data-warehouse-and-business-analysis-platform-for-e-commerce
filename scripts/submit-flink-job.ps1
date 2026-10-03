[CmdletBinding()]
param(
    [string]$BootstrapServers = "localhost:9092",
    [string]$Topic = "order-events",
    [string]$GroupId = "ecommerce-order-metrics",
    [ValidateSet("committed", "earliest", "latest")]
    [string]$StartingOffsets = "committed",
    [ValidateRange(0, 3600)]
    [int]$OutOfOrdernessSeconds = 10,
    [ValidateRange(1, 3600)]
    [int]$IdlenessSeconds = 60,
    [ValidateRange(1, 8760)]
    [int]$DeduplicationTtlHours = 24,
    [ValidateRange(0, 3600)]
    [int]$AllowedLatenessSeconds = 0,
    [ValidateRange(1, 3600)]
    [int]$CheckpointIntervalSeconds = 10,
    [ValidateRange(1, 128)]
    [int]$Parallelism = 1,
    [ValidateSet("clickhouse", "print", "both")]
    [string]$MetricsSink = "clickhouse",
    [string]$ClickHouseUrl = "jdbc:clickhouse://localhost:8123/ecommerce",
    [string]$ClickHouseUser = "default",
    [ValidateRange(1, 10000)]
    [int]$ClickHouseBatchSize = 100,
    [ValidateRange(1, 60000)]
    [int]$ClickHouseBatchIntervalMs = 1000,
    [ValidateRange(0, 100)]
    [int]$ClickHouseMaxRetries = 3
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$jobJar = Join-Path $repoRoot "flink-job\target\ecommerce-flink-job-0.1.0-SNAPSHOT.jar"

if (-not (Get-Command flink -ErrorAction SilentlyContinue)) {
    throw "The Flink CLI was not found. Install Flink 1.20.1 and add its bin directory to PATH."
}
if (-not (Test-Path -LiteralPath $jobJar -PathType Leaf)) {
    throw "The job JAR was not found. Build it with 'mvn -f flink-job/pom.xml clean package'."
}

& flink run --detached `
    --class com.zhangliyang.portfolio.job.KafkaOrderMetricsJob `
    $jobJar `
    --bootstrap-servers $BootstrapServers `
    --topic $Topic `
    --group-id $GroupId `
    --starting-offsets $StartingOffsets `
    --out-of-orderness-seconds $OutOfOrdernessSeconds `
    --idleness-seconds $IdlenessSeconds `
    --deduplication-ttl-hours $DeduplicationTtlHours `
    --allowed-lateness-seconds $AllowedLatenessSeconds `
    --checkpoint-interval-seconds $CheckpointIntervalSeconds `
    --parallelism $Parallelism `
    --metrics-sink $MetricsSink `
    --clickhouse-url $ClickHouseUrl `
    --clickhouse-user $ClickHouseUser `
    --clickhouse-batch-size $ClickHouseBatchSize `
    --clickhouse-batch-interval-ms $ClickHouseBatchIntervalMs `
    --clickhouse-max-retries $ClickHouseMaxRetries

if ($LASTEXITCODE -ne 0) {
    throw "The Flink job submission failed with exit code $LASTEXITCODE."
}
