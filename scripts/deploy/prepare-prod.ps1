# ============================================================================
# Script de préparation des livrables de production
# Usage: .\scripts\prepare-prod.ps1
# ============================================================================

param(
    [string]$OutputDir = ".\PROD",
    [switch]$Clean = $false
)

$ErrorActionPreference = "Stop"

# Déterminer le répertoire source (racine du projet)
# Script est dans scripts/deploy/, donc on remonte de 2 niveaux
if ($PSScriptRoot) {
    $SourceDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
} else {
    $SourceDir = Get-Location
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Preparation des livrables PRODUCTION" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Nettoyer le répertoire de sortie si demandé
if ($Clean -and (Test-Path $OutputDir)) {
    Write-Host "[CLEAN] Suppression de $OutputDir..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $OutputDir
}

# Créer le répertoire de sortie
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

Write-Host "[INFO] Source: $SourceDir" -ForegroundColor Gray
Write-Host "[INFO] Destination: $OutputDir" -ForegroundColor Gray
Write-Host ""

# ============================================================================
# Fichiers racine
# ============================================================================
Write-Host "[1/9] Copie des fichiers racine..." -ForegroundColor Green

# Chemins racine embarques dans le dossier PROD, qui est le CONTEXTE de build
# de l'image web. La CI construit depuis le depot entier et ne voit donc jamais
# un oubli ici : seule cette liste decide de ce que `docker build` trouvera.
#
# `Required` = son absence casse le build. Un simple avertissement jaune est
# precisement ce qui a laisse passer `patches/` (ADR-157) : la preparation
# reussissait, et l'echec ne survenait que dix minutes plus tard, sur le Pi,
# dans `COPY patches ./patches`. La garde
# `apps/api/tests/unit/test_prepare_prod_build_context_guard.py` derive cette
# liste des instructions COPY du Dockerfile de production.
$rootPaths = @(
    @{ Path = ".npmrc";                  Required = $true;  Recurse = $false },
    @{ Path = "package.json";            Required = $true;  Recurse = $false },
    @{ Path = "pnpm-workspace.yaml";     Required = $true;  Recurse = $false },
    @{ Path = "pnpm-lock.yaml";          Required = $true;  Recurse = $false },
    # `pnpm.patchedDependencies` pointe dessus : sans ce repertoire,
    # `pnpm install --frozen-lockfile` echoue d'emblee.
    @{ Path = "patches";                 Required = $true;  Recurse = $true  },
    @{ Path = "docker-compose.prod.yml"; Required = $true;  Recurse = $false },
    @{ Path = ".sops.yaml";              Required = $false; Recurse = $false }
)

$missingRequired = @()
foreach ($entry in $rootPaths) {
    $src = Join-Path $SourceDir $entry.Path
    if (Test-Path $src) {
        if ($entry.Recurse) {
            Copy-Item $src -Destination $OutputDir -Recurse -Force
        } else {
            Copy-Item $src -Destination $OutputDir
        }
        Write-Host "  + $($entry.Path)" -ForegroundColor DarkGray
    } elseif ($entry.Required) {
        $missingRequired += $entry.Path
        Write-Host "  X $($entry.Path) (REQUIS, introuvable)" -ForegroundColor Red
    } else {
        Write-Host "  ! $($entry.Path) (optionnel, non trouve)" -ForegroundColor Yellow
    }
}

if ($missingRequired.Count -gt 0) {
    throw "Chemins racine requis absents de la source : $($missingRequired -join ', '). " +
          "Le build Docker echouerait sur le Pi ; la preparation s'arrete ici."
}

# ============================================================================
# Apps API
# ============================================================================
Write-Host "[2/9] Copie de apps/api..." -ForegroundColor Green

$apiDir = Join-Path $OutputDir "apps\api"
New-Item -ItemType Directory -Path $apiDir -Force | Out-Null

# Fichiers API à copier
$apiFiles = @(
    "Dockerfile.prod",
    "docker-entrypoint.sh",
    "requirements.txt",
    "requirements.lock.txt",
    "alembic.ini"
)

foreach ($file in $apiFiles) {
    $src = Join-Path $SourceDir "apps\api\$file"
    if (Test-Path $src) {
        Copy-Item $src -Destination $apiDir
        Write-Host "  + apps/api/$file" -ForegroundColor DarkGray
    }
}

# Copier le code source API (src/)
$apiSrcDir = Join-Path $SourceDir "apps\api\src"
if (Test-Path $apiSrcDir) {
    Copy-Item $apiSrcDir -Destination $apiDir -Recurse
    Write-Host "  + apps/api/src/" -ForegroundColor DarkGray
}

# Copier les migrations Alembic
$alembicDir = Join-Path $SourceDir "apps\api\alembic"
if (Test-Path $alembicDir) {
    Copy-Item $alembicDir -Destination $apiDir -Recurse
    Write-Host "  + apps/api/alembic/" -ForegroundColor DarkGray
}

# Copier les scripts operationnels (create_admin, create_grafana_reader — le
# runbook prod du role Grafana lecture seule s'execute DANS le conteneur api :
# sans cette copie, `python -m scripts.data.create_grafana_reader` echoue en
# ModuleNotFoundError sur le Pi, constate au deploiement v1.26.2).
$apiScriptsDir = Join-Path $SourceDir "apps\api\scripts"
if (Test-Path $apiScriptsDir) {
    Copy-Item $apiScriptsDir -Destination $apiDir -Recurse
    Write-Host "  + apps/api/scripts/" -ForegroundColor DarkGray
}

# Copier le répertoire config (Firebase service account, etc.)
$configDir = Join-Path $SourceDir "apps\api\config"
if (Test-Path $configDir) {
    Copy-Item $configDir -Destination $apiDir -Recurse
    Write-Host "  + apps/api/config/" -ForegroundColor DarkGray
} else {
    Write-Host "  ! apps/api/config/ (non trouve - Firebase FCM ne fonctionnera pas)" -ForegroundColor Yellow
}

# ============================================================================
# Apps Web
# ============================================================================
Write-Host "[3/9] Copie de apps/web..." -ForegroundColor Green

$webDir = Join-Path $OutputDir "apps\web"
New-Item -ItemType Directory -Path $webDir -Force | Out-Null

# Fichiers Web à copier
$webFiles = @(
    "Dockerfile.prod",
    "package.json",
    "next.config.ts",
    "tsconfig.json",
    "postcss.config.mjs",
    "tailwind.config.ts",
    "components.json"
)

foreach ($file in $webFiles) {
    $src = Join-Path $SourceDir "apps\web\$file"
    if (Test-Path $src) {
        Copy-Item $src -Destination $webDir
        Write-Host "  + apps/web/$file" -ForegroundColor DarkGray
    }
}

# Copier les dossiers source Web
$webDirs = @("src", "public", "locales")
foreach ($dir in $webDirs) {
    $src = Join-Path $SourceDir "apps\web\$dir"
    if (Test-Path $src) {
        Copy-Item $src -Destination $webDir -Recurse
        Write-Host "  + apps/web/$dir/" -ForegroundColor DarkGray
    }
}

# ============================================================================
# Infrastructure
# ============================================================================
Write-Host "[4/9] Copie de infrastructure..." -ForegroundColor Green

$infraDir = Join-Path $OutputDir "infrastructure"
New-Item -ItemType Directory -Path $infraDir -Force | Out-Null

# Sous-dossiers infrastructure nécessaires
$infraDirs = @(
    "docker",
    "logwatch",
    "observability",
    "pgadmin",
    "database",
    "claude-cli"
)

foreach ($dir in $infraDirs) {
    $src = Join-Path $SourceDir "infrastructure\$dir"
    if (Test-Path $src) {
        Copy-Item $src -Destination $infraDir -Recurse
        Write-Host "  + infrastructure/$dir/" -ForegroundColor DarkGray
    }
}

# ============================================================================
# Clés de chiffrement (optionnel)
# ============================================================================
Write-Host "[5/9] Copie des cles de chiffrement..." -ForegroundColor Green

$keysDir = Join-Path $OutputDir "keys"
New-Item -ItemType Directory -Path $keysDir -Force | Out-Null

$keyFile = Join-Path $SourceDir "keys\age-key-prod.txt"
if (Test-Path $keyFile) {
    Copy-Item $keyFile -Destination $keysDir
    Write-Host "  + keys/age-key-prod.txt" -ForegroundColor DarkGray
} else {
    Write-Host "  ! keys/age-key-prod.txt (non trouve)" -ForegroundColor Yellow
}

# ============================================================================
# Fichier .env.prod ou .env.prod.encrypted
# ============================================================================
Write-Host "[6/9] Copie des fichiers d'environnement..." -ForegroundColor Green

$envFiles = @(".env.prod", ".env.prod.encrypted")
foreach ($file in $envFiles) {
    $src = Join-Path $SourceDir $file
    if (Test-Path $src) {
        Copy-Item $src -Destination $OutputDir
        Write-Host "  + $file" -ForegroundColor DarkGray
    }
}

# ============================================================================
# Skills système (livrés avec l'application, read-only en prod)
# ============================================================================
Write-Host "[7/9] Copie des skills systeme..." -ForegroundColor Green

$skillsSystemSrc = Join-Path $SourceDir "data\skills\system"
if (Test-Path $skillsSystemSrc) {
    $skillsDataDir = Join-Path $OutputDir "data\skills"
    New-Item -ItemType Directory -Path $skillsDataDir -Force | Out-Null
    Copy-Item $skillsSystemSrc -Destination $skillsDataDir -Recurse
    $skillCount = (Get-ChildItem $skillsSystemSrc -Directory).Count
    Write-Host "  + data/skills/system/ ($skillCount skills)" -ForegroundColor DarkGray
} else {
    Write-Host "  ! data/skills/system/ (non trouve - skills systeme indisponibles en prod)" -ForegroundColor Yellow
}

# ============================================================================
# Knowledge files for System RAG (FAQ) — bind-mounted read-only in prod
# ============================================================================
Write-Host "[8/9] Copie des fichiers knowledge (System RAG)..." -ForegroundColor Green

$knowledgeSrc = Join-Path $SourceDir "docs\knowledge"
if (Test-Path $knowledgeSrc) {
    $knowledgeDir = Join-Path $OutputDir "docs\knowledge"
    New-Item -ItemType Directory -Path $knowledgeDir -Force | Out-Null
    Copy-Item "$knowledgeSrc\*" -Destination $knowledgeDir -Recurse
    $fileCount = (Get-ChildItem $knowledgeSrc -File -Filter "*.md").Count
    Write-Host "  + docs/knowledge/ ($fileCount files)" -ForegroundColor DarkGray
} else {
    Write-Host "  ! docs/knowledge/ (non trouve - System RAG FAQ indisponible en prod)" -ForegroundColor Yellow
}

# ============================================================================
# Création du script de déploiement
# ============================================================================
Write-Host "[9/9] Creation du script de deploiement..." -ForegroundColor Green

$deployScript = @'
#!/bin/bash
# ============================================================================
# Script de deploiement LIA - Raspberry Pi
# ============================================================================

set -e

# Build provenance computed at prepare time (F030/F008): version, commit SHA and
# build date. Exported so `docker compose build` injects them (build args) and
# the release manifest records exactly what was deployed.
[ -f "provenance.env" ] && . ./provenance.env

echo "============================================"
echo "  Deploiement LIA - Production"
echo "============================================"

# Verifier si .env existe, sinon decrypter
if [ ! -f ".env" ]; then
    if [ -f ".env.prod.encrypted" ] && [ -f "keys/age-key-prod.txt" ]; then
        echo "[1/6] Decryptage des secrets..."
        export SOPS_AGE_KEY_FILE=./keys/age-key-prod.txt
        sops --decrypt --input-type dotenv --output-type dotenv .env.prod.encrypted > .env
        echo "  -> .env cree depuis .env.prod.encrypted"
    elif [ -f ".env.prod" ]; then
        echo "[1/6] Copie de .env.prod vers .env..."
        cp .env.prod .env
    else
        echo "ERREUR: Aucun fichier .env trouve!"
        exit 1
    fi
else
    echo "[1/6] .env existe deja"
fi

# Fixer les permissions des scripts (CRLF -> LF deja gere dans Dockerfile)
echo "[2/6] Verification des permissions..."
chmod +x apps/api/docker-entrypoint.sh 2>/dev/null || true

# Repertoire des backups PostgreSQL (ADR-109) : cree AVANT le up pour eviter
# qu'un bind mount cree par Docker (root, 755) n'expose les dumps.
echo "[3/6] Preparation du repertoire de backups PostgreSQL..."
BACKUP_DIR=$(grep -E '^POSTGRES_BACKUP_HOST_DIR=' .env | tail -1 | cut -d= -f2- | awk '{print $1}')
BACKUP_DIR=${BACKUP_DIR:-./backups/postgres}
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
echo "  -> $BACKUP_DIR (chmod 700)"

# Install/update logwatch configuration
echo "[4/6] Installation de la configuration logwatch..."
if [ -d "infrastructure/logwatch" ]; then
    # Install logwatch if not present
    if ! command -v logwatch &> /dev/null; then
        echo "  -> Installation de logwatch..."
        sudo apt-get install -y logwatch > /dev/null 2>&1
    fi

    # Render logwatch.conf from template, substituting mail addresses from .env
    # (keeps personal addresses out of the public repo — see .env LOGWATCH_*).
    LOGWATCH_MAILTO=$(grep -E '^LOGWATCH_MAILTO=' .env | tail -1 | cut -d= -f2- | awk '{print $1}')
    LOGWATCH_MAILFROM=$(grep -E '^LOGWATCH_MAILFROM=' .env | tail -1 | cut -d= -f2- | awk '{print $1}')
    if [ -z "$LOGWATCH_MAILTO" ] || [ -z "$LOGWATCH_MAILFROM" ]; then
        echo "  -> WARN: LOGWATCH_MAILTO/LOGWATCH_MAILFROM unset in .env — keeping existing logwatch.conf"
    else
        sed -e "s|\${LOGWATCH_MAILTO}|${LOGWATCH_MAILTO}|g" \
            -e "s|\${LOGWATCH_MAILFROM}|${LOGWATCH_MAILFROM}|g" \
            infrastructure/logwatch/conf/logwatch.conf.template \
            | sudo tee /etc/logwatch/conf/logwatch.conf > /dev/null
    fi

    # Deploy logfile overrides
    sudo mkdir -p /etc/logwatch/conf/logfiles
    sudo cp infrastructure/logwatch/conf/logfiles/*.conf /etc/logwatch/conf/logfiles/

    # Deploy service configs
    sudo mkdir -p /etc/logwatch/conf/services
    sudo cp infrastructure/logwatch/conf/services/*.conf /etc/logwatch/conf/services/

    # Deploy custom scripts
    sudo mkdir -p /etc/logwatch/scripts/services
    sudo cp infrastructure/logwatch/scripts/services/* /etc/logwatch/scripts/services/
    sudo chmod +x /etc/logwatch/scripts/services/*

    # Deploy custom cron script (MIME-encoded HTML to avoid line-length SMTP errors)
    if [ -f "infrastructure/logwatch/cron/00logwatch" ]; then
        sudo cp infrastructure/logwatch/cron/00logwatch /etc/cron.daily/00logwatch
        sudo chmod +x /etc/cron.daily/00logwatch
        echo "  -> Cron custom 00logwatch deploye (MIME base64)"
    fi

    echo "  -> Logwatch configure (configs + scripts custom deployes)"
else
    echo "  -> infrastructure/logwatch/ absent, skip"
fi

# Readiness gate + operational rollback + release manifest (F008). Sourcing the
# shipped library keeps the tested logic (scripts/deploy/lib) and the deploy in
# sync. Guarded so a missing lib degrades to the inline readiness poll below.
[ -f "deploy_readiness_gate.sh" ] && . ./deploy_readiness_gate.sh

# Capture the CURRENT images as a rollback point BEFORE the build overwrites them.
command -v capture_rollback_point >/dev/null 2>&1 && capture_rollback_point

# Build des images
echo "[5/6] Build des images Docker..."
docker compose -f docker-compose.prod.yml build

# Demarrage des services (force-recreate pour recharger les volumes).
# --wait bloque jusqu'a ce que les healthchecks compose passent (ou echoue).
echo "[6/6] Demarrage des services..."
docker compose -f docker-compose.prod.yml up -d --force-recreate --wait

# Readiness gate with operational rollback + release manifest (F008). Prefer the
# shipped library (polls /ready; on failure auto-rolls back to the previous
# image and re-validates; on success writes release-manifest.json). Fall back to
# a plain readiness poll only if the lib was not shipped.
if command -v run_readiness_gate >/dev/null 2>&1; then
    run_readiness_gate || exit 1
else
    echo "  -> Verification de la readiness (/ready) [fallback inline]..."
    ready=0
    for i in $(seq 1 30); do
        if curl -fsk https://localhost:8000/ready >/dev/null 2>&1 || curl -fs http://localhost:8000/ready >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 2
    done
    if [ "$ready" -ne 1 ]; then
        echo "ERREUR: l'API n'est pas prete (/ready) apres 60s -- deploiement en ECHEC." >&2
        echo "    docker compose -f docker-compose.prod.yml logs --tail=120 api" >&2
        exit 1
    fi
    echo "  -> API prete (/ready OK)"
fi

echo ""
echo "============================================"
echo "  Deploiement termine (readiness verifiee)!"
echo "============================================"
echo ""
echo "Services disponibles:"
echo "  - API:      http://localhost:8000"
echo "  - Web:      http://localhost:3000"
echo "  - Grafana:  http://localhost:3001"
echo "  - Langfuse: http://localhost:3002"
echo ""
echo "Commandes utiles:"
echo "  docker compose -f docker-compose.prod.yml logs -f"
echo "  docker compose -f docker-compose.prod.yml ps"
echo "  docker compose -f docker-compose.prod.yml down"
'@

$deployScriptPath = Join-Path $OutputDir "deploy.sh"
$deployScript | Out-File -FilePath $deployScriptPath -Encoding utf8 -NoNewline
# Convertir CRLF en LF pour Linux
(Get-Content $deployScriptPath -Raw) -replace "`r`n", "`n" | Set-Content $deployScriptPath -NoNewline
Write-Host "  + deploy.sh" -ForegroundColor DarkGray

# Build provenance (F030/F008): capture version + commit SHA + build date at
# prepare time and ship them so `docker compose build` injects them and the
# release manifest records exactly what was deployed.
$gitSha = (& git rev-parse HEAD 2>$null)
if (-not $gitSha) { $gitSha = "unknown" }
$buildDate = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$appVersion = "unknown"
foreach ($pkgRel in @("package.json", "apps/web/package.json")) {
    $pkg = Join-Path $SourceDir $pkgRel
    if ($appVersion -eq "unknown" -and (Test-Path $pkg)) {
        try { $appVersion = (Get-Content $pkg -Raw | ConvertFrom-Json).version } catch {}
    }
}
$provenancePath = Join-Path $OutputDir "provenance.env"
"export APP_VERSION=$appVersion`nexport GIT_COMMIT_SHA=$gitSha`nexport BUILD_DATE=$buildDate`n" |
    Out-File -FilePath $provenancePath -Encoding utf8 -NoNewline
(Get-Content $provenancePath -Raw) -replace "`r`n", "`n" | Set-Content $provenancePath -NoNewline
$shaShort = if ($gitSha.Length -ge 12) { $gitSha.Substring(0, 12) } else { $gitSha }
Write-Host "  + provenance.env ($appVersion / $shaShort)" -ForegroundColor DarkGray

# Ship the tested readiness-gate library (F008: release manifest + rollback).
$gateLib = Join-Path $PSScriptRoot "lib/deploy_readiness_gate.sh"
if (Test-Path $gateLib) {
    $gateDest = Join-Path $OutputDir "deploy_readiness_gate.sh"
    Copy-Item $gateLib -Destination $gateDest
    (Get-Content $gateDest -Raw) -replace "`r`n", "`n" | Set-Content $gateDest -NoNewline
    Write-Host "  + deploy_readiness_gate.sh" -ForegroundColor DarkGray
}

# Belt-and-braces: every shell script shipped in the bundle must be LF — CRLF
# breaks bash/sh on the production host, and Windows checkouts can drift
# (core.autocrlf). Catches any future generated/copied script the per-file
# normalizations above would miss.
Get-ChildItem -Path $OutputDir -Recurse -Filter *.sh | ForEach-Object {
    $raw = Get-Content -LiteralPath $_.FullName -Raw
    if ($raw -match "`r") {
        ($raw -replace "`r`n", "`n") | Set-Content -LiteralPath $_.FullName -NoNewline
        Write-Host "  ~ normalized to LF: $($_.FullName)" -ForegroundColor DarkGray
    }
}

# ============================================================================
# Résumé
# ============================================================================
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Preparation terminee!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Calculer la taille
$size = (Get-ChildItem $OutputDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "Repertoire: $OutputDir" -ForegroundColor White
Write-Host "Taille: $([math]::Round($size, 2)) MB" -ForegroundColor White
Write-Host ""
Write-Host "Pour deployer sur le Raspberry Pi:" -ForegroundColor Yellow
Write-Host "  1. Copier le dossier PROD sur le Raspberry" -ForegroundColor Gray
Write-Host "  2. cd PROD && chmod +x deploy.sh && ./deploy.sh" -ForegroundColor Gray
Write-Host ""
