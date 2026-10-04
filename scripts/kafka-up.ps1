[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

Push-Location $repoRoot
try {
    docker compose version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose v2 is unavailable."
    }

    docker compose up -d kafka
    if ($LASTEXITCODE -ne 0) {
        throw "Kafka container failed to start."
    }

    $health = ""
    foreach ($attempt in 1..30) {
        $health = docker inspect --format '{{.State.Health.Status}}' ecommerce-kafka 2>$null
        if ($health -eq "healthy") {
            break
        }
        Start-Sleep -Seconds 2
    }
    if ($health -ne "healthy") {
        docker compose logs kafka
        throw "Kafka did not become healthy within 60 seconds."
    }

    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server kafka:29092 `
        --create `
        --if-not-exists `
        --topic order-events `
        --partitions 3 `
        --replication-factor 1
    if ($LASTEXITCODE -ne 0) {
        throw "The order-events topic could not be created."
    }

    docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
        --bootstrap-server kafka:29092 `
        --describe `
        --topic order-events
    if ($LASTEXITCODE -ne 0) {
        throw "The order-events topic could not be described."
    }
}
finally {
    Pop-Location
}

