<#
.SYNOPSIS
    Build the InterScribe Windows installer.

.DESCRIPTION
    1. Compiles the tray app (requires .NET SDK 4.8 / msbuild).
    2. Runs Inno Setup to produce dist\InterScribe-Setup.exe.

.REQUIREMENTS
    - .NET SDK (dotnet CLI in PATH) — https://dot.net
    - Inno Setup 6 installed to default location, or iscc.exe in PATH
      https://jrsoftware.org/isdl.php
#>

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# ── Build tray app ────────────────────────────────────────────────────────────
Write-Host "Building tray app…"
dotnet build tray-app\TrayApp.csproj -c Release
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed" }

# ── Run Inno Setup ────────────────────────────────────────────────────────────
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $candidate = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $candidate) { $iscc = $candidate } else {
        throw "iscc.exe not found. Install Inno Setup 6 from https://jrsoftware.org/isdl.php"
    }
}

Write-Host "Running Inno Setup…"
& $iscc InterScribe.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host ""
Write-Host "Done — installer at: $PSScriptRoot\dist\InterScribe-Setup.exe"
