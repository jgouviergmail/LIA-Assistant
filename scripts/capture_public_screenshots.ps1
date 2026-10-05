# Capture the current Docker UI with handwritten demo fixtures, never account data.
# Review output/playwright/public-screenshots, then rerun with -Publish to copy it.
param(
    [string]$WebContainer = 'lia-web-dev',
    [ValidateRange(1024, 65535)][int]$Port = 3130,
    [ValidateSet('.next-e2e', '.next-e2e-simli-fix')]
    [string]$DistDirectory = '.next-e2e',
    [switch]$Publish,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = Join-Path $repo 'output/playwright/public-screenshots'
$browser = 'lia-public-screenshots-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$dist = $DistDirectory
$serverPid = $null

function Invoke-Docker {
    param([string[]]$DockerArgs)
    & docker @DockerArgs
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed ($LASTEXITCODE)." }
}

try {
    if (-not $Publish) {
        Invoke-Docker -DockerArgs @('exec', $WebContainer, 'node', '-e',
            "require('node:net').createServer().once('error',()=>process.exit(1)).listen($Port,()=>process.exit(0))")
        if (-not $SkipBuild) {
            Invoke-Docker -DockerArgs @('exec', '-w', '/monorepo/apps/web',
                '-e', 'NODE_ENV=production', '-e', 'NEXT_BUILD_CPUS=4',
                '-e', "NEXT_DIST_DIR=$dist", '-e', 'NEXT_TELEMETRY_DISABLED=1',
                '-e', 'NEXT_PUBLIC_API_URL=', '-e', 'NEXT_PUBLIC_PRODUCT_TELEMETRY=false',
                '-e', 'API_URL_SERVER=http://127.0.0.1:1', '-e', 'API_URL_SERVER_HTTP=http://127.0.0.1:1',
                '-e', 'NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE=0', $WebContainer, 'pnpm', 'build')
        }
        Invoke-Docker -DockerArgs @('exec', '-w', '/monorepo/apps/web', $WebContainer, 'sh', '-c',
            "cp -r $dist/static $dist/standalone/apps/web/$dist/; cp -r public $dist/standalone/apps/web/")
        Invoke-Docker -DockerArgs @('exec', '-d', '-w', "/monorepo/apps/web/$dist/standalone/apps/web",
            $WebContainer, 'sh', '-c',
            "PORT=$Port HOSTNAME=0.0.0.0 NODE_ENV=production API_URL_SERVER=http://127.0.0.1:1 API_URL_SERVER_HTTP=http://127.0.0.1:1 LANDING_MEDIA_BASE_URL= node server.js > /tmp/public-screenshots-$Port.log 2>&1 & echo `$! > /tmp/public-screenshots-$Port.pid; wait")
        $serverPid = (Invoke-Docker -DockerArgs @('exec', $WebContainer, 'cat',
            "/tmp/public-screenshots-$Port.pid")) | Select-Object -Last 1
        if ($serverPid -notmatch '^\d+$') { throw 'Missing isolated server PID.' }
    }
    Invoke-Docker -DockerArgs @('run', '--rm', '-d', '--name', $browser,
        '--network', "container:$WebContainer", '-v', "${repo}:/repo", '-w', '/capture',
        'mcr.microsoft.com/playwright:v1.63.0-noble', 'sleep', 'infinity')
    # Install in the disposable container; leave the repository's node_modules alone.
    Invoke-Docker -DockerArgs @('exec', $browser, 'sh', '-c',
        'cp /repo/apps/web/e2e/package*.json /capture/; cp -r /repo/apps/web/e2e/capture /repo/apps/web/e2e/fixtures /capture/; npm ci --no-audit --no-fund')
    if (-not $Publish) {
        Invoke-Docker -DockerArgs @('exec', $browser, 'node', '-e',
            "(async()=>{for(let i=0;i<50;i++){try{await fetch('http://127.0.0.1:$Port/en');return}catch{await new Promise(r=>setTimeout(r,200))}}process.exit(1)})()")
        Invoke-Docker -DockerArgs @('exec', $browser, 'node', '/capture/capture/run-public-screenshots.mjs',
            'capture', '/repo', '/capture/output', "http://127.0.0.1:$Port")
        New-Item -ItemType Directory -Force -Path $output | Out-Null
        Invoke-Docker -DockerArgs @('cp', "${browser}:/capture/output/.", $output)
        Write-Host "Review all PNGs in $output. Then run this script with -Publish."
    } else {
        if (-not (Test-Path (Join-Path $output 'capture-report.json'))) {
            throw 'Capture and visually review the images before publishing them.'
        }
        Invoke-Docker -DockerArgs @('cp', $output, "${browser}:/capture/output")
        Invoke-Docker -DockerArgs @('exec', $browser, 'node', '/capture/capture/run-public-screenshots.mjs',
            'publish', '/repo', '/capture/output')
    }
} finally {
    if ($serverPid -match '^\d+$') {
        & docker exec $WebContainer kill $serverPid | Out-Null
    }
    & docker stop $browser 2>$null | Out-Null
}
