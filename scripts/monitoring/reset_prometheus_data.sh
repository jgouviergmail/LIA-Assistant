#!/bin/bash
# Script de réinitialisation des données Prometheus
# Usage: ./scripts/reset_prometheus_data.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "RESET PROMETHEUS DATA - Réinitialisation complète"
echo "========================================================================"
echo ""

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Step 1: Confirmation
echo "========================================================================="
echo "AVERTISSEMENT"
echo "========================================================================="
echo ""
log_warn "Cette opération va SUPPRIMER TOUTES les données Prometheus:"
log_warn "  - Toutes les métriques historiques"
log_warn "  - Tous les graphiques seront réinitialisés"
log_warn "  - Les alertes perdront leur historique"
echo ""
log_warn "Volume concerné: lia_prometheus_data"
echo ""
read -p "Êtes-vous sûr de vouloir continuer? (tapez 'oui' pour confirmer): " confirmation

if [ "$confirmation" != "oui" ]; then
    log_warn "Opération annulée par l'utilisateur"
    exit 0
fi

echo ""

# Step 2: Arrêt de Prometheus
echo "========================================================================="
echo "STEP 1: Arrêt du conteneur Prometheus"
echo "========================================================================="
echo ""

log_info "Arrêt de Prometheus..."
docker-compose stop prometheus

log_info "Prometheus arrêté"
echo ""

# Step 3: Suppression du volume
echo "========================================================================="
echo "STEP 2: Suppression du volume de données"
echo "========================================================================="
echo ""

log_info "Suppression du volume lia_prometheus_data..."
docker volume rm lia_prometheus_data

log_info "Volume supprimé avec succès"
echo ""

# Step 4: Redémarrage de Prometheus
echo "========================================================================="
echo "STEP 3: Redémarrage de Prometheus"
echo "========================================================================="
echo ""

log_info "Démarrage de Prometheus (avec nouveau volume vide)..."
docker-compose up -d prometheus

log_info "Attente de 10 secondes pour le démarrage..."
sleep 10

# Step 5: Vérification
echo ""
echo "========================================================================="
echo "STEP 4: Vérification"
echo "========================================================================="
echo ""

log_info "Vérification de l'état de Prometheus..."

PROMETHEUS_HEALTH=$(curl -s http://localhost:9090/-/healthy 2>/dev/null || echo "FAIL")
if [[ $PROMETHEUS_HEALTH == *"Prometheus is Healthy"* ]]; then
    log_info "Prometheus: HEALTHY"
else
    log_error "Prometheus: UNHEALTHY ou non accessible"
    log_warn "Vérifier les logs: docker logs lia-prometheus-dev"
    exit 1
fi

log_info "Vérification du nouveau volume..."
docker volume inspect lia_prometheus_data > /dev/null 2>&1
if [ $? -eq 0 ]; then
    log_info "Nouveau volume créé avec succès"
else
    log_error "Volume non créé"
    exit 1
fi

# Step 6: Vérification des métriques
log_info "Vérification des métriques (doit être vide)..."
METRIC_COUNT=$(curl -s "http://localhost:9090/api/v1/query?query=llm_tokens_consumed_total" | jq -r '.data.result | length' 2>/dev/null || echo "0")
log_info "Séries de métriques llm_tokens_consumed_total: $METRIC_COUNT"

echo ""
echo "========================================================================="
echo "RESET TERMINÉ AVEC SUCCÈS"
echo "========================================================================="
echo ""
echo "✓ Prometheus redémarré"
echo "✓ Volume de données recréé (vide)"
echo "✓ Toutes les métriques historiques effacées"
echo ""
echo "Prochaines étapes:"
echo "  1. Les nouvelles métriques commenceront à s'accumuler"
echo "  2. Les dashboards Grafana seront vides jusqu'à nouvelle collecte"
echo "  3. Attendre quelques minutes pour voir les premières données"
echo ""
echo "Pour vérifier:"
echo "  - Prometheus UI: http://localhost:9090"
echo "  - Grafana: http://localhost:3001"
echo ""
echo "========================================================================"
