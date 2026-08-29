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
    [int]$RetryDelaySeconds = 5,
    # ADR-250: le deploiement distant tourne DETACHE et le pilote scrute son
    # verdict. Ces deux bornes sont a l'operateur, pas au script : un Pi charge
    # depasse les 11 minutes mesurees en v1.37.0, et le budget epuise ne rend
    # pas un echec mais un `inconnu` -- il vaut donc mieux pouvoir l'allonger
    # que d'apprendre a lire un verdict prudent comme une panne.
    [int]$DeployPollSeconds = 5,
    [int]$DeployBudgetSeconds = 2700
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

# ADR-250: la regle "255 ne dit rien du distant" vit dans UNE bibliotheque,
# partagee avec demo-prod.ps1. Son absence est une erreur franche, pas une
# degradation silencieuse : un pilote qui perdrait cette classification
# recommencerait a annoncer des echecs qu'il ne peut pas constater.
$remoteExitLib = Join-Path $PSScriptRoot "lib/RemoteExit.ps1"
if (-not (Test-Path $remoteExitLib)) {
    Write-Host "ERR: bibliotheque introuvable: $remoteExitLib" -ForegroundColor Red
    exit 1
}
. $remoteExitLib

# ADR-250: l'execution distante detachee. Meme regle que ci-dessus -- son
# absence est une erreur franche : un pilote qui la perdrait retomberait sur
# une session ssh bloquante, ou la survie du deploiement depend de la survie
# de la connexion.
$remoteRunLib = Join-Path $PSScriptRoot "lib/RemoteRun.ps1"
if (-not (Test-Path $remoteRunLib)) {
    Write-Host "ERR: bibliotheque introuvable: $remoteRunLib" -ForegroundColor Red
    exit 1
}
. $remoteRunLib

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
# SEC-038 — RemoteDir is interpolated into `cp -r ~/$RemoteDir` (step 5) and,
# through the $StagingDir derived from it below, into `sudo rm -rf ~/$StagingDir`
# (step 6). It is therefore validated HERE, before the first interpolation and
# before that derivation, and not next to the destructive command as it was:
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

# Le bundle est depose dans un repertoire de STAGING, jamais dans le repertoire
# vivant. Un bind mount est resolu vers un INODE a la creation du conteneur :
# `rm -rf ~/lia/*` casse donc tous les montages de repertoire des conteneurs QUI
# SERVENT ENCORE, pendant toute la duree du build distant (~10 min). Constate en
# direct le 2026-08-05, en plein deploiement : l'API en production voyait
# /app/config, /app/docs/knowledge et /app/data/skills/system VIDES alors que
# l'hote etait peuple — d'ou les `firebase_init_failed` et
# `system_rag_startup_error` recurrents. La bascule finale se fait par `mv`
# (renommage), qui preserve l'inode : les conteneurs encore vivants gardent des
# montages valides jusqu'a leur recreation deliberee.
# Derive du parametre DEJA valide ci-dessus : le suffixe ne peut pas introduire
# de segment de chemin ni de metacaractere shell.
$StagingDir = "$RemoteDir.staging"

# ============================================================================
# SEC-040: les porteurs de secret dans PROD/, declares UNE fois
# ============================================================================
# `PROD/.env` est le fichier d'environnement de production EN CLAIR (l'etape 4
# y renomme le `.env.prod` dechiffre). L'etape 10 supprime tout le bundle --
# mais elle ne s'execute que sur le chemin nominal, et ce pilote a 14 sorties
# prematurees (11 `exit`, 3 `throw`). Pire : `deploy:prod` se termine sur une
# session SSH reinitialisee meme quand le deploiement REUSSIT (le skill
# lia-deploy-prod le documente : "the exit code lies"), donc le chemin d'echec
# est le chemin NOMINAL et la fuite etait systematique. Mesure le 2026-07-28 :
# 434 Mo de bundle survivant a un deploiement qui avait pourtant abouti.
#
# La liste est EXACTE, jamais un glob : `provenance.env` vit dans le meme
# repertoire, n'est pas un secret, et quatre tests le lisent.
#
# Elle sert deux fois -- a l'etape 3 (purger ce qu'une execution precedente
# aurait laisse, AVANT de constituer le bundle) et dans le `finally` finel
# (ne rien laisser derriere soi). Une seule declaration : deux listes
# auraient diverge.
# DEUX ensembles, et leur difference est le coeur du sujet : l'etape 3 purge
# AVANT que le bundle parte, l'etape 4 a encore besoin de `.env.prod` pour le
# renommer en `.env`. Les confondre supprime la source avant son renommage --
# le bundle part alors SANS fichier d'environnement, et le deploiement echoue
# a distance sur un `.env` absent. Mesure : cette erreur exacte a fait tomber
# le test "renamed .env.prod to .env inside the bundle" a la premiere passe.
#
# `.env` figure dans le lot pre-transfert a dessein : un `.env` residuel d'une
# execution avortee etait sinon EXPEDIE en production quand `.env.prod` est
# absent, l'etape 4 ne le supprimant que sur la branche ou elle renomme.
$SensitivePreTransfer = @(
    ".env",                  # residu d'une execution precedente
    ".env.prod.encrypted",   # archive SOPS
    ".sops.yaml",            # regles de chiffrement
    "keys"                   # cle age de production (repertoire)
)

# Le nettoyage final retire tout : le lot ci-dessus PLUS la production en clair
# et sa source, qui n'ont plus aucune raison de survivre a l'execution.
$SensitiveInProd = $SensitivePreTransfer + @(".env.prod")

function Remove-SensitiveFromProd {
    <#
        .SYNOPSIS
        Retire de PROD/ les seuls porteurs de secret, et rien d'autre.

        .DESCRIPTION
        Chirurgical par construction : un `Remove-Item PROD` complet
        detruirait le bundle qu'un operateur inspecte apres un echec, et un
        glob `*.env` emporterait `provenance.env`, qui n'est pas un secret.
        Silencieux quand il n'y a rien a faire -- il s'execute a chaque sortie.
    #>
    param([string]$Dir, [switch]$Quiet)

    if (-not (Test-Path $Dir)) { return @() }
    $removed = @()
    foreach ($name in $SensitiveInProd) {
        $path = Join-Path $Dir $name
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path -ErrorAction SilentlyContinue
            if (-not (Test-Path $path)) { $removed += $name }
        }
    }
    # Le script parle une langue stricte : Write-Step (cyan, numerote),
    # Write-Info (gris), Write-Success ("OK:", vert), Write-Warning ("WARN:"),
    # Write-Err ("ERR:"). Un `Write-Host` brut dans une couleur absente de
    # cette palette se lit comme une anomalie d'affichage.
    #
    # `Write-Success` et non `Write-Warning` : rien ne s'est mal passe ICI.
    # Sur un chemin d'echec, cette ligne est meme la seule bonne nouvelle --
    # elle dit a l'operateur que ses identifiants de production ne trainent
    # pas sur son poste. Le marqueur SEC-040 suit la convention de SEC-013,
    # deja porte par des messages d'execution.
    if ($removed.Count -gt 0 -and -not $Quiet) {
        Write-Success "SEC-040: secrets retires de PROD/ ($($removed -join ', '))"
    }
    return $removed
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
# SEC-040: a partir d'ici, TOUTE sortie passe par le nettoyage final
# ============================================================================
# PowerShell execute un `finally` sur `exit` comme sur un `throw` non rattrape,
# en preservant le code de retour -- verifie sur powershell 5.1 ET pwsh 7. Le
# corps n'est pas reindente : le langage n'y est pas sensible, et un
# reindentation de 600 lignes aurait noye le correctif dans le diff.
try {

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

# Derive de $SensitivePreTransfer (SEC-040) : le lot PRE-TRANSFERT, qui
# exclut deliberement `.env.prod` -- l'etape 4 doit encore le renommer.
$filesToRemove = $SensitivePreTransfer | ForEach-Object { Join-Path $ProdDir $_ }

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
# `$SshUser` rather than a remote `$(whoami)`: `Invoke-WithRetry` runs this
# string through `cmd /c` on Windows but `sh -c` on Linux/macOS, and only the
# second expands `$(...)`. The substitution was therefore resolved LOCALLY on a
# Unix host — a deployment from Linux issued `chown -R <local-user>:<local-user>`
# on the SERVER (observed in CI as `chown -R runner:runner`). The account that
# owns the files is the account we connect as, which PowerShell already knows
# and which the parameter validation above has already constrained.
$sshCmd = "sudo rm -rf ~/$StagingDir/* ~/$StagingDir/.[!.]* 2>/dev/null; mkdir -p ~/$StagingDir && sudo chown -R ${SshUser}:${SshUser} ~/$StagingDir"

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
Write-Info "Destination: $sshTarget`:~/$StagingDir/"

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
        # Presence is not reachability: WSL runs behind its own NAT and can
        # have NO route to a LAN host Windows reaches perfectly well (measured
        # 2026-08-24 -- "Network is unreachable" from WSL while native ssh
        # worked throughout). Choosing this transport on `which rsync` alone
        # selected one that could not connect, and the deployment carried on
        # against an EMPTY staging directory.
        $wslReach = wsl bash -c "timeout 8 bash -c '</dev/tcp/$SshHost/$SshPort' 2>/dev/null && echo reachable" 2>$null
        if ($wslReach -match "reachable") {
            $rsyncMode = "wsl"
            Write-Info "rsync WSL detecte, hote joignable depuis WSL - transfert resilient"
        } else {
            Write-Warning "rsync WSL present mais ${SshHost}:${SshPort} INJOIGNABLE depuis WSL - bascule sur scp"
        }
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
        $rsyncDst = "${sshTarget}:$StagingDir/"

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

        # The entries are ENUMERATED, never globbed. `scp ... "$ProdDir/*"`
        # runs through `cmd /c`, which does not expand `*` inside a quoted
        # argument, so scp received the literal path and answered
        # `stat local "...\PROD/*": No such file or directory` (measured
        # 2026-08-24, the first time this fallback ever ran -- WSL rsync had
        # always won before). Enumerating also carries the dotfiles, which the
        # glob could not, so the separate `.env` pass below it disappears.
        Write-Info "Copie des fichiers (scp avec retry)..."
        $entries = Get-ChildItem -Path $ProdDir -Force
        if (-not $entries) {
            throw "Le dossier $ProdDir est vide: rien a transferer"
        }
        $quoted = ($entries | ForEach-Object { "`"$($_.FullName)`"" }) -join " "
        Write-Info "  $($entries.Count) entrees a transferer (dotfiles inclus)"
        $scpCmd = "scp -P $SshPort $SshOptionsStr -r -C $quoted `"${sshTarget}:~/$StagingDir/`""
        Invoke-WithRetry -Command $scpCmd -OperationName "SCP fichiers" -MaxAttempts 5
        Write-Success "Fichiers copies avec scp"
    }

    # Absence of an exception is not proof of delivery. The rsync branch above
    # printed "Fichiers copies" on a transfer that moved ZERO bytes (measured
    # 2026-08-24: WSL had no route to the host, rsync exited 255, and the
    # pipeline carried on through four more steps before failing on a missing
    # deploy.sh). The transfer is a promise; this is the postcondition that
    # makes it one.
    $landed = Invoke-WithRetry `
        -Command "ssh -p $SshPort $SshOptionsStr $sshTarget `"test -f ~/$StagingDir/deploy.sh && test -f ~/$StagingDir/.env && ls ~/$StagingDir | wc -l`"" `
        -OperationName "Verification du transfert" -MaxAttempts 2
    $landedCount = ($landed | Select-Object -Last 1) -as [int]
    if (-not $landedCount -or $landedCount -lt 5) {
        Write-Err "Transfert INCOMPLET: ~/$StagingDir contient $landedCount entree(s) et il manque deploy.sh ou .env"
        Write-Err "La production n'a PAS ete touchee. Verifier le transport (rsync/scp) avant de relancer."
        throw "Transfer postcondition failed: staging directory is not deployable"
    }
    Write-Success "Transfert verifie: $landedCount entrees, deploy.sh et .env presents"
} else {
    if ($rsyncMode -eq "wsl") {
        $driveLetter = $ProdDir.Substring(0, 1).ToLower()
        $wslPath = "/mnt/$driveLetter" + ($ProdDir.Substring(2) -replace '\\', '/')
        Write-Info "[DRY RUN] wsl rsync -avz --partial --progress `"$wslPath/`" `"${sshTarget}:~/$StagingDir/`""
    } elseif ($rsyncMode -eq "native") {
        Write-Info "[DRY RUN] rsync -avz --partial --progress `"$ProdDir/`" `"${sshTarget}:~/$StagingDir/`""
    } else {
        Write-Info "[DRY RUN] scp -P $SshPort $SshOptionsStr -r -C `"$ProdDir/*`" `"${sshTarget}:~/$StagingDir/`""
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
    # Ensure DOCKER_GID is set in remote .env (required for Docker socket access).
    #
    # `printf` + `stat` instead of `DOCKER_GID=$(stat ...)`: this string reaches
    # `sh -c` on a Unix host (Invoke-WithRetry), which expands the substitution
    # LOCALLY. The remote .env would then receive the docker GID of the machine
    # that ran the deployment — observed in CI as `DOCKER_GID=118`, the runner's.
    # A wrong GID here means the API container cannot reach the Docker socket,
    # which is what the skill sandbox (SEC-001) runs on.
    #
    # Target the STAGING .env, not the live one: deploy.sh atomically renames
    # ~/$StagingDir over ~/$RemoteDir (ADR-215), so a value appended to the
    # retired live .env is silently discarded by the swap. That exact miss ran
    # in production 2026-08-08 → 2026-08-15: group_add fell back to 999 (host
    # docker GID was 984) and every container-sandboxed skill script died on
    # a Docker-socket EACCES.
    $gidCmd = "grep -q DOCKER_GID ~/${StagingDir}/.env 2>/dev/null || { printf 'DOCKER_GID=' >> ~/${StagingDir}/.env; stat -c '%g' /var/run/docker.sock >> ~/${StagingDir}/.env; } && echo DOCKER_GID set"
    Invoke-WithRetry -OperationName "Set DOCKER_GID" -Command "ssh $SshOptionsStr -p $SshPort ${SshUser}@${SshHost} `"$gidCmd`""

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
# Etape 8.4: Fichier de secrets du demonstrateur
# ============================================================================
# AVANT le durcissement (8.5) et AVANT le deploiement (9), et l'ordre n'est
# pas cosmetique : `deploy.sh` RENOMME le repertoire de staging en repertoire
# vivant. Pose apres, ce fichier atterrissait dans un chemin que la bascule
# venait de consommer -- scp echouait, l'avertissement passait inapercu, et
# `task demo:prod:up` refusait ensuite sur un fichier absent (mesure
# 2026-08-07 : ~/lia sans .env.demo-instance.prod apres un deploiement vert).
# Pose avant, la bascule l'emporte avec le reste, et le chmod 600 de l'etape
# 8.5 -- qui le nommait deja -- fait enfin son travail.
# ============================================================================
# Il n'entre pas dans le bundle PROD : il porte des identifiants DIFFERENTS de
# ceux de la production (ses propres cles fournisseur, son propre relais, le
# jeton du tunnel). Il est donc pousse ici, directement, sur le canal SSH deja
# chiffre — puis mis en 600 dans la foulee.
#
# Automatique parce que l'alternative ne marchait pas : la premiere version
# demandait a l'operateur de le poser a la main, et `task demo:prod:up` echouait
# sur un hote ou il manquait (mesure 2026-08-07). Un prerequis qu'on documente
# est un prerequis qu'on oublie.
#
# Non bloquant : une installation qui ne veut pas de demonstrateur est un cas
# legitime, et le fichier est simplement absent du poste.
Write-Step "Fichier de secrets du demonstrateur..."

$demoEnv = Join-Path $ProjectRoot ".env.demo-instance.prod"
if (-not (Test-Path $demoEnv)) {
    Write-Info "Absent du poste - le demonstrateur ne sera pas configure (ignore)."
} elseif ($DryRun) {
    Write-Info "[DRY RUN] scp .env.demo-instance.prod + chmod 600"
} else {
    $demoContent = Get-Content $demoEnv -Raw
    $refus = $null
    if ($demoContent -match '(?m)^(FRONTEND_URL|APP_URL_SERVER)=.*localhost') {
        $refus = "il pointe sur localhost : forme de DEVELOPPEMENT"
    }
    foreach ($key in @("DEMO_INSTANCE_TUNNEL_TOKEN", "DEEPSEEK_API_KEY", "SECRET_KEY", "FERNET_KEY")) {
        if ($demoContent -notmatch "(?m)^$key=.") { $refus = "$key est vide" }
    }
    if ($refus) {
        Write-Warning "Fichier du demonstrateur non envoye : $refus"
        Write-Info "Le corriger puis rejouer: task demo:prod:push-env"
    } else {
        & scp -P $SshPort $demoEnv "${sshTarget}:~/$StagingDir/.env.demo-instance.prod"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "scp du fichier du demonstrateur a echoue ($LASTEXITCODE)"
        } else {
            $chmodCmd = "chmod 600 ~/$StagingDir/.env.demo-instance.prod && stat -c 'PERMS_DEMO=%a' ~/$StagingDir/.env.demo-instance.prod"
            $fullChmod = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$chmodCmd`""
            $out = if (($null -eq $IsWindows) -or $IsWindows) { cmd /c $fullChmod } else { sh -c $fullChmod }
            if ("$out" -match "PERMS_DEMO=600") {
                Write-Success "Fichier du demonstrateur en place (600)"
            } else {
                Write-Err "Permissions du fichier du demonstrateur non confirmees: $out"
                exit 1
            }
        }
    }
}

# ============================================================================
# Etape 8.5: Durcissement des permissions des secrets (SEC-013)
# ============================================================================
# The demonstrator's own env file is hardened too when it is there. It is NOT
# shipped by a deployment — the operator places it, because it carries a
# DIFFERENT set of provider credentials — but it holds the demonstrator's
# provider keys, its smarthost password and the Cloudflare tunnel token, and a
# file created by hand lands 0644 under the usual umask. `task demo:prod:up`
# refuses to start on a loose one; this makes the deployment fix it instead of
# only reporting it.
#
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
    #
    # Written with `printf` + `stat` rather than `echo VAR=$(stat ...)` on
    # purpose. `Invoke-WithRetry` hands this string to the platform shell —
    # `cmd /c` on Windows, `sh -c` on Linux — and only the second one expands
    # `$(...)`. A command substitution here would therefore be evaluated LOCALLY
    # on Linux, against a filesystem where none of these paths exist, and the
    # remote shell would receive a literal `PERMS_ENV=missing`: the hardening
    # check would fail every deployment from a Unix host while passing from
    # Windows. Nothing below is expanded by either shell.
    $statEnv = "printf 'PERMS_ENV='; stat -c '%a' ~/$StagingDir/.env 2>/dev/null || echo missing"
    $statDir = "printf 'PERMS_DIR='; stat -c '%a' ~/$StagingDir 2>/dev/null || echo missing"
    $hardenCmd = "chmod 700 ~/$StagingDir 2>/dev/null; [ -f ~/$StagingDir/.env ] && chmod 600 ~/$StagingDir/.env; [ -f ~/$StagingDir/.env.demo-instance.prod ] && chmod 600 ~/$StagingDir/.env.demo-instance.prod; [ -d ~/.claude ] && chmod 700 ~/.claude; [ -f ~/.claude/.credentials.json ] && chmod 600 ~/.claude/.credentials.json; [ -d ~/$StagingDir/apps/api/config ] && chmod 700 ~/$StagingDir/apps/api/config; find ~/$StagingDir/apps/api/config -maxdepth 1 -type f -name '*.json' -exec chmod 600 {} + 2>/dev/null; $statEnv; $statDir"
    $hardenSsh = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$hardenCmd`""
    $hardenResult = Invoke-WithRetry -Command $hardenSsh -OperationName "Harden secret permissions" -MaxAttempts 2

    $hardenText = ($hardenResult | Out-String)
    $envMode = if ($hardenText -match 'PERMS_ENV=(\S+)') { $Matches[1] } else { "unknown" }
    $dirMode = if ($hardenText -match 'PERMS_DIR=(\S+)') { $Matches[1] } else { "unknown" }

    if ($envMode -ne "600" -or $dirMode -ne "700") {
        Write-Err "Durcissement des permissions ECHOUE (SEC-013)"
        Write-Err "  ~/$StagingDir/.env attendu 600, obtenu: $envMode"
        Write-Err "  ~/$StagingDir    attendu 700, obtenu: $dirMode"
        Write-Err "Le .env de production contient tous les secrets applicatifs."
        Write-Err "Deploiement interrompu avant 'docker compose up'."
        exit 1
    }
    Write-Success "Permissions secrets durcies et verifiees (.env $envMode, dossier $dirMode)"
} else {
    Write-Info "[DRY RUN] ssh chmod 700 ~/$StagingDir ; chmod 600 ~/$StagingDir/.env ; chmod 700 ~/.claude ; chmod 600 ~/.claude/.credentials.json ; chmod 700 apps/api/config ; chmod 600 apps/api/config/*.json"
}

# ============================================================================
# Etape 9: Execution du script de deploiement sur le serveur
# ============================================================================
# ADR-250: le travail est DETACHE, son verdict est LU.
#
# Il tenait auparavant dans une session ssh bloquante, si bien que la survie du
# deploiement dependait de la survie de la connexion -- et elle n'y survivait
# pas : mesure du 2026-08-29 sur l'hote reel, tuer le client fait mourir le
# script distant par SIGPIPE (exit 141) en ~6 s des qu'il ecrit sur le canal.
# Sur un des deux essais, aucun verdict n'a meme ete ecrit. Le meme travail
# lance detache survit a la destruction de tous les clients ssh et rend son
# code exact.
#
# Le pilote ne DEDUIT donc plus rien d'un code de transport : il scrute un
# fichier que le distant a ecrit. Un sondage qui echoue est reessaye, jamais
# converti en verdict -- une coupure pendant la scrutation ne dit rien du
# travail. Les six issues sont distinctes parce que la conduite a tenir l'est :
# `RemoteFailure` autorise a parler d'echec, `Interrupted` et `Unknown` non.
Write-Step "Execution du deploiement sur le serveur..."

$deployCmd = "chmod +x deploy.sh && ./deploy.sh"

Write-Info "Commande: cd ~/$StagingDir && $deployCmd"

if (-not $DryRun) {
    # La frontiere d'E/S, et rien d'autre : toute la machine a etats vit dans
    # la bibliotheque, ou elle se verifie sans reseau ni attente.
    #
    # La charge voyage encodee (elle traverse PowerShell, le reassemblage
    # d'arguments de ssh, puis le shell distant, et chacun revendique le
    # guillemet). La PHASE, elle, voyage en clair a cote : sans elle, la trace
    # du pilote et la table des processus de l'hote n'afficheraient qu'un bloc
    # de base64. `sh -s --` la depose en parametre positionnel, ou le corps ne
    # la lit pas -- elle n'est la que pour etre lisible.
    $sshArgList = @("-p", "$SshPort") + $SshOptionsStr.Split(' ') + @($sshTarget)
    $remoteExecutor = {
        param([string]$Payload, [string]$Phase)

        # Meme precaution que Invoke-WithRetry : ssh ecrit ses avertissements
        # sur stderr, qu'un $ErrorActionPreference a "Stop" transformerait en
        # exception sur une execution parfaitement normale.
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            $raw = & ssh @sshArgList "echo $Payload | base64 -d | sh -s -- lia-deploy-$Phase" 2>&1
            # $global: EST OBLIGATOIRE ICI. `GetNewClosure()` recopie dans la
            # portee de la closure toutes les variables visibles a sa creation,
            # $LASTEXITCODE compris ; la lecture nue rend alors la valeur GELEE
            # a ce moment-la, pas celle que ssh vient de poser. Mesure du
            # 2026-08-29 : lecture nue 0, lecture globale 255, pour le meme
            # appel. Le harnais l'a montre en silence -- un lancement dont la
            # connexion tombait etait rapporte comme reussi, ce qui est
            # exactement le verdict lu au mauvais endroit que tout ce chantier
            # supprime.
            $code = $global:LASTEXITCODE
        } finally {
            $ErrorActionPreference = $prevEap
        }
        return @{ ExitCode = $code; Output = ($raw | Out-String) }
    }.GetNewClosure()

    $outcome = Invoke-RemoteDetached -RemoteDir "~/$StagingDir" -Command $deployCmd `
        -RemoteExecutor $remoteExecutor `
        -PollIntervalSeconds $DeployPollSeconds -BudgetSeconds $DeployBudgetSeconds `
        -OnLogLine { param($line) Write-Info $line }

    # Les commandes qui permettent de trancher, factorisees : elles sont
    # imprimees sur les quatre chemins ou le pilote ne sait pas conclure.
    $inspectLines = @(
        "  ssh -p $SshPort $sshTarget `"cat $($outcome.LogPath)`"",
        "  ssh -p $SshPort $sshTarget `"cd $RemoteDir && docker compose -f docker-compose.prod.yml ps`"",
        "  ssh -p $SshPort $sshTarget `"cat $RemoteDir/release-manifest.json`""
    )
    function Write-Inspect {
        Write-Info ""
        Write-Info "Pour trancher :"
        foreach ($l in $inspectLines) { Write-Info $l }
    }

    switch ($outcome.Kind) {
        "Success" {
            Write-Success "Deploiement termine (execution $($outcome.RunId))"
        }
        "RemoteFailure" {
            # Le seul etat ou l'on peut parler d'echec : le code a ete ECRIT
            # par le distant, il ne vient pas du transport.
            Write-Err "Echec du deploiement (exit code: $($outcome.ExitCode))"
            Write-Info "Journal distant : $($outcome.LogPath)"
            exit 1
        }
        "Busy" {
            # Un deploiement etait deja en vol : celui-ci n'a pas eu lieu. Ce
            # n'est pas un echec, et surtout il ne faut pas relancer -- l'etape
            # 7 effacerait le staging sous le build de l'autre.
            Write-Warning "Un deploiement est deja en cours sur le serveur : celui-ci n'a PAS eu lieu."
            Write-Info "Rien n'a ete modifie a distance par cette execution."
            Write-Info "Attendre la fin du deploiement en vol avant de relancer."
            Write-Inspect
            exit 1
        }
        "LaunchFailed" {
            if ((Get-RemoteExitVerdict -ExitCode $outcome.ExitCode) -eq "ContactLost") {
                # 255 au LANCEMENT : la connexion a pu tomber apres que l'hote
                # ait deja forke le travail. On ne peut donc pas dire que rien
                # n'a demarre -- c'est exactement la conclusion pressee que ce
                # dispositif existe pour supprimer. La prose vient de la
                # bibliotheque : les deux pilotes doivent dire la MEME chose
                # d'une coupure. Premiere ligne en avertissement (elle porte le
                # fait), le reste en information -- la palette est stricte.
                $explanation = Get-ContactLostExplanation
                Write-Warning $explanation[0]
                foreach ($line in $explanation[1..($explanation.Count - 1)]) { Write-Info $line }
                Write-Inspect
                exit 1
            }
            # Tout autre code vient de la commande de lancement elle-meme, qui
            # est synchrone : la, rien n'a demarre a distance et relancer est
            # sans danger.
            Write-Err "Lancement du deploiement impossible (exit code: $($outcome.ExitCode))"
            Write-Info "Rien n'a demarre sur le serveur : l'operation est relancable telle quelle."
            exit 1
        }
        "Interrupted" {
            # Le travail s'est arrete en chemin sans ecrire de verdict : OOM,
            # redemarrage, signal. Ni succes ni echec -- et surtout pas un
            # echec du deploiement, qui affirmerait ce que personne n'a mesure.
            Write-Warning "ADR-250: le deploiement distant s'est interrompu sans rendre de verdict."
            Write-Info "Le verdict est INCONNU : le processus a disparu avant d'ecrire son code de"
            Write-Info "sortie. Ce n'est pas un echec constate, c'est une absence de constat."
            Write-Info ""
            Write-Info "NE PAS relancer le deploiement tant que le doute persiste : il"
            Write-Info "effacerait le repertoire de staging sous un build en vol."
            Write-Inspect
            exit 1
        }
        default {
            # "Unknown" : le budget de scrutation est epuise alors que le
            # travail tournait encore. On a cesse de regarder, il ne s'est rien
            # passe de mal. Le budget est un parametre, precisement pour que
            # cette prudence puisse etre allongee plutot qu'apprise par coeur.
            Write-Warning "ADR-250: budget de scrutation epuise ($DeployBudgetSeconds s) -- le deploiement tourne ENCORE."
            Write-Info "Le verdict est INCONNU : le travail distant n'a pas echoue, il n'a pas fini."
            Write-Info "Relancer avec -DeployBudgetSeconds superieur pour l'attendre plus longtemps."
            Write-Info ""
            Write-Info "NE PAS relancer le deploiement : il effacerait le repertoire de staging"
            Write-Info "sous un build encore en vol."
            Write-Inspect
            exit 1
        }
    }
} else {
    Write-Info "[DRY RUN] ssh -p $SshPort $SshOptionsStr $sshTarget <charge detachee ADR-250> ; cd ~/$StagingDir && $deployCmd"
}

# ============================================================================
# Etape 9bis: Isolation de l'hote vis-a-vis du demonstrateur
# ============================================================================
# Les reseaux `internal` de Docker n'empechent PAS un conteneur de joindre la
# passerelle du bridge, et cette passerelle EST l'hote : sur ce Pi cela signifie
# sshd, et de la toute la pile de production (mesure le 2026-08-07 avec des
# conteneurs jetables). Le script pose des regles iptables idempotentes.
#
# Il tourne a CHAQUE deploiement parce qu'un reboot de l'hote les perd si la
# distribution ne les persiste pas, et parce qu'une regle qu'on oublie de
# reposer est une regle qui n'existe pas.
#
# Non bloquant, et ce n'est PAS ici que la protection se pose : les regles
# visent les SOUS-RESEAUX du demonstrateur, qui n'existent pas tant que ses
# reseaux n'existent pas. Un deploiement livre l'instance sans la demarrer,
# donc l'absence de reseaux est le cas NOMINAL et ce pas ne fait rien.
#
# La pose reelle est dans `task demo:prod:up`, juste apres le demarrage, et
# elle y est MESUREE. Ce pas-ci ne sert qu'a une chose : reposer les regles
# apres un redemarrage de l'hote, quand l'instance tourne deja et que la
# distribution n'a pas persiste iptables.
Write-Step "Isolation de l'hote vis-a-vis du demonstrateur (iptables, idempotent)..."

if (-not $DryRun) {
    $hardenCmd = "cd ~/$RemoteDir && sh scripts/deploy/harden-demo-host.sh"
    $fullHardenCmd = "ssh -p $SshPort $SshOptionsStr $sshTarget `"$hardenCmd`""
    if (($null -eq $IsWindows) -or $IsWindows) {
        cmd /c $fullHardenCmd
    } else {
        sh -c $fullHardenCmd
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Regles d'isolation non posees (le demonstrateur ne tourne probablement pas)."
        Write-Info "Rejouer apres 'task demo:prod:up' : task demo:prod:harden"
    } else {
        Write-Success "Isolation hote/demonstrateur en place"
    }
} else {
    Write-Info "[DRY RUN] ssh ... 'sh scripts/deploy/harden-demo-host.sh'"
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

} finally {
    # ========================================================================
    # SEC-040: ne rien laisser derriere soi, quel que soit le chemin de sortie
    # ========================================================================
    # Ne s'applique JAMAIS en simulation : `-DryRun` doit laisser un PROD/
    # preexistant strictement intact, y compris ses cles (contrat teste).
    #
    # Sur le chemin nominal, l'etape 10 a deja supprime tout le bundle : il n'y
    # a plus rien a retirer et ce bloc reste muet. Il ne parle que lorsqu'il a
    # reellement quelque chose a nettoyer, c'est-a-dire sur un echec -- ou sur
    # ce faux echec qu'est une session SSH reinitialisee en fin de deploiement.
    if (-not $DryRun) {
        Remove-SensitiveFromProd -Dir $ProdDir | Out-Null
    }
}
