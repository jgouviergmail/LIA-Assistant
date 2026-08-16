# ============================================================================
# Hermetic Pester (v5) tests for the prod deploy driver (audit F008).
#
# Proves the WHOLE deploy system — driver (deploy-prod.ps1), bundle builder
# (prepare-prod.ps1), generated deploy.sh and the shipped readiness-gate
# library — as ONE wired system, without ever contacting a network, Docker or
# production:
#
#   - every external tool (ssh/scp/rsync/sops, and docker/curl for the bash
#     side) is a PATH shim that logs its invocation to a file;
#   - the driver runs against a throwaway sandbox project in $TestDrive (its
#     own git repo, so provenance SHAs are real and deterministic);
#   - the sandbox copies NEVER load the developer's deploy.local.ps1 overrides
#     (running the repo script directly would — that file rewrites $SshHost
#     AFTER param binding);
#   - the generated PROD/deploy.sh is then executed under bash with docker/curl
#     shims to prove the readiness-gate wiring end-to-end (green, red→rollback,
#     rollback failure), including the provenance identity landing in the
#     release manifest.
#
# Platform coverage (audit: "Windows, pwsh Unix"): the same suite runs on
# Windows dev machines (Invoke-WithRetry `cmd /c` branch) and on the Linux CI
# runner (`sh -c` branch). Requires Pester >= 5:
#   Install-Module Pester -MinimumVersion 5.5 -Scope CurrentUser -Force
# Run:  pwsh -Command "Invoke-Pester -Path scripts/deploy -Output Detailed"
# ============================================================================
#Requires -Version 7.0

BeforeAll {
    $script:RepoDeployDir = $PSScriptRoot

    # --- bash discovery (wiring tests) --------------------------------------
    # On Windows, prefer Git Bash explicitly (cygpath available); `bash` from
    # PATH may resolve to WSL, whose /mnt/... path mapping differs.
    $script:BashExe = $null
    if ($IsWindows) {
        foreach ($candidate in @(
                (Join-Path $env:ProgramFiles "Git\bin\bash.exe"),
                (Join-Path $env:ProgramFiles "Git\usr\bin\bash.exe"))) {
            if (Test-Path $candidate) { $script:BashExe = $candidate; break }
        }
    } else {
        $script:BashExe = "bash"
    }

    function ConvertTo-BashPath([string]$Path) {
        if (-not $IsWindows) { return $Path }
        $fwd = $Path -replace '\\', '/'
        (& $script:BashExe -c "cygpath -u '$fwd'").Trim()
    }

    # --- sandbox project ------------------------------------------------------
    function New-DeploySandbox([string]$Root) {
        $proj = Join-Path $Root "proj"
        New-Item -ItemType Directory -Path (Join-Path $proj "scripts/deploy/lib") -Force | Out-Null
        Copy-Item (Join-Path $RepoDeployDir "deploy-prod.ps1") (Join-Path $proj "scripts/deploy/")
        Copy-Item (Join-Path $RepoDeployDir "prepare-prod.ps1") (Join-Path $proj "scripts/deploy/")
        Copy-Item (Join-Path $RepoDeployDir "lib/deploy_readiness_gate.sh") (Join-Path $proj "scripts/deploy/lib/")
        # NOTE: deploy.local.ps1 deliberately NOT copied — hermetic defaults.

        Set-Content (Join-Path $proj "package.json") '{"version": "9.9.9-test"}'
        Set-Content (Join-Path $proj "docker-compose.prod.yml") "services: {}"
        Set-Content (Join-Path $proj "docker-compose.skill-sandbox.yml") "services: {}"
        Set-Content (Join-Path $proj "docker-compose.devops.yml") "services: {}"
        # The demonstrator's envelope and the three shell scripts the deployment
        # ships for it. `prepare-prod.ps1` marks all four REQUIRED and aborts
        # without them, so a sandbox lacking them is not a deployable tree —
        # exactly the fiction this fixture exists to avoid. Missed on
        # 2026-08-07: they became required and this suite went red unnoticed,
        # because a deployment-path change shipped without `task test:deploy`.
        Set-Content (Join-Path $proj "docker-compose.demo-instance.yml") "services: {}"
        foreach ($demoScript in @(
                "harden-demo-host.sh", "verify-demo-surface.sh", "preflight-demo-prod.sh")) {
            Copy-Item (Join-Path $RepoDeployDir $demoScript) (Join-Path $proj "scripts/deploy/")
        }
        New-Item -ItemType Directory (Join-Path $proj "infrastructure/demo-instance") -Force | Out-Null
        Set-Content (Join-Path $proj "infrastructure/demo-instance/Caddyfile") ":80 { respond 404 }"
        # Filled with the four keys the pipeline refuses to ship without, and a
        # non-localhost URL: an incomplete file makes the step decline, and a
        # step that declines measures nothing.
        Set-Content (Join-Path $proj ".env.demo-instance.prod") @"
FRONTEND_URL=https://demo.example.org
APP_URL_SERVER=https://demo.example.org
DEMO_INSTANCE_TUNNEL_TOKEN=fake-token
DEEPSEEK_API_KEY=fake-key
SECRET_KEY=fake-secret
FERNET_KEY=fake-fernet
"@
        Set-Content (Join-Path $proj ".sops.yaml") "creation_rules: []"
        # The pnpm workspace files and the patch directory: prepare-prod refuses
        # to produce a bundle without them, because the web image's build CONTEXT
        # is the PROD folder itself and `COPY patches ./patches` fails on the
        # production host otherwise (v1.25.24). A sandbox missing them is not a
        # deployable tree, so it must not stand in for one.
        Set-Content (Join-Path $proj ".npmrc") "node-linker=isolated"
        Set-Content (Join-Path $proj "pnpm-workspace.yaml") "packages:`n  - apps/*"
        Set-Content (Join-Path $proj "pnpm-lock.yaml") "lockfileVersion: '9.0'"
        New-Item -ItemType Directory (Join-Path $proj "patches") -Force | Out-Null
        Set-Content (Join-Path $proj "patches/fake@1.0.0.patch") "diff --git a/x b/x"
        Set-Content (Join-Path $proj ".env.prod") "POSTGRES_BACKUP_HOST_DIR=./backups/postgres`nSENTINEL_ENV=1"
        New-Item -ItemType Directory (Join-Path $proj "keys") -Force | Out-Null
        Set-Content (Join-Path $proj "keys/age-key-prod.txt") "AGE-SECRET-KEY-FAKE-PROD"
        Set-Content (Join-Path $proj "keys/age-key-dev.txt") "AGE-SECRET-KEY-FAKE-DEV"
        New-Item -ItemType Directory (Join-Path $proj "apps/api/src") -Force | Out-Null
        Set-Content (Join-Path $proj "apps/api/src/main.py") "# API_SENTINEL"
        Set-Content (Join-Path $proj "apps/api/Dockerfile.prod") "FROM scratch"
        Set-Content (Join-Path $proj "apps/api/docker-entrypoint.sh") "#!/bin/sh"
        Set-Content (Join-Path $proj "apps/api/requirements.txt") "fastapi"
        # Compiled gettext catalogues. The fixture must satisfy every
        # precondition prepare-prod.ps1 enforces, or the bundle is never
        # generated and the whole suite fails on a missing deploy.sh instead of
        # on the behaviour under test.
        New-Item -ItemType Directory (Join-Path $proj "apps/api/locales/fr/LC_MESSAGES") -Force | Out-Null
        Set-Content (Join-Path $proj "apps/api/locales/fr/LC_MESSAGES/messages.mo") "LOCALE_SENTINEL"
        New-Item -ItemType Directory (Join-Path $proj "apps/web/src") -Force | Out-Null
        Set-Content (Join-Path $proj "apps/web/src/page.tsx") "// WEB_SENTINEL"
        Set-Content (Join-Path $proj "apps/web/Dockerfile.prod") "FROM scratch"
        Set-Content (Join-Path $proj "apps/web/package.json") '{"version": "9.9.9-test"}'

        # Real git repo → prepare-prod's `git rev-parse HEAD` yields a
        # deterministic, assertable provenance SHA. autocrlf off: silence
        # LF/CRLF warnings on the sandbox files.
        & git -C $proj init -q
        & git -C $proj config core.autocrlf false
        & git -C $proj add -A 2>$null
        & git -C $proj -c user.email=t@test -c user.name=t commit -qm "sandbox" | Out-Null
        $proj
    }

    function Get-SandboxSha([string]$Proj) { (& git -C $Proj rev-parse HEAD).Trim() }

    # --- PATH shims -----------------------------------------------------------
    # Each tool gets a Windows .bat AND a POSIX sh shim; both append their
    # invocation to $env:SHIM_LOG. ssh is scriptable via SSH_MODE:
    #   ok (default) | fail_twice (RETRY_COUNTER) | always_fail | fail_deploy
    #   | bad_perms (SEC-013: hardening reports modes that were NOT applied)
    #
    # The shim answers the permission-hardening step with the `stat` readback
    # the driver parses. `bad_perms` returns the modes an unreported chmod
    # failure would leave behind — world-readable secrets — which is what the
    # driver must now refuse to deploy on.
    function New-ShimSet([string]$Root) {
        $bin = Join-Path $Root "bin"
        New-Item -ItemType Directory $bin -Force | Out-Null

        # NOTE: no EnableDelayedExpansion here — it eats `!` characters from the
        # logged command line (the cleanup step's `.[!.]*` glob), truncating the
        # shim log. goto-based flow avoids parenthesized blocks entirely.
        $sshBat = @'
@echo off
echo ssh %* >> "%SHIM_LOG%"
if "%SSH_MODE%"=="always_fail" exit /b 9
if "%SSH_MODE%"=="fail_deploy" goto :faildeploy
if "%SSH_MODE%"=="fail_twice" goto :failtwice
goto :ok
:faildeploy
echo %* | findstr /C:"deploy.sh" >nul && exit /b 5
goto :ok
:failtwice
set N=0
if exist "%RETRY_COUNTER%" set /p N=<"%RETRY_COUNTER%"
set /a N=N+1
(echo %N%)>"%RETRY_COUNTER%"
if %N% LSS 3 exit /b 7
:ok
echo BACKUP_CREATED
if "%SSH_MODE%"=="bad_perms" goto :badperms
echo PERMS_ENV=600
echo PERMS_DIR=700
echo PERMS_DEMO=600
exit /b 0
:badperms
echo PERMS_ENV=644
echo PERMS_DIR=755
echo PERMS_DEMO=600
exit /b 0
'@
        $sshSh = @'
#!/bin/sh
echo "ssh $@" >> "$SHIM_LOG"
[ "$SSH_MODE" = "always_fail" ] && exit 9
if [ "$SSH_MODE" = "fail_deploy" ]; then
  case "$*" in *deploy.sh*) exit 5 ;; esac
fi
if [ "$SSH_MODE" = "fail_twice" ]; then
  N=0; [ -f "$RETRY_COUNTER" ] && N=$(cat "$RETRY_COUNTER")
  N=$((N+1)); echo $N > "$RETRY_COUNTER"
  [ $N -lt 3 ] && exit 7
fi
echo BACKUP_CREATED
if [ "$SSH_MODE" = "bad_perms" ]; then
  echo PERMS_ENV=644
  echo PERMS_DIR=755
else
  echo PERMS_ENV=600
  echo PERMS_DIR=700
fi
echo PERMS_DEMO=600
exit 0
'@
        $logOnlyBat = @'
@echo off
echo {TOOL} %* >> "%SHIM_LOG%"
exit /b 0
'@
        $logOnlySh = @'
#!/bin/sh
echo "{TOOL} $@" >> "$SHIM_LOG"
exit 0
'@
        $sopsBat = @'
@echo off
echo sops %* >> "%SHIM_LOG%"
echo FAKE=encrypted_by_shim
exit /b 0
'@
        $sopsSh = @'
#!/bin/sh
echo "sops $@" >> "$SHIM_LOG"
echo FAKE=encrypted_by_shim
exit 0
'@
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText((Join-Path $bin "ssh.bat"), $sshBat, $utf8)
        [IO.File]::WriteAllText((Join-Path $bin "ssh"), ($sshSh -replace "`r`n", "`n"), $utf8)
        foreach ($tool in "scp", "rsync") {
            [IO.File]::WriteAllText((Join-Path $bin "$tool.bat"), ($logOnlyBat -replace '\{TOOL\}', $tool), $utf8)
            [IO.File]::WriteAllText((Join-Path $bin $tool), (($logOnlySh -replace '\{TOOL\}', $tool) -replace "`r`n", "`n"), $utf8)
        }
        [IO.File]::WriteAllText((Join-Path $bin "sops.bat"), $sopsBat, $utf8)
        [IO.File]::WriteAllText((Join-Path $bin "sops"), ($sopsSh -replace "`r`n", "`n"), $utf8)
        if (-not $IsWindows) { & chmod +x (Join-Path $bin "ssh") (Join-Path $bin "scp") (Join-Path $bin "rsync") (Join-Path $bin "sops") }
        $bin
    }

    # docker/curl/sudo sh shims for executing the GENERATED deploy.sh under
    # bash. docker is scripted via HAS_ROLLBACK; curl via CURL_MODE
    # (green | red | red_then_green + CURL_FAILS/CURL_COUNTER).
    function New-BashShimSet([string]$Root) {
        $bin = Join-Path $Root "bash-bin"
        New-Item -ItemType Directory $bin -Force | Out-Null
        $docker = @'
#!/bin/sh
echo "docker $*" >> "$SHIM_LOG"
if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then
  case "$*" in
    *--format*) echo "sha256:fakeimageid"; exit 0 ;;
    *__rollback*) [ "$HAS_ROLLBACK" = "1" ] && exit 0 || exit 1 ;;
    *) exit 0 ;;
  esac
fi
exit 0
'@
        $curl = @'
#!/bin/sh
echo "curl $*" >> "$SHIM_LOG"
case "$CURL_MODE" in
  green) exit 0 ;;
  red) exit 1 ;;
  red_then_green)
    N=0; [ -f "$CURL_COUNTER" ] && N=$(cat "$CURL_COUNTER")
    N=$((N+1)); echo $N > "$CURL_COUNTER"
    [ $N -le "${CURL_FAILS:-2}" ] && exit 1
    exit 0 ;;
esac
exit 0
'@
        $sudo = @'
#!/bin/sh
echo "sudo $*" >> "$SHIM_LOG"
exit 0
'@
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText((Join-Path $bin "docker"), ($docker -replace "`r`n", "`n"), $utf8)
        [IO.File]::WriteAllText((Join-Path $bin "curl"), ($curl -replace "`r`n", "`n"), $utf8)
        [IO.File]::WriteAllText((Join-Path $bin "sudo"), ($sudo -replace "`r`n", "`n"), $utf8)
        if (-not $IsWindows) { & chmod +x (Join-Path $bin "docker") (Join-Path $bin "curl") (Join-Path $bin "sudo") }
        $bin
    }

    # --- driver invocation (child pwsh: the script calls `exit`) --------------
    function Invoke-DeployProd {
        param(
            [string]$Proj,
            [string]$ShimBin,
            [string[]]$Arguments = @(),
            [hashtable]$EnvOverrides = @{}
        )
        $scriptPath = Join-Path $Proj "scripts/deploy/deploy-prod.ps1"
        $saved = @{}
        foreach ($k in @("PATH", "USERPROFILE", "HOME", "SHIM_LOG", "SSH_MODE", "RETRY_COUNTER")) {
            $saved[$k] = [Environment]::GetEnvironmentVariable($k)
        }
        try {
            if ($ShimBin) {
                $env:PATH = "$ShimBin$([IO.Path]::PathSeparator)$($env:PATH)"
            }
            # Hermetic home: step 8 must never see the developer's real
            # ~/.claude/.credentials.json.
            $env:USERPROFILE = $Proj
            $env:HOME = $Proj
            foreach ($k in $EnvOverrides.Keys) {
                [Environment]::SetEnvironmentVariable($k, $EnvOverrides[$k])
            }
            Push-Location $Proj
            $output = & pwsh -NoProfile -File $scriptPath @Arguments 2>&1 | Out-String
            [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $output }
        } finally {
            Pop-Location
            foreach ($k in $saved.Keys) {
                [Environment]::SetEnvironmentVariable($k, $saved[$k])
            }
            foreach ($k in $EnvOverrides.Keys) {
                if (-not $saved.ContainsKey($k)) {
                    [Environment]::SetEnvironmentVariable($k, $null)
                }
            }
        }
    }

    function Test-HasCrlf([string]$File) {
        ([IO.File]::ReadAllBytes($File) -contains [byte]13)
    }
}

# ============================================================================
# Parameter validation — the driver refuses unsafe inputs before doing anything
# ============================================================================
Describe "deploy-prod.ps1 parameter validation" {
    BeforeAll {
        $proj = New-DeploySandbox $TestDrive
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-validation.log"
    }

    It "rejects an empty SshHost (exit 1)" {
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-SshHost", "", "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $log }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SshHost"
    }

    It "rejects an out-of-range SshPort (exit 1)" {
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-SshPort", "0", "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $log }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SshPort invalide"
    }

    It "rejects an SshUser containing shell metacharacters (exit 1)" {
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-SshUser", "evil;user", "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $log }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SshUser invalide"
    }

    It "rejects an SshHost containing shell metacharacters (exit 1)" {
        # $sshTarget is "$SshUser@$SshHost" and lands in the same `cmd /c`
        # string as the username, which WAS checked — the host was not.
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-SshHost", "1.2.3.4;id", "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $log }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "SshHost invalide"
    }

    # ------------------------------------------------------------------------
    # SEC-038 — RemoteDir feeds `sudo rm -rf ~/$RemoteDir/*`. Each value below
    # is destructive on a real host, and NONE of them needs a shell
    # metacharacter to be so; the previous denylist accepted all but the last
    # two. The assertion on the exit code alone would be satisfied by a check
    # placed anywhere in the script, so every case also proves the shim log
    # stayed empty: the driver died before reaching the backup step, which is
    # the first place the value was interpolated.
    # ------------------------------------------------------------------------
    It "rejects the RemoteDir value <Why> (exit 1, no ssh invoked)" -ForEach @(
        @{ Value = ".."; Why = "'..' (would expand to `sudo rm -rf ~/../*` — every home dir)" }
        @{ Value = "."; Why = "'.' (would expand to `sudo rm -rf ~/./*` — the whole home dir)" }
        @{ Value = "lia foo"; Why = "'lia foo' (a space yields two rm targets)" }
        @{ Value = "lia;rm -rf /"; Why = "'lia;rm -rf /' (command separator)" }
        @{ Value = "/"; Why = "'/' (filesystem root)" }
        @{ Value = "~"; Why = "'~' (home shorthand)" }
        @{ Value = ""; Why = "the empty string (would expand to `sudo rm -rf ~//*`)" }
        @{ Value = "lia/prod"; Why = "'lia/prod' (more than one path segment)" }
        @{ Value = "../../etc"; Why = "'../../etc' (traversal above the home dir)" }
        @{ Value = "-rf"; Why = "'-rf' (a leading dash is read as an option by rm/cp)" }
        @{ Value = ".ssh"; Why = "'.ssh' (a dotfile directory holding the host's own keys)" }
        @{ Value = "lia`$(whoami)"; Why = "a command substitution" }
        @{ Value = "lia`nid"; Why = "an embedded newline (terminates the remote command)" }
    ) {
        $caseLog = Join-Path $TestDrive "shim-remotedir-$([Guid]::NewGuid().ToString('N')).log"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-RemoteDir", $Value, "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $caseLog }
        $r.ExitCode | Should -Be 1 -Because "'$Value' must never reach a remote command"
        $r.Output | Should -Match "RemoteDir invalide"
        (Test-Path $caseLog) | Should -BeFalse -Because "validation must precede the first interpolation"
    }

    It "rejects a RemoteDir ending in a newline (`\z` anchor, not `$`)" {
        # .NET's `$` ALSO matches immediately before a trailing newline, so an
        # `^...$` anchor would accept "lia`n" — which closes the remote command
        # line early. This case is what forces \A..\z. Guarded rather than
        # merged into the table above: if the value cannot survive the process
        # boundary intact the test says so instead of passing vacuously.
        $value = "lia`n"
        $caseLog = Join-Path $TestDrive "shim-remotedir-newline.log"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-RemoteDir", $value, "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $caseLog }
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "RemoteDir invalide"
        (Test-Path $caseLog) | Should -BeFalse
    }

    It "still accepts a legitimate RemoteDir (no false rejection)" {
        # The counterpart every allowlist owes: proof it did not simply become
        # a wall. Letters, digits, dash, underscore and an inner dot all pass.
        $caseLog = Join-Path $TestDrive "shim-remotedir-ok.log"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-RemoteDir", "lia-prod_2.v3", "-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $caseLog }
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "RemoteDir invalide"
        $r.Output | Should -Match "lia-prod_2\.v3"
    }

    It "keeps the default RemoteDir valid (the shipped value)" {
        $caseLog = Join-Path $TestDrive "shim-remotedir-default.log"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $caseLog }
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Not -Match "RemoteDir invalide"
    }
}

# ============================================================================
# DryRun — a simulation must not mutate ANYTHING, locally or remotely
# ============================================================================
Describe "deploy-prod.ps1 -DryRun" {
    BeforeAll {
        $proj = New-DeploySandbox $TestDrive
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-dryrun.log"
        # Pre-created PROD with sensitive content: DryRun must leave it intact.
        New-Item -ItemType Directory (Join-Path $proj "PROD/keys") -Force | Out-Null
        Set-Content (Join-Path $proj "PROD/keys/sentinel.txt") "MUST_SURVIVE"
        Set-Content (Join-Path $proj "PROD/.env.prod") "MUST_SURVIVE=1"
        $script:r = Invoke-DeployProd -Proj $proj -ShimBin $bin -Arguments @("-DryRun") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "ok" }
    }

    It "exits 0 and announces the simulation for every step" {
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "DRY RUN"
        $r.Output | Should -Match "\[DRY RUN\] sops --encrypt"
        $r.Output | Should -Match "\[DRY RUN\] ssh"
    }

    It "never invokes ssh/scp/rsync/sops (shim log stays empty)" {
        (Test-Path $log) | Should -BeFalse
    }

    It "leaves the pre-existing PROD dir (including keys) untouched" {
        (Join-Path $proj "PROD/keys/sentinel.txt") | Should -Exist
        (Join-Path $proj "PROD/.env.prod") | Should -Exist
    }

    It "creates no encrypted files" {
        (Join-Path $proj ".env.prod.encrypted") | Should -Not -Exist
        (Join-Path $proj ".env.encrypted") | Should -Not -Exist
    }
}

# ============================================================================
# Hermetic real run, stopped at the remote-deploy step — the local bundle and
# the ssh/scp/rsync sequence are then inspectable (PROD not yet deleted)
# ============================================================================
Describe "deploy-prod.ps1 bundle + transfer sequence (hermetic, deploy step fails)" {
    BeforeAll {
        $proj = New-DeploySandbox $TestDrive
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-bundle.log"
        $script:sha = Get-SandboxSha $proj
        # SSH_MODE=fail_deploy: every remote op succeeds EXCEPT the final
        # `./deploy.sh` execution → the driver exits 1 at step 9 and the local
        # PROD bundle survives for inspection.
        $script:r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0", "-MaxRetries", "1") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "fail_deploy" }
        $script:prod = Join-Path $proj "PROD"
        $script:shimLog = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
    }

    It "fails at the remote deploy step (proof the exit code propagates)" {
        $r.ExitCode | Should -Not -Be 0
        $r.Output | Should -Match "Echec du deploiement"
    }

    It "actually copied the code bundle (API + web sentinels present)" {
        (Join-Path $prod "apps/api/src/main.py") | Should -Exist
        (Join-Path $prod "apps/web/src/page.tsx") | Should -Exist
        (Join-Path $prod "apps/api/Dockerfile.prod") | Should -Exist
        (Join-Path $prod "docker-compose.prod.yml") | Should -Exist
    }

    It "generated deploy.sh with the readiness-gate wiring in the right order" {
        $deploySh = Get-Content (Join-Path $prod "deploy.sh") -Raw
        $deploySh | Should -Match '\[ -f "provenance\.env" \] && \. \./provenance\.env'
        $deploySh | Should -Match '\[ -f "deploy_readiness_gate\.sh" \] && \. \./deploy_readiness_gate\.sh'
        $iCapture = $deploySh.IndexOf("capture_rollback_point")
        $iBuild = $deploySh.IndexOf("docker compose -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml -f docker-compose.devops.yml build")
        $iUp = $deploySh.IndexOf("up -d --force-recreate --wait")
        $iGate = $deploySh.IndexOf("run_readiness_gate")
        $iCapture | Should -BeGreaterThan 0
        $iBuild | Should -BeGreaterThan $iCapture
        $iUp | Should -BeGreaterThan $iBuild
        $iGate | Should -BeGreaterThan $iUp
    }

    It "kept the heredoc literal (bash dollar-constructs not expanded by PowerShell)" {
        $deploySh = Get-Content (Join-Path $prod "deploy.sh") -Raw
        $deploySh | Should -Match ([regex]::Escape('BACKUP_DIR=$(grep -E '))
        $deploySh | Should -Match ([regex]::Escape('${LOGWATCH_MAILTO}'))
    }

    It "shipped LF-only bash artifacts (deploy.sh, gate lib, provenance.env)" {
        Test-HasCrlf (Join-Path $prod "deploy.sh") | Should -BeFalse
        Test-HasCrlf (Join-Path $prod "deploy_readiness_gate.sh") | Should -BeFalse
        Test-HasCrlf (Join-Path $prod "provenance.env") | Should -BeFalse
    }

    It "recorded the sandbox commit SHA and version in provenance.env" {
        $prov = Get-Content (Join-Path $prod "provenance.env") -Raw
        $prov | Should -Match "GIT_COMMIT_SHA=$sha"
        $prov | Should -Match "APP_VERSION=9.9.9-test"
    }

    It "scrubbed the sensitive files from the bundle (keys, .sops.yaml)" {
        (Join-Path $prod "keys") | Should -Not -Exist
        (Join-Path $prod ".sops.yaml") | Should -Not -Exist
    }

    It "renamed .env.prod to .env inside the bundle" {
        (Join-Path $prod ".env") | Should -Exist
        (Join-Path $prod ".env.prod") | Should -Not -Exist
    }

    It "drove the remote sequence: backup, cleanup, transfer, then deploy" {
        $shimLog | Should -Match "lia-backups"
        $shimLog | Should -Match "sudo rm -rf"
        $shimLog | Should -Match "rsync .*-avz.*--partial"
        $shimLog | Should -Match ([regex]::Escape("chmod +x deploy.sh && ./deploy.sh"))
    }

    It "hardens the remote secret permissions before deploy (SEC-013)" {
        # Step 8.5 chmods the finalized .env to 0600 inside a 0700 dir over ssh,
        # AFTER the DOCKER_GID write (step 8) and BEFORE ./deploy.sh (step 9).
        $shimLog | Should -Match ([regex]::Escape("chmod 600"))
        $shimLog | Should -Match "\.env"
        $iHarden = $shimLog.IndexOf("stat -c")
        $iDeploy = $shimLog.IndexOf("chmod +x deploy.sh")
        $iHarden | Should -BeGreaterThan 0
        $iDeploy | Should -BeGreaterThan $iHarden
    }

    It "verifies the modes it obtained instead of announcing success (SEC-013)" {
        # The step used to end in a bare `echo PERMS_HARDENED`, which runs
        # whether or not a single chmod succeeded — the driver matched that
        # string and reported success, so the control could not fail. It must
        # now read the modes back.
        $shimLog | Should -Match ([regex]::Escape("stat -c"))
        $r.Output | Should -Match "Permissions secrets durcies et verifiees"
    }

    It "writes DOCKER_GID into the STAGING .env — the file the swap promotes" {
        # Step 8 used to append DOCKER_GID to the retired live .env
        # (~/lia/.env); the ADR-215 staging swap then promoted a fresh .env
        # WITHOUT it, so `group_add` fell back to 999, the API container lost
        # the Docker socket and every container-sandboxed skill script died
        # with EACCES (prod 2026-08-08 → 2026-08-15, skill widgets KO).
        $shimLog | Should -Match ([regex]::Escape("DOCKER_GID ~/lia.staging/.env"))
        $shimLog | Should -Not -Match ([regex]::Escape("DOCKER_GID ~/lia/.env"))
    }
}

# ============================================================================
# SEC-013 — a hardening that did not take must stop the deployment
# ============================================================================
Describe "deploy-prod.ps1 refuses to deploy on unhardened secrets (SEC-013)" {
    BeforeAll {
        $proj = New-DeploySandbox (Join-Path $TestDrive "badperms")
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-badperms.log"
        # Every remote op succeeds, but the permission readback reports the
        # modes an unnoticed chmod failure leaves behind: a world-readable .env.
        $script:r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0", "-MaxRetries", "1") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "bad_perms" }
        $script:shimLog = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
    }

    It "exits non-zero and names both offending modes" {
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "Durcissement des permissions ECHOUE"
        $r.Output | Should -Match "644"
        $r.Output | Should -Match "755"
    }

    It "never reaches docker compose — the platform does not start on leaked secrets" {
        # The assertion that matters: the .env holds every application secret,
        # so starting the stack anyway would knowingly run production with them
        # readable by any user on the host.
        $shimLog | Should -Not -Match ([regex]::Escape("chmod +x deploy.sh"))
    }
}

# ============================================================================
# Happy path end-to-end + step-8 home portability (pwsh/Unix)
# ============================================================================
Describe "deploy-prod.ps1 full happy path (hermetic)" {
    BeforeAll {
        $proj = New-DeploySandbox $TestDrive
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-happy.log"
        $script:proj = $proj
        $script:r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "ok" }
    }

    It "exits 0 and reports success" {
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "DEPLOIEMENT TERMINE AVEC SUCCES"
    }

    It "removes the local PROD bundle after a successful deploy" {
        (Join-Path $proj "PROD") | Should -Not -Exist
    }

    It "survives an unset USERPROFILE (pwsh/Unix home fallback, step 8)" {
        # Simulates the Linux pwsh environment where USERPROFILE does not
        # exist: the driver must fall back to HOME instead of crashing on
        # Join-Path with an empty path.
        $proj2 = New-DeploySandbox (Join-Path $TestDrive "nohome")
        $log2 = Join-Path $TestDrive "shim-nohome.log"
        $saved = $env:USERPROFILE
        try {
            $r2 = Invoke-DeployProd -Proj $proj2 -ShimBin $bin `
                -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0") `
                -EnvOverrides @{ SHIM_LOG = $log2; SSH_MODE = "ok"; USERPROFILE = "" }
            $r2.ExitCode | Should -Be 0
        } finally {
            $env:USERPROFILE = $saved
        }
    }
}

# ============================================================================
# Retry with exponential backoff
# ============================================================================
Describe "deploy-prod.ps1 retry behavior" {
    BeforeAll {
        $bin = New-ShimSet $TestDrive
    }

    It "retries a transient ssh failure and succeeds on the 3rd attempt" {
        $proj = New-DeploySandbox (Join-Path $TestDrive "retry-ok")
        $log = Join-Path $TestDrive "shim-retry.log"
        $counter = Join-Path $TestDrive "retry-counter.txt"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0", "-MaxRetries", "3") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "fail_twice"; RETRY_COUNTER = $counter }
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "Tentative 3/3"
    }

    It "gives up after MaxRetries and exits non-zero" {
        $proj = New-DeploySandbox (Join-Path $TestDrive "retry-fail")
        $log = Join-Path $TestDrive "shim-retry-fail.log"
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0", "-MaxRetries", "2") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "always_fail" }
        $r.ExitCode | Should -Not -Be 0
        $r.Output | Should -Match "echoue apres 2 tentatives"
    }
}

# ============================================================================
# Encrypt path — crash-safe: the developer's secrets file is never mutated
# ============================================================================
Describe "deploy-prod.ps1 SOPS encryption (shimmed)" {
    It "encrypts via a temp copy and leaves the source .env.prod byte-identical" {
        $proj = New-DeploySandbox (Join-Path $TestDrive "encrypt")
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-encrypt.log"
        $envProd = Join-Path $proj ".env.prod"
        $before = Get-Content $envProd -Raw
        $r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-RetryDelaySeconds", "0") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "ok" }
        $r.ExitCode | Should -Be 0
        # .env.prod is copied into PROD then renamed — but the SOURCE remains.
        (Get-Content $envProd -Raw) | Should -Be $before
        (Join-Path $proj ".env.prod.encrypted") | Should -Exist
        (Get-Content (Join-Path $proj ".env.prod.encrypted") -Raw) | Should -Match "encrypted_by_shim"
        (Join-Path $proj ".env.prod.sops.tmp") | Should -Not -Exist
    }
}

# ============================================================================
# Windows PowerShell 5.1 compatibility (static) — `task deploy:prod` invokes
# the driver through powershell.exe 5.1, while THIS suite runs under pwsh 7+.
# PS6+-only constructs therefore pass every hermetic test here yet crash in
# real use (seen live: 3-positional-argument Join-Path — -AdditionalChildPath
# does not exist in 5.1 — broke step 8 of a prod deploy). Guard statically.
# ============================================================================
Describe "deploy hardens every secret it ships (SEC-013, static)" {
    It "hardens the Firebase service-account key" {
        # Found at 0775 in production on 2026-07-24 while .env was correctly 0600:
        # the hardening step listed .env and the Claude credentials but not this
        # file. It is a Google service-account PRIVATE KEY, bind-mounted into the
        # API container — so any process there, including a skill script, could
        # read it. The 0700 parent only protects it from other HOST users.
        $src = Get-Content (Join-Path $RepoDeployDir "deploy-prod.ps1") -Raw
        $src | Should -Match 'apps/api/config' `
            -Because "the Firebase key directory must be hardened like the other secrets"
        $src | Should -Match "chmod 600 \{\}|chmod 600 .*\.json" `
            -Because "the service-account key must end up owner-readable only"
    }
}

Describe "deploy scripts SSH host authenticity (SEC-014, static)" {
    It "never disables host key checking" {
        # `StrictHostKeyChecking=no` accepted ANY host key on every run. This
        # flow ships the sources and the production .env, then runs deploy.sh
        # remotely: a spoofed host (DNS/ARP) would receive the secrets and could
        # return arbitrary output. `accept-new` pins on first contact and fails
        # when the key changes.
        $scripts = Get-ChildItem $RepoDeployDir -Filter *.ps1 |
            Where-Object Name -notlike "*.Tests.ps1"
        foreach ($script in $scripts) {
            $src = Get-Content $script.FullName -Raw
            $src | Should -Not -Match 'StrictHostKeyChecking\s*=\s*no' `
                -Because "$($script.Name) must not disable SSH host authenticity"
        }
    }

    It "never throws the pinned host key away" {
        # `UserKnownHostsFile=/dev/null` discarded the pin after each run, so a
        # substituted host was undetectable even on the second deployment.
        $scripts = Get-ChildItem $RepoDeployDir -Filter *.ps1 |
            Where-Object Name -notlike "*.Tests.ps1"
        foreach ($script in $scripts) {
            $src = Get-Content $script.FullName -Raw
            $src | Should -Not -Match 'UserKnownHostsFile\s*=\s*/dev/null' `
                -Because "$($script.Name) must keep a persistent known_hosts"
        }
    }
}

Describe "deploy scripts remote command substitution (static)" {
    It "never sends a `$(...) that the LOCAL shell would expand first" {
        # `Invoke-WithRetry` runs its command string through `cmd /c` on Windows
        # and `sh -c` on Linux/macOS. Only the second expands `$(...)`, so a
        # command substitution intended for the REMOTE shell is resolved locally
        # on a Unix host — silently, and only there.
        #
        # Both known cases were real: `chown -R $(whoami):$(whoami)` became
        # `chown -R runner:runner` in CI (the GitHub runner's account, applied to
        # the production server), and `echo PERMS_ENV=$(stat -c '%a' ...)` became
        # `PERMS_ENV=missing`, which made the SEC-013 hardening check fail every
        # deployment from a Unix host while passing from Windows.
        #
        # The fix is never an escape — no single string escapes correctly for
        # both shells. Interpolate the value in PowerShell when it is known
        # (`$SshUser`), or restructure so no substitution is needed at all
        # (`printf 'K='; cmd` instead of `echo K=$(cmd)`).
        # Matched on the BACKTICK-escaped form only. `$(...)` unescaped is a
        # PowerShell sub-expression, evaluated before the string ever leaves the
        # process and therefore harmless; ``$(...)`` is a dollar deliberately
        # protected FROM PowerShell, i.e. one meant for a shell — exactly the
        # construct that behaves differently on the two platforms. Comment lines
        # are skipped so this rationale can name the pattern it forbids.
        $scripts = Get-ChildItem $RepoDeployDir -Filter *.ps1 |
            Where-Object Name -notlike "*.Tests.ps1"
        foreach ($script in $scripts) {
            $offending = Get-Content $script.FullName |
                Where-Object { $_ -notmatch '^\s*#' } |
                Where-Object { $_ -match '`\$\(' }
            $offending | Should -BeNullOrEmpty `
                -Because ("$($script.Name) must not embed a shell command substitution: " +
                          "cmd /c leaves it literal, sh -c expands it locally")
        }
    }
}

Describe "deploy scripts Windows PowerShell 5.1 compatibility (static)" {
    It "uses no 3-positional-argument Join-Path (PS6+-only -AdditionalChildPath)" {
        $scripts = Get-ChildItem $RepoDeployDir -Filter *.ps1 |
            Where-Object Name -notlike "*.Tests.ps1"
        foreach ($script in $scripts) {
            $src = Get-Content $script.FullName -Raw
            # Two whitespace-separated quoted literals after Join-Path on one
            # line = a third positional argument. [ \t]+ (not \s+) so the gap
            # between the literals cannot silently span a line break on -Raw.
            $src | Should -Not -Match 'Join-Path\s+[^\r\n]*"[^"]*"[ \t]+"[^"]*"' `
                -Because "$($script.Name) must run under Windows PowerShell 5.1 (task deploy:prod)"
        }
    }
}

# ============================================================================
# Wiring: the GENERATED deploy.sh executed under bash with docker/curl shims —
# green readiness, red readiness with rollback, and unrecoverable failure.
# This is the "one system" proof: prepare-prod's heredoc + shipped gate lib.
# ============================================================================
# NOTE: no "<->" in the Describe name — Pester 6 fails parsing such names
# ("The term '$-' is not recognized").
Describe "generated deploy.sh to readiness-gate wiring (bash)" {
    BeforeAll {
        if (-not $script:BashExe -or -not (Get-Command $script:BashExe -ErrorAction SilentlyContinue)) {
            Set-ItResult -Skipped -Because "no usable bash on this machine"
        }
        $proj = New-DeploySandbox $TestDrive
        $bashBin = New-BashShimSet $TestDrive
        # Build the bundle directly (prepare-prod) — the driver tests above
        # already prove the driver invokes it.
        Push-Location $proj
        try {
            & pwsh -NoProfile -File (Join-Path $proj "scripts/deploy/prepare-prod.ps1") -Clean | Out-Null
        } finally {
            Pop-Location
        }
        $script:prod = Join-Path $proj "PROD"
        # The driver normally renames .env.prod -> .env (step 4); do it here.
        if (Test-Path (Join-Path $prod ".env.prod")) {
            Move-Item (Join-Path $prod ".env.prod") (Join-Path $prod ".env") -Force
        }
        $script:sha = Get-SandboxSha $proj
        $script:prodPosix = ConvertTo-BashPath $prod
        $script:binPosix = ConvertTo-BashPath $bashBin
        & $script:BashExe -c "chmod +x '$binPosix'/* '$prodPosix/deploy.sh' 2>/dev/null || true"
    }

    # Runs PROD/deploy.sh hermetically; returns @{ ExitCode; Output; ShimLog }.
    # (Defined here, not in the top BeforeAll, because it captures $prodPosix.)
    BeforeEach {
        $script:runDeploySh = {
            param([string]$Mode, [string]$HasRollback, [string]$LogName)
            $log = Join-Path $TestDrive $LogName
            $logPosix = ConvertTo-BashPath $log
            $counter = ConvertTo-BashPath (Join-Path $TestDrive "$LogName.curlcount")
            $cmd = "cd '$prodPosix' && export PATH='$binPosix':`$PATH SHIM_LOG='$logPosix' " +
            "READY_RETRIES=1 READY_SLEEP=0 CURL_MODE=$Mode CURL_FAILS=2 CURL_COUNTER='$counter' " +
            "HAS_ROLLBACK=$HasRollback && bash ./deploy.sh"
            $out = & $script:BashExe -c $cmd 2>&1 | Out-String
            @{
                ExitCode = $LASTEXITCODE
                Output   = $out
                ShimLog  = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
            }
        }
    }

    It "green readiness: exit 0, manifest carries the provenance identity" {
        $r = & $runDeploySh "green" "1" "wiring-green.log"
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match "API prete"
        $r.ShimLog | Should -Match "docker compose -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml -f docker-compose.devops.yml build"
        $r.ShimLog | Should -Match "up -d --force-recreate --wait"
        $manifest = Get-Content (Join-Path $prod "release-manifest.json") -Raw
        $manifest | Should -Match """git_commit_sha"": ""$sha"""
        $manifest | Should -Match '"app_version": "9.9.9-test"'
        $manifest | Should -Match '"status": "deployed"'
        # rollback never triggered on the green path
        $r.ShimLog | Should -Not -Match "docker tag lia-api:__rollback"
    }

    It "red readiness: automatic rollback to the previous image, exit 1" {
        Remove-Item (Join-Path $prod "release-manifest.json") -ErrorAction SilentlyContinue
        $r = & $runDeploySh "red_then_green" "1" "wiring-red.log"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "Rollback reussi"
        $r.ShimLog | Should -Match "docker tag lia-api:__rollback lia-api:local"
        (Join-Path $prod "release-manifest.json") | Should -Not -Exist
    }

    It "red readiness + no rollback point: critical failure, exit 1" {
        Remove-Item (Join-Path $prod "release-manifest.json") -ErrorAction SilentlyContinue
        $r = & $runDeploySh "red" "0" "wiring-critical.log"
        $r.ExitCode | Should -Be 1
        $r.Output | Should -Match "ERREUR CRITIQUE"
        (Join-Path $prod "release-manifest.json") | Should -Not -Exist
    }
}

# ============================================================================
# A2 — the live directory must survive the build
#
# Bind mounts resolve to an INODE at container creation. `rm -rf ~/lia/*`
# therefore breaks every directory mount of the CONTAINERS THAT ARE STILL
# SERVING, for the whole duration of the remote build (~10 min): the running
# API loses /app/config (Firebase credentials), /app/docs/knowledge (system RAG)
# and /app/data/skills/system. Observed live on 2026-08-05, mid-deployment:
#
#   docker exec lia-api-prod ls /app/config        -> empty
#   docker exec lia-api-prod ls /app/docs/knowledge -> empty
#
# while the host directories were fully populated. They came back only at
# `up --force-recreate`. This is the mechanism behind the recurring
# `firebase_init_failed` and `system_rag_startup_error` entries.
#
# The fix stages into a SEPARATE directory and swaps with `mv`: a rename keeps
# the inode alive, so the running containers hold valid mounts until they are
# recreated on purpose.
# ============================================================================
Describe "deploy-prod.ps1 keeps the live directory intact during the build (A2)" {
    BeforeAll {
        $proj = New-DeploySandbox (Join-Path $TestDrive "atomic")
        $bin = New-ShimSet $TestDrive
        $log = Join-Path $TestDrive "shim-atomic.log"
        $script:r = Invoke-DeployProd -Proj $proj -ShimBin $bin `
            -Arguments @("-SkipEncrypt", "-RetryDelaySeconds", "0", "-MaxRetries", "1") `
            -EnvOverrides @{ SHIM_LOG = $log; SSH_MODE = "fail_deploy" }
        $script:prod = Join-Path $proj "PROD"
        $script:shimLog = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
        $script:deploySh = Get-Content (Join-Path $script:prod "deploy.sh") -Raw
    }

    It "never wipes the live directory" {
        # The wipe is legitimate, but only against the staging directory that no
        # container mounts.
        $shimLog | Should -Not -Match ([regex]::Escape("rm -rf ~/lia/*"))
        $shimLog | Should -Not -Match ([regex]::Escape("rm -rf ~/lia/.[!.]*"))
    }

    It "wipes and fills a staging directory instead" {
        $shimLog | Should -Match ([regex]::Escape("rm -rf ~/lia.staging"))
        $shimLog | Should -Match ([regex]::Escape("lia.staging"))
    }

    It "runs the remote deploy from the staging directory" {
        $shimLog | Should -Match ([regex]::Escape("cd ~/lia.staging && chmod +x deploy.sh && ./deploy.sh"))
    }

    It "stages the demonstrator secrets BEFORE the swap consumes the directory" {
        # `deploy.sh` RENAMES the staging directory into the live one. A file
        # copied into the staging path afterwards lands nowhere: scp fails, the
        # warning scrolls past, and `task demo:prod:up` then refuses on an
        # absent file. Measured 2026-08-07 — a green deployment left ~/lia
        # without .env.demo-instance.prod.
        # The SCP specifically. Matching the file name alone measured the
        # hardening step's `chmod`, which names it too and always precedes the
        # deploy — so the assertion held whatever the order, and proved nothing
        # (caught by re-injecting the defect, 2026-08-07).
        $push = [regex]::Match($shimLog, "(?m)^scp .*\.env\.demo-instance\.prod")
        $swap = $shimLog.IndexOf("chmod +x deploy.sh")

        $push.Success | Should -BeTrue -Because "the pipeline must push the demonstrator secrets itself"
        $swap | Should -BeGreaterThan -1
        $push.Index | Should -BeLessThan $swap -Because "the swap consumes the staging directory the push targets"
    }

    It "swaps by renaming, never by deleting the live directory" {
        # `mv` preserves the inode of the directory being replaced, which is what
        # keeps the still-running containers' mounts valid. The paths are DERIVED
        # from the working directory rather than hard-coded, so the swap follows
        # a custom -RemoteDir automatically; the assertions match that derivation.
        $deploySh | Should -Match ([regex]::Escape('LIVE_DIR="${STAGING_DIR%.staging}"'))
        $deploySh | Should -Match ([regex]::Escape('mv "$STAGING_DIR" "$LIVE_DIR"'))
        $deploySh | Should -Not -Match "rm -rf .*LIVE_DIR"
    }

    It "runs unchanged outside the pipeline (manual relaunch)" {
        # A manual `./deploy.sh` from the live directory has nothing to swap.
        # Failing there would deny the operator the simplest restart, at the
        # worst possible moment.
        $deploySh | Should -Match ([regex]::Escape('aucune bascule'))
    }

    It "swaps AFTER the build and BEFORE the services are recreated" {
        $iBuild = $deploySh.IndexOf("docker compose -f docker-compose.prod.yml -f docker-compose.skill-sandbox.yml -f docker-compose.devops.yml build")
        $iSwap = $deploySh.IndexOf("SWAP_MARKER")
        $iUp = $deploySh.IndexOf("up -d --force-recreate --wait")
        $iBuild | Should -BeGreaterThan 0
        $iSwap | Should -BeGreaterThan $iBuild
        $iUp | Should -BeGreaterThan $iSwap
    }

    It "warns when the dumps sit inside the tree the deploy replaces" {
        # The operator's .env overrides the compose default, so shipping a safe
        # default is not enough — the deployment itself has to say it.
        $deploySh | Should -Match ([regex]::Escape('est DANS le repertoire deploye'))
        $deploySh | Should -Match ([regex]::Escape('../lia-data/postgres-backups'))
    }

    It "keeps the previous directory for rollback, with retention" {
        $deploySh | Should -Match ([regex]::Escape('PREV_DIR="${LIVE_DIR}.prev.'))
        # Unbounded generations would silently fill the SD card of the Pi.
        $deploySh | Should -Match ([regex]::Escape('tail -n +3'))
    }
}
