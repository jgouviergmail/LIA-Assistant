# Script de réinitialisation des données Prometheus (Windows PowerShell)
# Usage: .\scripts\reset_prometheus_data.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================================================"
Write-Host "RESET PROMETHEUS DATA - Réinitialisation complète"
Write-Host "========================================================================"
Write-Host ""

function Log-Info {
    param($Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Log-Warn {
    param($Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Log-Error {
    param($Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

# Step 1: Confirmation
Write-Host "========================================================================"
Write-Host "AVERTISSEMENT"
Write-Host "========================================================================"
Write-Host ""
Log-Warn "Cette opération va SUPPRIMER TOUTES les données Prometheus:"
Log-Warn "  - Toutes les métriques historiques"
Log-Warn "  - Tous les graphiques seront réinitialisés"
Log-Warn "  - Les alertes perdront leur historique"
Write-Host ""
Log-Warn "Volume concerné: lia_prometheus_data"
Write-Host ""
$confirmation = Read-Host "Êtes-vous sûr de vouloir continuer? (tapez 'oui' pour confirmer)"

if ($confirmation -ne "oui") {
    Log-Warn "Opération annulée par l'utilisateur"
    exit 0
}

Write-Host ""

# Step 2: Arrêt de Prometheus
Write-Host "========================================================================"
Write-Host "STEP 1: Arrêt du conteneur Prometheus"
Write-Host "========================================================================"
Write-Host ""

Log-Info "Arrêt de Prometheus..."
docker-compose stop prometheus

Log-Info "Prometheus arrêté"
Write-Host ""

# Step 3: Suppression du volume
Write-Host "========================================================================"
Write-Host "STEP 2: Suppression du volume de données"
Write-Host "========================================================================"
Write-Host ""

Log-Info "Suppression du volume lia_prometheus_data..."
docker volume rm lia_prometheus_data

Log-Info "Volume supprimé avec succès"
Write-Host ""

# Step 4: Redémarrage de Prometheus
Write-Host "========================================================================"
Write-Host "STEP 3: Redémarrage de Prometheus"
Write-Host "========================================================================"
Write-Host ""

Log-Info "Démarrage de Prometheus (avec nouveau volume vide)..."
docker-compose up -d prometheus

Log-Info "Attente de 10 secondes pour le démarrage..."
Start-Sleep -Seconds 10

# Step 5: Vérification
Write-Host ""
Write-Host "========================================================================"
Write-Host "STEP 4: Vérification"
Write-Host "========================================================================"
Write-Host ""

Log-Info "Vérification de l'état de Prometheus..."

try {
    $PrometheusHealth = Invoke-RestMethod -Uri "http://localhost:9090/-/healthy" -TimeoutSec 5
    if ($PrometheusHealth -like "*Prometheus is Healthy*") {
        Log-Info "Prometheus: HEALTHY"
    } else {
        Log-Error "Prometheus: UNHEALTHY"
        exit 1
    }
} catch {
    Log-Error "Prometheus: NON ACCESSIBLE"
    Log-Warn "Vérifier les logs: docker logs lia-prometheus-dev"
    exit 1
}

Log-Info "Vérification du nouveau volume..."
try {
    docker volume inspect lia_prometheus_data | Out-Null
    Log-Info "Nouveau volume créé avec succès"
} catch {
    Log-Error "Volume non créé"
    exit 1
}

# Step 6: Vérification des métriques
Log-Info "Vérification des métriques (doit être vide)..."
try {
    $Response = Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=llm_tokens_consumed_total"
    $MetricCount = $Response.data.result.Count
    Log-Info "Séries de métriques llm_tokens_consumed_total: $MetricCount"
} catch {
    Log-Warn "Impossible de vérifier les métriques (normal si tout est vide)"
}

Write-Host ""
Write-Host "========================================================================"
Write-Host "RESET TERMINÉ AVEC SUCCÈS"
Write-Host "========================================================================"
Write-Host ""
Write-Host "√ Prometheus redémarré"
Write-Host "√ Volume de données recréé (vide)"
Write-Host "√ Toutes les métriques historiques effacées"
Write-Host ""
Write-Host "Prochaines étapes:"
Write-Host "  1. Les nouvelles métriques commenceront à s'accumuler"
Write-Host "  2. Les dashboards Grafana seront vides jusqu'à nouvelle collecte"
Write-Host "  3. Attendre quelques minutes pour voir les premières données"
Write-Host ""
Write-Host "Pour vérifier:"
Write-Host "  - Prometheus UI: http://localhost:9090"
Write-Host "  - Grafana: http://localhost:3001"
Write-Host ""
Write-Host "========================================================================"
