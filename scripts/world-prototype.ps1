<#
.SYNOPSIS
Runs a source snapshot in an owned web container. Shared dependencies are read-only.
.EXAMPLE
powershell -File scripts/world-prototype.ps1 -Action Start
#>
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Sync', 'Status', 'Stop')][string]$Action = 'Status',
    [ValidateRange(1024, 65535)][int]$Port = 3002,
    [ValidateSet('127.0.0.1', '127.0.0.2', '127.0.0.3', '127.0.0.4', '127.0.0.5', '127.0.0.6', '127.0.0.7', '0.0.0.0')][string]$BindAddress = '127.0.0.1',
    [ValidateSet('Development', 'Production')][string]$Mode = 'Development',
    [string]$Container = 'lia-world-prototype-web',
    [string]$Image = 'lia-web-dev:latest',
    [string]$Network = 'lia_lia-network',
    [string]$ApiUrlServer = 'https://api:8000',
    [string]$AllowedDevOrigins = '',
    [switch]$ProofPreview,
    [switch]$ProofTranslationFixture,
    [string]$DependenciesVolume = 'lia_web_node_modules',
    [string]$CertificatesVolume = 'lia_ssl_certs'
)
$ErrorActionPreference = 'Stop'
$taskLabel = 'world-prototype'
$sourceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$developmentOrigins = (@($AllowedDevOrigins.Split(',') | Where-Object { $_.Trim() }) + @($BindAddress) | Select-Object -Unique) -join ','

function Invoke-Docker {
    param([string[]]$Arguments)
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed ($LASTEXITCODE): $($Arguments[0])" }
}
function Get-OwnedContainer {
    $names = & docker container ls -a --format '{{.Names}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker inventory failed.' }
    if ($names -notcontains $Container) { return $null }
    $metadata = & docker container inspect $Container
    if ($LASTEXITCODE -ne 0) { throw 'Container inspection failed.' }
    $record = ($metadata | ConvertFrom-Json)[0]
    if ($record.Config.Labels.'lia.task' -ne $taskLabel) {
        throw "Refusing to operate on container '$Container': ownership label differs."
    }
    return $record
}
function Sync-Source {
    $temporaryDirectory = Join-Path $sourceRoot '.tmp'
    New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
    $archive = Join-Path $temporaryDirectory "world-source-$PID.tar"
    try {
        # tar does not follow dependency junctions; exclude them explicitly too.
        & tar -cf $archive --exclude=node_modules --exclude=coverage --exclude=test-results --exclude=playwright-report --exclude=.tmp '--exclude=.next*' '--exclude=.env*' '--exclude=*.tsbuildinfo' -C $sourceRoot apps/web apps/api/src/domains/agents/expressivity apps/api/src/core/recurrence/spec.py
        if ($LASTEXITCODE -ne 0) { throw 'Source archive failed.' }
        Invoke-Docker -Arguments @('cp', $archive, "${Container}:/tmp/world-source.tar")
        Invoke-Docker -Arguments @('exec', $Container, 'sh', '-lc', 'mkdir -p /monorepo && tar -xf /tmp/world-source.tar -C /monorepo && rm /tmp/world-source.tar')
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
    }
}

$owned = Get-OwnedContainer
if ($Action -eq 'Stop') {
    if ($owned) { Invoke-Docker -Arguments @('rm', '-f', $Container) }
    return
}
if ($Action -eq 'Status') {
    if (!$owned) { Write-Output 'Prototype container is absent.'; return }
    $actualPort = $owned.NetworkSettings.Ports.'3000/tcp'[0].HostPort
    $previewHost = $owned.NetworkSettings.Ports.'3000/tcp'[0].HostIp
    if ($previewHost -eq '0.0.0.0') { $previewHost = 'localhost' }
    $route = if ($owned.Config.Labels.'lia.world.mode' -eq 'Production') { 'dashboard/world' } else { 'world-preview' }
    Write-Output "Prototype: $($owned.State.Status). Preview: http://${previewHost}:$actualPort/fr/$route"
    return
}
if ($Action -eq 'Sync') {
    if (!$owned -or !$owned.State.Running) { throw 'Start the prototype container before syncing.' }
    if ($owned.Config.Labels.'lia.world.mode' -eq 'Production') { throw 'Production snapshots require an explicit rebuild; do not sync a running build.' }
    Sync-Source
    Write-Output 'Source snapshot synchronized. Next development reloads changed files.'
    return
}
if ($owned) {
    if (!$owned.State.Running) { Invoke-Docker -Arguments @('start', $Container) }
    Write-Output 'Container already exists. Use Sync to update its source, or Stop then Start to recreate it.'
    return
}
# Existing image/volume/network are required; this script installs no dependency.
Invoke-Docker -Arguments @('image', 'inspect', $Image, '--format', '{{.Id}}')
Invoke-Docker -Arguments @('volume', 'inspect', $DependenciesVolume, '--format', '{{.Name}}')
Invoke-Docker -Arguments @('volume', 'inspect', $CertificatesVolume, '--format', '{{.Name}}')
Invoke-Docker -Arguments @('network', 'inspect', $Network, '--format', '{{.Name}}')
Invoke-Docker -Arguments @('run', '-d', '--name', $Container, '--label', "lia.task=$taskLabel", '--label', "lia.world.mode=$Mode", '--network', $Network,
    '-p', "${BindAddress}:${Port}:3000", '--mount', "type=volume,src=$DependenciesVolume,dst=/monorepo/apps/web/node_modules,readonly",
    '--mount', "type=volume,src=$CertificatesVolume,dst=/certs,readonly",
    '--entrypoint', 'sh', $Image, '-c', 'sleep infinity')
Sync-Source
$nodeEnvironment = if ($Mode -eq 'Production') { 'production' } else { 'development' }
$runScript = if ($Mode -eq 'Production') {
    'node scripts/copy-ort-runtime.mjs && node node_modules/next/dist/bin/next build --webpack && mkdir -p .next-world/standalone/apps/web/public .next-world/standalone/apps/web/.next-world/static && cp -a public/. .next-world/standalone/apps/web/public/ && cp -a .next-world/static/. .next-world/standalone/apps/web/.next-world/static/ && HOSTNAME=0.0.0.0 PORT=3000 NODE_OPTIONS=--max-old-space-size=320 exec node .next-world/standalone/apps/web/server.js'
} else {
    'exec node node_modules/next/dist/bin/next dev --webpack --hostname 0.0.0.0 --port 3000'
}
Invoke-Docker -Arguments @('exec', '-d', '-w', '/monorepo/apps/web', '-e', 'NEXT_DIST_DIR=.next-world',
    '-e', "NODE_ENV=$nodeEnvironment",
    '-e', 'NEXT_PUBLIC_API_URL=', '-e', "API_URL_SERVER=$ApiUrlServer", '-e', "NEXT_PUBLIC_ALLOWED_DEV_ORIGINS=$developmentOrigins", '-e', "WORLD_PROOF_PREVIEW=$($ProofPreview.IsPresent.ToString().ToLowerInvariant())", '-e', "WORLD_PROOF_TRANSLATION_FIXTURE=$($ProofTranslationFixture.IsPresent.ToString().ToLowerInvariant())", '-e', 'NODE_EXTRA_CA_CERTS=/certs/cert.pem', $Container,
    'sh', '-lc', "{ $runScript; } >/tmp/world-next.log 2>&1")
$previewHost = if ($BindAddress -eq '0.0.0.0') { 'localhost' } else { $BindAddress }
$route = if ($Mode -eq 'Production') { 'dashboard/world' } else { 'world-preview' }
Write-Output "Preview: http://${previewHost}:$Port/fr/$route (first compilation/build may take a moment)."
