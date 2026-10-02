[CmdletBinding()]
param(
    [ValidateRange(1, 100000)]
    [int]$Count = 20,
    [string]$Topic = "order-events",
    [switch]$FromBeginning
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found."
}

$consumerArguments = @(
    "compose", "exec", "-T", "kafka",
    "/opt/kafka/bin/kafka-console-consumer.sh",
    "--bootstrap-server", "kafka:29092",
    "--topic", $Topic,
    "--max-messages", $Count,
    "--timeout-ms", "10000"
)
if ($FromBeginning) {
    $consumerArguments += "--from-beginning"
}

Push-Location $repoRoot
try {
    & docker @consumerArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Kafka consumer failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

