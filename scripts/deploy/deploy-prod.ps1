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
            $result = cmd /c $Command 2>&1
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

$script:step = 1

# ============================================================================
# Validation des parametres (securite)
# ============================================================================
if ([string]::IsNullOrWhiteSpace($SshHost)) {
    Write-Err "SshHost ne peut pas etre vide"
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
            $env:SOPS_AGE_KEY_FILE = $KeysProd
            $result = sops --encrypt --input-type dotenv --output-type dotenv $envProd 2>&1
            if ($LASTEXITCODE -eq 0) {
                $result | Out-File -FilePath $envProdEnc -Encoding utf8
                Write-Success ".env.prod.encrypted cree"
            } else {
                Write-Err "Echec du chiffrement: $result"
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
            $env:SOPS_AGE_KEY_FILE = $KeysDev
            $result = sops --encrypt --input-type dotenv --output-type dotenv $envDev 2>&1
            if ($LASTEXITCODE -eq 0) {
                $result | Out-File -FilePath $envDevEnc -Encoding utf8
                Write-Success ".env.encrypted cree"
            } else {
                Write-Err "Echec du chiffrement: $result"
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
        Write-Info "$(Split-Path -Leaf $file) n'existe pas, skip"
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

# Validation securite: RemoteDir ne doit pas etre vide ou contenir des caracteres dangereux
if ([string]::IsNullOrWhiteSpace($RemoteDir) -or $RemoteDir -match '[;|&`$]' -or $RemoteDir -eq "/" -or $RemoteDir -eq "~") {
    Write-Err "RemoteDir invalide ou dangereux: '$RemoteDir'"
    exit 1
}

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
        $rsyncSshOpts = "ssh -p $SshPort -o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o StrictHostKeyChecking=no"
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
            # NOTE SECURITE: StrictHostKeyChecking=no desactive la verification de l'hote
            # Acceptable pour deploiement reseau local vers Raspberry Pi connu
            # En production cloud, utiliser StrictHostKeyChecking=accept-new et gerer known_hosts
            $sshKeyOpt = if ($wslKeyPath) { "-i $wslKeyPath" } else { "" }
            $rsyncSshOpts = "ssh -p $SshPort $sshKeyOpt -o ServerAliveInterval=30 -o ServerAliveCountMax=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

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
# Etape 8: Execution du script de deploiement sur le serveur
# ============================================================================
Write-Step "Execution du deploiement sur le serveur..."

$deployCmd = "cd ~/$RemoteDir && chmod +x deploy.sh && ./deploy.sh"

Write-Info "Commande: $deployCmd"

if (-not $DryRun) {
    # Le deploiement lui-meme ne devrait pas etre retry (idempotence non garantie)
    # Mais on utilise les options SSH pour maintenir la connexion
    $fullDeployCmd = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$deployCmd`""
    Write-Info "Execution: $fullDeployCmd"
    cmd /c $fullDeployCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Echec du deploiement (exit code: $LASTEXITCODE)"
        exit 1
    }
    Write-Success "Deploiement termine"
} else {
    Write-Info "[DRY RUN] ssh -p $SshPort $SshOptionsStr $sshTarget `"$deployCmd`""
}

# ============================================================================
# Etape 9: Nettoyage du dossier PROD local
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
    Write-Info "Dossier PROD n'existe pas, skip"
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
