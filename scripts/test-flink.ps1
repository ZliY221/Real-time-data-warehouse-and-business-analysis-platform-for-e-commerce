[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$jdkHome = "C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"

if (-not (Test-Path -LiteralPath (Join-Path $jdkHome "bin\java.exe") -PathType Leaf)) {
    throw "JDK 17 was not found at $jdkHome. Update scripts/test-flink.ps1 for your local JDK."
}
if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
    throw "Maven was not found on PATH."
}

$previousJavaHome = $env:JAVA_HOME
$previousPath = $env:Path
Push-Location (Join-Path $repoRoot "flink-job")
try {
    $env:JAVA_HOME = $jdkHome
    $env:Path = (Join-Path $jdkHome "bin") + ";" + $previousPath
    java -version
    mvn --batch-mode --no-transfer-progress clean test
    if ($LASTEXITCODE -ne 0) {
        throw "Flink Maven tests failed."
    }
}
finally {
    $env:JAVA_HOME = $previousJavaHome
    $env:Path = $previousPath
    Pop-Location
}

