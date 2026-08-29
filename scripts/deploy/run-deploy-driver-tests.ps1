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

# Decouverte par REPERTOIRE, pas par fichier nomme. Pointer un seul fichier
# faisait qu'un nouveau `*.Tests.ps1` -- y compris sous lib/ -- n'etait jamais
# execute : il aurait suffi d'en ajouter un pour croire la surface couverte
# alors que rien ne tournait. C'est la classe "jamais cable" que ce depot a
# deja rencontree sur les sections de FAQ et les cartes de guides.
#
# `PassedCount -eq 0` ci-dessous reste la garde qui attrape une decouverte
# vide (repertoire deplace, filtre casse) : zero test passe est un echec, pas
# un succes silencieux.
$result = Invoke-Pester -Path $PSScriptRoot -PassThru
if ($result.FailedCount -gt 0 -or $result.PassedCount -eq 0) { exit 1 }
exit 0
