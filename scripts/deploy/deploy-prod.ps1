# ============================================================================
# Script de deploiement complet en production
# Usage: .\scripts\deploy\deploy-prod.ps1
#        .\scripts\deploy\deploy-prod.ps1 -SkipEncrypt   # Skip encryption step
#        .\scripts\deploy\deploy-prod.ps1 -DryRun       # Show what would be done
#        .\scripts\deploy\deploy-prod.ps1 -MaxRetries 5 # 5 retries per operation
#
# Features:
#   - Retry automatique avec backoff exponentiel (par defaut 3 tentatives)
#   - SSH keep-alive pour eviter les timeouts sur connexions lentes
#   - Utilise rsync si disponible (reprend les transferts interrompus)
#   - Fallback sur scp avec compression si rsync indisponible
# ============================================================================

param(
    [switch]$SkipEncrypt = $false,
    [switch]$DryRun = $false,
    [string]$SshHost = "your-server-ip",
    [int]$SshPort = 22,
    [string]$SshUser = "deploy",
    [string]$RemoteDir = "lia",
    [int]$MaxRetries = 3,
    [int]$RetryDelaySeconds = 5
)

$ErrorActionPreference = "Stop"

# Load local overrides (gitignored) if present
# Create scripts/deploy/deploy.local.ps1 with your personal values:
#   $SshHost = "10.0.0.100"
#   $SshPort = 22
#   $SshUser = "deploy"
$localConfig = Join-Path $PSScriptRoot "deploy.local.ps1"
if (Test-Path $localConfig) {
    . $localConfig
}

# Chemins
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$KeysDev = Join-Path $ProjectRoot "keys\age-key-dev.txt"
$KeysProd = Join-Path $ProjectRoot "keys\age-key-prod.txt"
$ProdDir = Join-Path $ProjectRoot "PROD"

# Options SSH pour maintenir la connexion active (format string pour commandes natives)
$SshOptionsStr = "-o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o ConnectTimeout=30 -o ConnectionAttempts=3"

# Couleurs
function Write-Step { param($msg) Write-Host "`n[$script:step] $msg" -ForegroundColor Cyan; $script:step++ }
function Write-Info { param($msg) Write-Host "    $msg" -ForegroundColor Gray }
function Write-Success { param($msg) Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Warning { param($msg) Write-Host "    WARN: $msg" -ForegroundColor Yellow }
function Write-Err { param($msg) Write-Host "    ERR: $msg" -ForegroundColor Red }

# ============================================================================
# Fonction de retry avec backoff exponentiel
# ============================================================================
function Invoke-WithRetry {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Command,
        [Parameter(Mandatory=$true)]
        [string]$OperationName,
        [int]$MaxAttempts = $MaxRetries,
        [int]$InitialDelaySeconds = $RetryDelaySeconds
    )

    $attempt = 1
    $delay = $InitialDelaySeconds

    while ($attempt -le $MaxAttempts) {
        Write-Info "Tentative $attempt/$MaxAttempts..."

        # Executer la commande - temporairement ignorer les erreurs natives (warnings SSH sur stderr)
        $prevErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            # Run the ssh/scp/rsync command string through the platform shell so
            # the Linux/macOS Task branch (pwsh) works too — the old `cmd /c` is
            # Windows-only (audit F040). `$IsWindows` is $null on Windows
            # PowerShell 5.1, which only ever runs on Windows, so treat that as
            # Windows and keep the original path byte-identical.
            if (($null -eq $IsWindows) -or $IsWindows) {
                $result = cmd /c $Command 2>&1
            } else {
                $result = sh -c $Command 2>&1
            }
            $exitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevErrorAction
        }

        # Filtrer les warnings SSH du resultat pour l'affichage
        $filteredResult = $result | Where-Object {
            $_ -notmatch "^Warning:.*added.*known hosts" -and
            $_ -notmatch "^Permanently added"
        }

        if ($exitCode -eq 0) {
            return $filteredResult
        }

        if ($attempt -eq $MaxAttempts) {
            Write-Err "$OperationName echoue apres $MaxAttempts tentatives"
            Write-Err "Derniere erreur (exit code $exitCode): $filteredResult"
            throw "$OperationName failed after $MaxAttempts attempts"
        }

        Write-Warning "$OperationName echoue (tentative $attempt/$MaxAttempts, exit code $exitCode)"
        Write-Info "Nouvelle tentative dans $delay secondes..."
        Start-Sleep -Seconds $delay
        $delay = [Math]::Min($delay * 2, 60)  # Backoff exponentiel, max 60s
        $attempt++
    }
}

function Invoke-SopsEncryptDotenv {
    # Encrypt a dotenv file with SOPS WITHOUT mutating the original secrets file.
    # SOPS dotenv does not support inline comments, so the comments are stripped
    # into a TEMP copy that is encrypted and then removed. The real .env is never
    # touched, so a crash mid-encrypt cannot leave the developer's secrets file
    # truncated (the previous in-place strip/restore was not crash-safe).
    param(
        [Parameter(Mandatory)] [string]$SourceEnv,
        [Parameter(Mandatory)] [string]$OutputEnc,
        [Parameter(Mandatory)] [string]$AgeKeyFile
    )
    $env:SOPS_AGE_KEY_FILE = $AgeKeyFile
    $tmp = "$SourceEnv.sops.tmp"
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $cleanLines = Get-Content $SourceEnv | ForEach-Object {
        if ($_ -match '^[A-Za-z_]') { $_ -replace '\s+#\s.*$', '' } else { $_ }
    }
    [IO.File]::WriteAllText($tmp, ($cleanLines -join "`n") + "`n", $utf8NoBom)
    try {
        # --filename-override: the comment-stripped copy is a temp file
        # (".env.prod.sops.tmp") that matches NO .sops.yaml creation rule —
        # the rules are anchored on the exact names (^\.env\.prod$). Overriding
        # the filename makes SOPS pick the SOURCE file's rule (regression fix:
        # "error loading config: no matching creation rules found").
        $result = sops --encrypt --input-type dotenv --output-type dotenv `
            --filename-override $SourceEnv $tmp 2>&1
        if ($LASTEXITCODE -eq 0) {
            $result | Out-File -FilePath $OutputEnc -Encoding utf8
            return $true
        }
        Write-Err "Echec du chiffrement: $result"
        return $false
    } finally {
        Remove-Item -Force $tmp -ErrorAction SilentlyContinue
    }
}

$script:step = 1

# ============================================================================
# Validation des parametres (securite)
# ============================================================================
if ([string]::IsNullOrWhiteSpace($SshHost) -or $SshHost -match '[;|&`$\s]') {
    # A metacharacter here reaches the same `cmd /c`/`sh -c` string as SshUser:
    # $sshTarget is "$SshUser@$SshHost". The denylist is deliberately NOT an
    # allowlist — an IPv6 literal contains ':' and must keep working.
    Write-Err "SshHost invalide: '$SshHost'"
    exit 1
}
if ($SshPort -lt 1 -or $SshPort -gt 65535) {
    Write-Err "SshPort invalide: $SshPort (doit etre entre 1 et 65535)"
    exit 1
}
if ([string]::IsNullOrWhiteSpace($SshUser) -or $SshUser -match '[;|&`$\s]') {
    Write-Err "SshUser invalide: '$SshUser'"
    exit 1
}
# SEC-038 — RemoteDir is interpolated into `sudo rm -rf ~/$RemoteDir/*` (step 6)
# and into `cp -r ~/$RemoteDir` (step 5). It is therefore validated HERE, before
# the first interpolation, and not next to the destructive command as it was:
# the backup step ran unguarded, and the denylist it used ('[;|&`$]' plus an
# all-whitespace check) accepted values that need no metacharacter to be
# catastrophic. `..` yielded `sudo rm -rf ~/../*` — every home directory on the
# host. `lia foo` yielded two targets, one of them relative to $HOME.
#
# The rule is an allowlist of ONE path segment starting with an alphanumeric:
# that single anchor rejects `.`, `..`, `-rf` (a leading dash is read as an
# option by rm/cp) and dotfiles, while `lia`, `lia-prod` and `lia_2` pass.
# \A..\z rather than ^..$ — in .NET, `$` also matches BEFORE a trailing
# newline, so "lia`n" would satisfy an ^..$ anchor and terminate the remote
# command line early.
if ($RemoteDir -notmatch '\A[A-Za-z0-9][A-Za-z0-9._-]*\z') {
    Write-Err "RemoteDir invalide: '$RemoteDir' (attendu: un seul segment, ex. 'lia')"
    exit 1
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host "  DEPLOIEMENT PRODUCTION - LIA" -ForegroundColor Magenta
Write-Host "========================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Cible:   $SshUser@$SshHost`:$SshPort/$RemoteDir" -ForegroundColor White
Write-Host "  Mode:    $(if ($DryRun) { 'DRY RUN (simulation)' } else { 'REEL' })" -ForegroundColor $(if ($DryRun) { 'Yellow' } else { 'Green' })
Write-Host "  Retries: $MaxRetries tentatives (delai initial: ${RetryDelaySeconds}s)" -ForegroundColor Gray
Write-Host ""

if ($DryRun) {
    Write-Host "  [DRY RUN] Aucune modification ne sera effectuee" -ForegroundColor Yellow
    Write-Host ""
}

# ============================================================================
# Etape 1: Chiffrement des fichiers .env
# ============================================================================
if (-not $SkipEncrypt) {
    Write-Step "Chiffrement des fichiers .env avec SOPS..."

    # Verifier que les cles existent
    if (-not (Test-Path $KeysProd)) {
        Write-Err "Cle PROD non trouvee: $KeysProd"
        exit 1
    }
    if (-not (Test-Path $KeysDev)) {
        Write-Err "Cle DEV non trouvee: $KeysDev"
        exit 1
    }

    # Chiffrer .env.prod
    $envProd = Join-Path $ProjectRoot ".env.prod"
    $envProdEnc = Join-Path $ProjectRoot ".env.prod.encrypted"
    if (Test-Path $envProd) {
        Write-Info "Chiffrement de .env.prod..."
        if (-not $DryRun) {
            if (Invoke-SopsEncryptDotenv -SourceEnv $envProd -OutputEnc $envProdEnc -AgeKeyFile $KeysProd) {
                Write-Success ".env.prod.encrypted cree"
            } else {
                exit 1
            }
        } else {
            Write-Info "[DRY RUN] sops --encrypt .env.prod > .env.prod.encrypted"
        }
    } else {
        Write-Warning ".env.prod non trouve, skip"
    }

    # Chiffrer .env (dev)
    $envDev = Join-Path $ProjectRoot ".env"
    $envDevEnc = Join-Path $ProjectRoot ".env.encrypted"
    if (Test-Path $envDev) {
        Write-Info "Chiffrement de .env (dev)..."
        if (-not $DryRun) {
            if (Invoke-SopsEncryptDotenv -SourceEnv $envDev -OutputEnc $envDevEnc -AgeKeyFile $KeysDev) {
                Write-Success ".env.encrypted cree"
            } else {
                exit 1
            }
        } else {
            Write-Info "[DRY RUN] sops --encrypt .env > .env.encrypted"
        }
    } else {
        Write-Warning ".env non trouve, skip"
    }
} else {
    Write-Step "Chiffrement SOPS ignore (--SkipEncrypt)"
}

# ============================================================================
# Etape 2: Preparation des livrables
# ============================================================================
Write-Step "Preparation des livrables (prepare-prod.ps1 -Clean)..."

$prepareScript = Join-Path $PSScriptRoot "prepare-prod.ps1"
if (-not $DryRun) {
    & $prepareScript -Clean
} else {
    Write-Info "[DRY RUN] & $prepareScript -Clean"
}

# ============================================================================
# Etape 3: Nettoyage des fichiers sensibles dans PROD
# ============================================================================
Write-Step "Nettoyage des fichiers sensibles dans PROD..."

$filesToRemove = @(
    (Join-Path $ProdDir "keys"),
    (Join-Path $ProdDir ".env.prod.encrypted"),
    (Join-Path $ProdDir ".sops.yaml")
)

foreach ($file in $filesToRemove) {
    if (Test-Path $file) {
        Write-Info "Suppression de $file..."
        if (-not $DryRun) {
            Remove-Item -Recurse -Force $file
        }
        Write-Success "$(Split-Path -Leaf $file) supprime"
    } else {
        Write-Info "$(Split-Path -Leaf $file) absent, skip"
    }
}

# ============================================================================
# Etape 4: Renommer .env.prod en .env
# ============================================================================
Write-Step "Renommage .env.prod -> .env dans PROD..."

$envProdInProd = Join-Path $ProdDir ".env.prod"
$envInProd = Join-Path $ProdDir ".env"

if (Test-Path $envProdInProd) {
    if (-not $DryRun) {
        if (Test-Path $envInProd) {
            Remove-Item $envInProd -Force
        }
        Rename-Item $envProdInProd ".env"
    }
    Write-Success ".env.prod renomme en .env"
} else {
    Write-Warning ".env.prod non trouve dans PROD"
}

# ============================================================================
# Etape 5: Backup horodate de la production actuelle
# ============================================================================
Write-Step "Backup horodate de la production actuelle..."

$sshTarget = "$SshUser@$SshHost"
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupDir = "lia-backups"
$backupName = "backup-$timestamp"

# Commande: creer dossier backups si necessaire, copier prod actuelle si elle existe
# Approche simple: mkdir -p est idempotent, cp echoue silencieusement si source vide
$backupCmd = "mkdir -p ~/$backupDir && cp -r ~/$RemoteDir ~/$backupDir/$backupName 2>/dev/null && echo BACKUP_CREATED || echo BACKUP_SKIPPED"

Write-Info "Connexion SSH: $sshTarget -p $SshPort"
Write-Info "Backup vers: ~/$backupDir/$backupName"

if (-not $DryRun) {
    $sshCmd = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$backupCmd`""
    $result = Invoke-WithRetry -Command $sshCmd -OperationName "Backup SSH"
    if ($result -match "BACKUP_CREATED") {
        Write-Success "Backup cree: ~/$backupDir/$backupName"
    } else {
        Write-Info "Aucun fichier a sauvegarder (dossier vide ou inexistant)"
    }
} else {
    Write-Info "[DRY RUN] ssh -p $SshPort $SshOptionsStr $sshTarget `"<backup commands>`""
    Write-Info "[DRY RUN] Backup serait cree dans: ~/$backupDir/$backupName"
}

# ============================================================================
# Etape 6: Suppression des anciens fichiers sur le serveur
# ============================================================================
Write-Step "Suppression des anciens fichiers sur le serveur..."

# SEC-038: RemoteDir is validated once, with the other parameters, before the
# banner and before step 5 already interpolates it. A second copy of the rule
# here would be a copy that drifts — the single validator is the contract, and
# nothing reassigns $RemoteDir between binding and this line.

# Utiliser sudo pour supprimer les fichiers crees par Docker (root ownership)
# Puis restaurer l'ownership du dossier pour eviter les permission denied lors du scp/rsync
$sshCmd = "sudo rm -rf ~/$RemoteDir/* ~/$RemoteDir/.[!.]* 2>/dev/null; mkdir -p ~/$RemoteDir && sudo chown -R `$(whoami):`$(whoami) ~/$RemoteDir"

Write-Info "Commande: $sshCmd"

if (-not $DryRun) {
    $cleanupCmd = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$sshCmd`""
    Invoke-WithRetry -Command $cleanupCmd -OperationName "Nettoyage SSH"
    Write-Success "Anciens fichiers supprimes"
} else {
    Write-Info "[DRY RUN] ssh -p $SshPort $SshOptionsStr $sshTarget `"$sshCmd`""
}

# ============================================================================
# Etape 7: Copie des fichiers vers le serveur
# ============================================================================
Write-Step "Copie des fichiers vers le serveur..."

Write-Info "Source: $ProdDir"
Write-Info "Destination: $sshTarget`:~/$RemoteDir/"

# Detecter si rsync est disponible (preferable pour gros fichiers, peut reprendre)
# Verifier d'abord rsync natif Windows, sinon rsync via WSL
$rsyncMode = $null
if (Get-Command rsync -ErrorAction SilentlyContinue) {
    $rsyncMode = "native"
    Write-Info "rsync natif detecte - utilisation pour transfert resilient"
} elseif (Get-Command wsl -ErrorAction SilentlyContinue) {
    # Verifier si rsync est disponible dans WSL
    $wslRsyncCheck = wsl which rsync 2>$null
    if ($wslRsyncCheck) {
        $rsyncMode = "wsl"
        Write-Info "rsync WSL detecte - utilisation pour transfert resilient"
    }
}
if (-not $rsyncMode) {
    Write-Info "rsync non disponible - utilisation de scp avec retry"
}

if (-not $DryRun) {
    if ($rsyncMode) {
        # rsync avec --partial (reprend les transferts interrompus)
        # -avz = archive, verbose, compress
        # --partial = garde les fichiers partiellement transferes
        # --progress = affiche la progression
        # -e "ssh -p PORT" = utilise SSH sur port specifique
        # SEC-014: accept-new pins the host key on first contact and REFUSES a
        # changed key afterwards. `no` accepted any key, every time — this flow
        # ships source and .env to the host and then triggers the deployment, so
        # an operator on a spoofed host/DNS could receive the secrets and return
        # arbitrary output. `accept-new` keeps first-run bootstrap frictionless
        # (no manual known_hosts seeding) while closing the substitution case.
        $rsyncSshOpts = "ssh -p $SshPort -o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o StrictHostKeyChecking=accept-new"
        $rsyncDst = "${sshTarget}:$RemoteDir/"

        if ($rsyncMode -eq "wsl") {
            # Convertir le chemin Windows en format WSL (/mnt/c/... ou /mnt/d/...)
            $driveLetter = $ProdDir.Substring(0, 1).ToLower()
            $wslPath = "/mnt/$driveLetter" + ($ProdDir.Substring(2) -replace '\\', '/')
            $rsyncSrc = "$wslPath/"

            # Copier la cle SSH Windows vers WSL avec permissions correctes (WSL monte Windows en 0777)
            # SSH refuse les cles avec permissions trop ouvertes
            $winSshDir = "/mnt/c/Users/$env:USERNAME/.ssh"
            $wslKeyPath = "~/.ssh/id_deploy_tmp"
            $sshKeySetup = ""

            # Tester les cles communes dans l'ordre de preference
            foreach ($keyName in @("id_ed25519", "id_rsa", "id_ecdsa")) {
                $testKey = wsl bash -c "test -f $winSshDir/$keyName && echo exists" 2>$null
                if ($testKey -eq "exists") {
                    # Copier la cle avec bonnes permissions
                    $sshKeySetup = "mkdir -p ~/.ssh && cp $winSshDir/$keyName $wslKeyPath && chmod 600 $wslKeyPath && "
                    Write-Info "Cle SSH trouvee: $winSshDir/$keyName -> $wslKeyPath"
                    break
                }
            }

            if (-not $sshKeySetup) {
                Write-Warning "Aucune cle SSH Windows trouvee dans $winSshDir"
                $wslKeyPath = ""
            }

            # Construire les options SSH
            # SEC-014: host authenticity used to be disabled outright, and the
            # learned key was written to a throwaway file, so a substituted host
            # went undetected even on the second deployment. This transfer
            # carries the sources and the production .env, then runs deploy.sh
            # remotely.
            #
            # `accept-new` + the default persistent known_hosts inside WSL keeps
            # the first run frictionless (the key is learned and pinned) and
            # fails loudly if the host key ever changes. Rotating the Pi's host
            # key therefore requires removing its entry from ~/.ssh/known_hosts
            # in WSL — that friction is the control.
            $sshKeyOpt = if ($wslKeyPath) { "-i $wslKeyPath" } else { "" }
            $rsyncSshOpts = "ssh -p $SshPort $sshKeyOpt -o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o StrictHostKeyChecking=accept-new"

            Write-Info "Chemin WSL: $rsyncSrc"
            Write-Info "Destination: $rsyncDst"

            # Executer rsync via WSL avec bash -c pour eviter les problemes de parsing
            # --no-perms --no-owner --no-group : evite les erreurs de permission sur les fichiers Docker
            # La commande complete est executee dans WSL
            # IMPORTANT: Cleanup de la cle temporaire apres rsync (securite)
            $sshKeyCleanup = if ($wslKeyPath) { " ; rm -f $wslKeyPath" } else { "" }
            $rsyncInnerCmd = "${sshKeySetup}rsync -avz --partial --progress --timeout=120 --no-perms --no-owner --no-group -e '$rsyncSshOpts' '$rsyncSrc' '$rsyncDst'$sshKeyCleanup"
            $rsyncCmd = "wsl bash -c `"$rsyncInnerCmd`""
        } else {
            # rsync natif Windows
            $rsyncSrc = ($ProdDir -replace '\\', '/') + "/"
            Write-Info "Utilisation de rsync natif (resilient, reprend les transferts)..."
            $rsyncCmd = "rsync -avz --partial --progress --timeout=120 --no-perms --no-owner --no-group -e `"$rsyncSshOpts`" `"$rsyncSrc`" `"$rsyncDst`""
        }

        Invoke-WithRetry -Command $rsyncCmd -OperationName "Rsync transfert" -MaxAttempts 5
        Write-Success "Fichiers copies avec rsync"
    } else {
        # Fallback SCP avec retry et options SSH
        # Note: Sur Windows, le glob * n'inclut pas les fichiers caches (dotfiles)
        # On copie d'abord les fichiers normaux, puis explicitement les dotfiles

        Write-Info "Copie des fichiers (scp avec retry)..."
        $scpCmd = "scp -P $SshPort $SshOptionsStr -r -C `"$ProdDir/*`" `"${sshTarget}:~/$RemoteDir/`""
        Invoke-WithRetry -Command $scpCmd -OperationName "SCP fichiers" -MaxAttempts 5

        # Copier explicitement les dotfiles (.env, etc.)
        $dotfiles = Get-ChildItem -Path $ProdDir -Filter ".*" -File -Force
        if ($dotfiles) {
            Write-Info "Copie des dotfiles..."
            foreach ($dotfile in $dotfiles) {
                $dotfilePath = $dotfile.FullName
                $dotfileName = $dotfile.Name
                $scpDotfileCmd = "scp -P $SshPort $SshOptionsStr -C `"$dotfilePath`" `"${sshTarget}:~/$RemoteDir/`""
                Invoke-WithRetry -Command $scpDotfileCmd -OperationName "SCP $dotfileName" -MaxAttempts 3
                Write-Info "  + $dotfileName"
            }
        }
        Write-Success "Fichiers copies avec scp"
    }
} else {
    if ($rsyncMode -eq "wsl") {
        $driveLetter = $ProdDir.Substring(0, 1).ToLower()
        $wslPath = "/mnt/$driveLetter" + ($ProdDir.Substring(2) -replace '\\', '/')
        Write-Info "[DRY RUN] wsl rsync -avz --partial --progress `"$wslPath/`" `"${sshTarget}:~/$RemoteDir/`""
    } elseif ($rsyncMode -eq "native") {
        Write-Info "[DRY RUN] rsync -avz --partial --progress `"$ProdDir/`" `"${sshTarget}:~/$RemoteDir/`""
    } else {
        Write-Info "[DRY RUN] scp -P $SshPort $SshOptionsStr -r -C `"$ProdDir/*`" `"${sshTarget}:~/$RemoteDir/`""
        Write-Info "[DRY RUN] + copie explicite des dotfiles (.env, etc.)"
    }
}

# ============================================================================
# Etape 8: Setup DevOps (DOCKER_GID + Claude CLI credentials) — BEFORE deploy
# ============================================================================
# Must run BEFORE deploy.sh because docker compose up reads DOCKER_GID from .env
Write-Step "Setting up DevOps prerequisites on remote server..."

# These are real remote mutations (write remote .env, create ~/.claude, copy
# credentials), so they MUST respect -DryRun — otherwise a "simulation" run
# still changes the server (audit F040/DryRun).
if (-not $DryRun) {
    # Ensure DOCKER_GID is set in remote .env (required for Docker socket access)
    Invoke-WithRetry -OperationName "Set DOCKER_GID" -Command @"
ssh $SshOptionsStr -p $SshPort ${SshUser}@${SshHost} "grep -q DOCKER_GID ~/${RemoteDir}/.env 2>/dev/null || echo DOCKER_GID=`$(stat -c '%g' /var/run/docker.sock) >> ~/${RemoteDir}/.env && echo DOCKER_GID set"
"@

    # Deploy Claude CLI credentials (same auth as dev — same Anthropic account)
    # $env:USERPROFILE is Windows-only: fall back to $HOME so the pwsh/Unix
    # branch (audit F008 hermetic tests) does not crash Join-Path on an empty
    # path. The Windows behavior is byte-identical (USERPROFILE always set).
    $userHome = if ($env:USERPROFILE) { $env:USERPROFILE } elseif ($env:HOME) { $env:HOME } else { $null }
    # Nested Join-Path on purpose: the 3-argument form (-AdditionalChildPath)
    # requires PowerShell 6+, and `task deploy:prod` runs under Windows
    # PowerShell 5.1 where it is a positional-parameter error.
    $LocalCreds = if ($userHome) { Join-Path (Join-Path $userHome ".claude") ".credentials.json" } else { $null }
    if ($LocalCreds -and (Test-Path $LocalCreds)) {
        Invoke-WithRetry -OperationName "Create remote .claude directory" -Command @"
ssh $SshOptionsStr -p $SshPort ${SshUser}@${SshHost} "mkdir -p ~/.claude"
"@

        Invoke-WithRetry -OperationName "Copy Claude CLI credentials" -Command @"
scp $SshOptionsStr -P $SshPort "$LocalCreds" ${SshUser}@${SshHost}:~/.claude/.credentials.json
"@

        Write-Success "Claude CLI credentials deployed"
    } else {
        Write-Warning "No local Claude CLI credentials. Run 'claude auth login' locally first."
    }
} else {
    Write-Info "[DRY RUN] ssh set DOCKER_GID in remote .env; ssh mkdir ~/.claude; scp Claude CLI credentials"
}

# ============================================================================
# Etape 8.5: Durcissement des permissions des secrets (SEC-013)
# ============================================================================
# The remote .env holds every application/integration secret. rsync pushes it
# with permissive bits, and Etape 8 just appended DOCKER_GID (the last write to
# it), so harden NOW — after the .env is final and BEFORE `docker compose up`.
# Target: .env = 0600 (owner rw only) inside a 0700 directory, plus the Claude
# CLI credentials. The Docker daemon runs as root and still reads the bind
# mounts; `docker compose` runs as the owner and traverses its own 0700 dir —
# so 0600/0700 breaks nothing.
#
# SEC-013 — this step used to end in a bare `echo PERMS_HARDENED`, which runs
# whether or not a single chmod succeeded. The driver then matched on that
# string and reported success: the check could not fail, so it verified nothing.
# It now READS BACK the resulting modes with `stat` and refuses to deploy when
# the production .env is not 0600 inside a 0700 directory.
#
# Blocking, deliberately, and only on those two: that file holds every
# application and integration secret, and continuing past a failed hardening
# means knowingly starting the platform with its secrets world-readable. The
# optional artifacts (Claude CLI credentials, Firebase key) are reported but
# never fatal — they may legitimately be absent.
#
# The Firebase service-account key was missing from this list and was found at
# 0775 in production on 2026-07-24 — a Google service-account private key
# readable by every process of the API container, including a skill script.
# The 0700 parent directory hides it from other host users, but the key is
# bind-mounted into the container, so in-container modes are what protect it.
Write-Step "Durcissement des permissions des secrets (SEC-013)..."

if (-not $DryRun) {
    # The trailing `stat` calls are the verification: they report the mode that
    # actually landed, so an unreported chmod failure cannot pass as a success.
    $hardenCmd = "chmod 700 ~/$RemoteDir 2>/dev/null; [ -f ~/$RemoteDir/.env ] && chmod 600 ~/$RemoteDir/.env; [ -d ~/.claude ] && chmod 700 ~/.claude; [ -f ~/.claude/.credentials.json ] && chmod 600 ~/.claude/.credentials.json; [ -d ~/$RemoteDir/apps/api/config ] && chmod 700 ~/$RemoteDir/apps/api/config; find ~/$RemoteDir/apps/api/config -maxdepth 1 -type f -name '*.json' -exec chmod 600 {} + 2>/dev/null; echo PERMS_ENV=`$(stat -c '%a' ~/$RemoteDir/.env 2>/dev/null || echo missing); echo PERMS_DIR=`$(stat -c '%a' ~/$RemoteDir 2>/dev/null || echo missing)"
    $hardenSsh = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$hardenCmd`""
    $hardenResult = Invoke-WithRetry -Command $hardenSsh -OperationName "Harden secret permissions" -MaxAttempts 2

    $hardenText = ($hardenResult | Out-String)
    $envMode = if ($hardenText -match 'PERMS_ENV=(\S+)') { $Matches[1] } else { "unknown" }
    $dirMode = if ($hardenText -match 'PERMS_DIR=(\S+)') { $Matches[1] } else { "unknown" }

    if ($envMode -ne "600" -or $dirMode -ne "700") {
        Write-Err "Durcissement des permissions ECHOUE (SEC-013)"
        Write-Err "  ~/$RemoteDir/.env attendu 600, obtenu: $envMode"
        Write-Err "  ~/$RemoteDir    attendu 700, obtenu: $dirMode"
        Write-Err "Le .env de production contient tous les secrets applicatifs."
        Write-Err "Deploiement interrompu avant 'docker compose up'."
        exit 1
    }
    Write-Success "Permissions secrets durcies et verifiees (.env $envMode, dossier $dirMode)"
} else {
    Write-Info "[DRY RUN] ssh chmod 700 ~/$RemoteDir ; chmod 600 ~/$RemoteDir/.env ; chmod 700 ~/.claude ; chmod 600 ~/.claude/.credentials.json ; chmod 700 apps/api/config ; chmod 600 apps/api/config/*.json"
}

# ============================================================================
# Etape 9: Execution du script de deploiement sur le serveur
# ============================================================================
Write-Step "Execution du deploiement sur le serveur..."

$deployCmd = "cd ~/$RemoteDir && chmod +x deploy.sh && ./deploy.sh"

Write-Info "Commande: $deployCmd"

if (-not $DryRun) {
    $fullDeployCmd = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$deployCmd`""
    Write-Info "Execution: $fullDeployCmd"
    # Cross-platform shell (F040): cmd /c is Windows-only. $IsWindows is $null on
    # Windows PowerShell 5.1 (Windows-only), so that path stays byte-identical.
    if (($null -eq $IsWindows) -or $IsWindows) {
        cmd /c $fullDeployCmd
    } else {
        sh -c $fullDeployCmd
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Echec du deploiement (exit code: $LASTEXITCODE)"
        exit 1
    }
    Write-Success "Deploiement termine"
} else {
    Write-Info "[DRY RUN] ssh -p $SshPort $SshOptionsStr $sshTarget `"$deployCmd`""
}

# ============================================================================
# Etape 10: Nettoyage du dossier PROD local
# ============================================================================
Write-Step "Nettoyage du dossier PROD local..."

if (Test-Path $ProdDir) {
    if (-not $DryRun) {
        Remove-Item -Recurse -Force $ProdDir
        Write-Success "Dossier PROD supprime"
    } else {
        Write-Info "[DRY RUN] Remove-Item -Recurse -Force `"$ProdDir`""
    }
} else {
    Write-Info "Dossier PROD absent, skip"
}

# ============================================================================
# Resume
# ============================================================================
Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  DEPLOIEMENT TERMINE AVEC SUCCES!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Services disponibles:" -ForegroundColor White
Write-Host "    - API:      http://$SshHost`:8000" -ForegroundColor Gray
Write-Host "    - Web:      http://$SshHost`:3000" -ForegroundColor Gray
Write-Host "    - Grafana:  http://$SshHost`:3001" -ForegroundColor Gray
Write-Host "    - Langfuse: http://$SshHost`:3002" -ForegroundColor Gray
Write-Host ""
Write-Host "  Commandes utiles:" -ForegroundColor White
Write-Host "    ssh -p $SshPort $SshUser@$SshHost `"cd $RemoteDir && docker compose -f docker-compose.prod.yml logs -f`"" -ForegroundColor Gray
Write-Host "    ssh -p $SshPort $SshUser@$SshHost `"cd $RemoteDir && docker compose -f docker-compose.prod.yml ps`"" -ForegroundColor Gray
Write-Host ""
