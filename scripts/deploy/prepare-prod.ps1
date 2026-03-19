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
Write-Host "[1/8] Copie des fichiers racine..." -ForegroundColor Green

$rootFiles = @(
    ".npmrc",
    "package.json",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    "docker-compose.prod.yml",
    ".sops.yaml"
)

foreach ($file in $rootFiles) {
    $src = Join-Path $SourceDir $file
    if (Test-Path $src) {
        Copy-Item $src -Destination $OutputDir
        Write-Host "  + $file" -ForegroundColor DarkGray
    } else {
        Write-Host "  ! $file (non trouve)" -ForegroundColor Yellow
    }
}

# ============================================================================
# Apps API
# ============================================================================
Write-Host "[2/8] Copie de apps/api..." -ForegroundColor Green

$apiDir = Join-Path $OutputDir "apps\api"
New-Item -ItemType Directory -Path $apiDir -Force | Out-Null

# Fichiers API à copier
$apiFiles = @(
    "Dockerfile.prod",
    "docker-entrypoint.sh",
    "requirements.txt",
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
Write-Host "[3/8] Copie de apps/web..." -ForegroundColor Green

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
Write-Host "[4/8] Copie de infrastructure..." -ForegroundColor Green

$infraDir = Join-Path $OutputDir "infrastructure"
New-Item -ItemType Directory -Path $infraDir -Force | Out-Null

# Sous-dossiers infrastructure nécessaires
$infraDirs = @(
    "docker",
    "logwatch",
    "observability",
    "pgadmin",
    "database"
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
Write-Host "[5/8] Copie des cles de chiffrement..." -ForegroundColor Green

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
Write-Host "[6/8] Copie des fichiers d'environnement..." -ForegroundColor Green

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
Write-Host "[7/8] Copie des skills systeme..." -ForegroundColor Green

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
# Création du script de déploiement
# ============================================================================
Write-Host "[8/8] Creation du script de deploiement..." -ForegroundColor Green

$deployScript = @'
#!/bin/bash
# ============================================================================
# Script de deploiement LIA - Raspberry Pi
# ============================================================================

set -e

echo "============================================"
echo "  Deploiement LIA - Production"
echo "============================================"

# Verifier si .env existe, sinon decrypter
if [ ! -f ".env" ]; then
    if [ -f ".env.prod.encrypted" ] && [ -f "keys/age-key-prod.txt" ]; then
        echo "[1/5] Decryptage des secrets..."
        export SOPS_AGE_KEY_FILE=./keys/age-key-prod.txt
        sops --decrypt --input-type dotenv --output-type dotenv .env.prod.encrypted > .env
        echo "  -> .env cree depuis .env.prod.encrypted"
    elif [ -f ".env.prod" ]; then
        echo "[1/5] Copie de .env.prod vers .env..."
        cp .env.prod .env
    else
        echo "ERREUR: Aucun fichier .env trouve!"
        exit 1
    fi
else
    echo "[1/5] .env existe deja"
fi

# Fixer les permissions des scripts (CRLF -> LF deja gere dans Dockerfile)
echo "[2/5] Verification des permissions..."
chmod +x apps/api/docker-entrypoint.sh 2>/dev/null || true

# Install/update logwatch configuration
echo "[3/5] Installation de la configuration logwatch..."
if [ -d "infrastructure/logwatch" ]; then
    # Install logwatch if not present
    if ! command -v logwatch &> /dev/null; then
        echo "  -> Installation de logwatch..."
        sudo apt-get install -y logwatch > /dev/null 2>&1
    fi

    # Deploy configuration files
    sudo cp infrastructure/logwatch/conf/logwatch.conf /etc/logwatch/conf/logwatch.conf

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

    echo "  -> Logwatch configure (configs + scripts custom deployes)"
else
    echo "  -> infrastructure/logwatch/ absent, skip"
fi

# Build des images
echo "[4/5] Build des images Docker..."
docker compose -f docker-compose.prod.yml build

# Demarrage des services (force-recreate pour recharger les volumes)
echo "[5/5] Demarrage des services..."
docker compose -f docker-compose.prod.yml up -d --force-recreate

echo ""
echo "============================================"
echo "  Deploiement termine!"
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
