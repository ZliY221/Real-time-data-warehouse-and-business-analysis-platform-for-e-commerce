[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install Docker Desktop and ensure 'docker' is on PATH."
}

Push-Location $repoRoot
try {
    docker compose up -d clickhouse
    if ($LASTEXITCODE -ne 0) {
        throw "ClickHouse container failed to start."
    }

    $health = ""
    foreach ($attempt in 1..30) {
        $health = docker inspect --format '{{.State.Health.Status}}' ecommerce-clickhouse 2>$null
        if ($health -eq "healthy") {
            break
        }
        Start-Sleep -Seconds 2
    }
    if ($health -ne "healthy") {
        docker compose logs clickhouse
        throw "ClickHouse did not become healthy within 60 seconds."
    }

    $schemaPath = Join-Path $repoRoot "infra\clickhouse\init\001_schema.sql"
    $schema = Get-Content -LiteralPath $schemaPath -Raw
    docker compose exec -T clickhouse clickhouse-client --multiquery --query $schema
    if ($LASTEXITCODE -ne 0) {
        throw "The ClickHouse schema could not be applied."
    }

    foreach ($table in @("minute_metrics", "rejected_order_events", "late_order_events")) {
        docker compose exec -T clickhouse clickhouse-client `
            --query "DESCRIBE TABLE ecommerce.$table" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "The ClickHouse $table table was not initialized."
        }
    }
}
finally {
    Pop-Location
}
