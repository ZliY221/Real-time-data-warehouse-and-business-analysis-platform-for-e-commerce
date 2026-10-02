[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Find-Jdk17Home {
    $candidateHomes = [System.Collections.Generic.List[string]]::new()
    if ($env:JAVA_HOME) {
        $candidateHomes.Add($env:JAVA_HOME)
    }

    $currentJava = Get-Command java -ErrorAction SilentlyContinue
    if ($currentJava -and $currentJava.Source) {
        $candidateHomes.Add((Split-Path -Parent (Split-Path -Parent $currentJava.Source)))
    }

    if ($env:OS -eq "Windows_NT") {
        foreach ($searchRoot in @(
            (Join-Path $env:ProgramFiles "Microsoft"),
            (Join-Path $env:ProgramFiles "Eclipse Adoptium"),
            (Join-Path $env:ProgramFiles "Java")
        )) {
            if (Test-Path -LiteralPath $searchRoot -PathType Container) {
                Get-ChildItem -LiteralPath $searchRoot -Directory -ErrorAction SilentlyContinue |
                    Where-Object Name -Like "jdk-17*" |
                    Sort-Object Name -Descending |
                    ForEach-Object { $candidateHomes.Add($_.FullName) }
            }
        }
    }

    $seen = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase)
    foreach ($candidateHome in $candidateHomes) {
        if (-not $candidateHome -or -not $seen.Add($candidateHome)) {
            continue
        }
        $javaName = if ($env:OS -eq "Windows_NT") { "java.exe" } else { "java" }
        $javaPath = Join-Path $candidateHome "bin\$javaName"
        if (-not (Test-Path -LiteralPath $javaPath -PathType Leaf)) {
            continue
        }
        $versionText = (& $javaPath -version 2>&1 | Out-String)
        if ($versionText -match 'version "(?<major>\d+)') {
            if ([int]$Matches.major -ge 17) {
                return $candidateHome
            }
        }
    }

    throw "JDK 17 or newer was not found. Install JDK 17 or set JAVA_HOME."
}

$jdkHome = Find-Jdk17Home
if (-not (Get-Command mvn -ErrorAction SilentlyContinue)) {
    throw "Maven was not found on PATH."
}

$previousJavaHome = $env:JAVA_HOME
$previousPath = $env:Path
Push-Location (Join-Path $repoRoot "flink-job")
try {
    $env:JAVA_HOME = $jdkHome
    $env:Path = (Join-Path $jdkHome "bin") + [System.IO.Path]::PathSeparator + $previousPath
    java -version
    mvn --batch-mode --no-transfer-progress clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Flink Maven verification failed."
    }
}
finally {
    $env:JAVA_HOME = $previousJavaHome
    $env:Path = $previousPath
    Pop-Location
}

