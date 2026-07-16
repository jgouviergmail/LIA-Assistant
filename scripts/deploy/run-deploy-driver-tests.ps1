# Runs the hermetic Pester suite for the prod deploy driver (audit F008) and
# exits non-zero on any failure. Kept in a file (not inline in Taskfile.yml /
# ci.yml) because go-task pipes commands through a POSIX shell that eats `$`.
# Requires Pester >= 5.5:
#   Install-Module Pester -MinimumVersion 5.5 -Scope CurrentUser -Force
#Requires -Version 7.0

$ErrorActionPreference = "Stop"

# CRLF preflight (hermetic). Git Bash on Windows tolerates CRLF in bash
# scripts, bash on Linux does not — and a CRLF harness cannot even self-report
# there. PowerShell parses regardless of the .sh files' endings, so this check
# gives an actionable diagnostic on BOTH platforms before anything executes.
$crlfOffenders = Get-ChildItem -Path $PSScriptRoot -Recurse -Filter *.sh |
    Where-Object { (Get-Content -LiteralPath $_.FullName -Raw) -match "`r" }
if ($crlfOffenders) {
    foreach ($f in $crlfOffenders) {
        Write-Host "CRLF line endings in $($f.FullName) — bash on Linux would fail. Normalize to LF (sed -i 's/\r`$//')." -ForegroundColor Red
    }
    exit 1
}

$pester = Get-Module -ListAvailable Pester | Where-Object { $_.Version -ge [version]"5.5" }
if (-not $pester) {
    if ($env:CI) {
        # CI runners bootstrap themselves; dev machines get an actionable error
        # instead of a silent CurrentUser install.
        Install-Module Pester -MinimumVersion 5.5 -Force -SkipPublisherCheck -Scope CurrentUser
    } else {
        Write-Error ("Pester >= 5.5 required. Install it with: " +
            "Install-Module Pester -MinimumVersion 5.5 -Scope CurrentUser -Force -SkipPublisherCheck")
        exit 1
    }
}

$suite = Join-Path $PSScriptRoot "deploy-prod.Tests.ps1"
$result = Invoke-Pester -Path $suite -PassThru
if ($result.FailedCount -gt 0 -or $result.PassedCount -eq 0) { exit 1 }
exit 0
