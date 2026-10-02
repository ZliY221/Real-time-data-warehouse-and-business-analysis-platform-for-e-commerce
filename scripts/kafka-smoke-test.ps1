[CmdletBinding()]
param(
    [ValidateRange(1, 10000)]
    [int]$Count = 20,
    [int]$Seed = 2027
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$topic = "order-events-smoke-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$runtimePython = if ($env:PYTHON) { $env:PYTHON } else { "python" }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found."
}
if (-not (Get-Command $runtimePython -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Set the PYTHON environment variable if needed."
}

$inputFile = [System.IO.Path]::GetTempFileName()
$outputFile = [System.IO.Path]::GetTempFileName()

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & $runtimePython -m event_generator.cli `
        --count $Count `
        --seed $Seed `
        --output $inputFile
    if ($LASTEXITCODE -ne 0) {
        throw "Event generation failed."
    }

    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server kafka:29092 `
        --create `
        --if-not-exists `
        --topic $topic `
        --partitions 3 `
        --replication-factor 1
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke-test topic creation failed."
    }

    Get-Content -LiteralPath $inputFile | docker compose exec -T kafka `
        /opt/kafka/bin/kafka-console-producer.sh `
        --bootstrap-server kafka:29092 `
        --topic $topic `
        --command-property acks=all
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke-test production failed."
    }

    docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh `
        --bootstrap-server kafka:29092 `
        --topic $topic `
        --from-beginning `
        --max-messages $Count `
        --timeout-ms 15000 | Set-Content -LiteralPath $outputFile -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "Smoke-test consumption failed."
    }

    & $runtimePython -m event_generator.validate_cli `
        --input $outputFile `
        --expected-count $Count
    if ($LASTEXITCODE -ne 0) {
        throw "Consumed records did not pass contract validation."
    }
    Write-Host "Kafka smoke test passed for $Count records on topic $topic."
}
finally {
    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server kafka:29092 `
        --delete `
        --topic $topic 2>$null
    Pop-Location
    Remove-Item -LiteralPath $inputFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
}

