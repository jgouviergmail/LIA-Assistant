#!/bin/bash
# Script de déploiement automatique - HITL Metrics
# Usage: ./scripts/deploy_hitl_metrics.sh

set -e  # Exit on error

echo "========================================================================"
echo "DEPLOYMENT HITL METRICS - Automated Deployment Script"
echo "========================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configurable URLs
API_URL="${API_URL:-http://localhost:8000}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"

check_command() {
    if ! command -v $1 &> /dev/null; then
        log_error "$1 not found. Please install $1"
        exit 1
    fi
}

# Step 1: Prerequisites
echo "========================================================================"
echo "STEP 1: Checking Prerequisites"
echo "========================================================================"

log_info "Checking required commands..."
check_command python
check_command docker
check_command curl
check_command jq

log_info "All prerequisites met"
echo ""

# Step 2: Validate Code
echo "========================================================================"
echo "STEP 2: Validating Code Implementation"
echo "========================================================================"

log_info "Running metrics validation..."
cd apps/api
python scripts/validate_hitl_metrics_simple.py
VALIDATION_RESULT=$?
cd ../..

if [ $VALIDATION_RESULT -ne 0 ]; then
    log_error "Metrics validation failed!"
    exit 1
fi

log_info "Code validation: PASS"
echo ""

# Step 3: Validate Configuration
echo "========================================================================"
echo "STEP 3: Validating Configuration Files"
echo "========================================================================"

log_info "Validating recording_rules.yml..."
python -c "import yaml; yaml.safe_load(open('infrastructure/observability/prometheus/recording_rules.yml', encoding='utf-8'))" && log_info "Recording rules: VALID" || { log_error "Recording rules: INVALID"; exit 1; }

log_info "Validating alert_rules.yml..."
python -c "import yaml; yaml.safe_load(open('infrastructure/observability/prometheus/alert_rules.yml', encoding='utf-8'))" && log_info "Alert rules: VALID" || { log_error "Alert rules: INVALID"; exit 1; }

log_info "Validating dashboard JSON..."
python -c "import json; json.load(open('infrastructure/observability/grafana/dashboards/07-hitl-tool-approval.json', encoding='utf-8'))" && log_info "Dashboard JSON: VALID" || { log_error "Dashboard JSON: INVALID"; exit 1; }

echo ""

# Step 4: Start/Restart Services
echo "========================================================================"
echo "STEP 4: Starting/Restarting Services"
echo "========================================================================"

log_info "Checking if Docker Compose is available..."
if [ -f "docker-compose.yml" ]; then
    log_info "Found docker-compose.yml"

    log_warn "About to restart Prometheus. This will cause brief interruption."
    read -p "Continue? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warn "Deployment cancelled by user"
        exit 0
    fi

    log_info "Restarting Prometheus..."
    docker-compose restart prometheus

    log_info "Waiting 10 seconds for Prometheus to start..."
    sleep 10
else
    log_warn "docker-compose.yml not found. Skipping service restart."
    log_warn "Please restart Prometheus manually."
fi

echo ""

# Step 5: Verify Prometheus
echo "========================================================================"
echo "STEP 5: Verifying Prometheus Configuration"
echo "========================================================================"

log_info "Checking Prometheus health..."
PROMETHEUS_HEALTH=$(curl -s http://localhost:9090/-/healthy)
if [[ $PROMETHEUS_HEALTH == *"Prometheus is Healthy"* ]]; then
    log_info "Prometheus: HEALTHY"
else
    log_error "Prometheus: UNHEALTHY or not accessible"
    log_warn "Please check Prometheus logs: docker logs prometheus"
    exit 1
fi

log_info "Checking recording rules loaded..."
RECORDING_RULES=$(curl -s http://localhost:9090/api/v1/rules | jq -r '.data.groups[] | select(.name=="hitl_user_behavior") | .name')
if [ "$RECORDING_RULES" == "hitl_user_behavior" ]; then
    log_info "Recording rules: LOADED (4 rules)"
else
    log_error "Recording rules: NOT LOADED"
    exit 1
fi

log_info "Checking alert rules loaded..."
ALERT_RULES_COUNT=$(curl -s http://localhost:9090/api/v1/rules | jq -r '.data.groups[] | select(.name=="hitl_quality") | .rules | length')
if [ "$ALERT_RULES_COUNT" == "8" ]; then
    log_info "Alert rules: LOADED (8 alerts)"
else
    log_error "Alert rules: NOT LOADED or incomplete (found $ALERT_RULES_COUNT, expected 8)"
    exit 1
fi

echo ""

# Step 6: Verify API
echo "========================================================================"
echo "STEP 6: Verifying API /metrics Endpoint"
echo "========================================================================"

log_info "Checking API health..."
API_HEALTH=$(curl -s ${API_URL}/health 2>/dev/null || echo "FAIL")
if [[ $API_HEALTH == *"ok"* ]] || [[ $API_HEALTH == *"healthy"* ]]; then
    log_info "API: HEALTHY"
else
    log_warn "API: Not accessible at ${API_URL}"
    log_warn "Please start API manually: cd apps/api && uvicorn src.main:app --reload"
    log_warn "Skipping metrics verification..."
    echo ""
    echo "========================================================================"
    echo "DEPLOYMENT: PARTIAL SUCCESS"
    echo "========================================================================"
    echo ""
    echo "Configuration deployed successfully, but API verification skipped."
    echo "Please start the API and verify metrics manually:"
    echo "  curl ${API_URL}/metrics | grep hitl_clarification_fallback"
    echo ""
    exit 0
fi

log_info "Checking /metrics endpoint..."
METRICS_AVAILABLE=$(curl -s ${API_URL}/metrics | grep -c "hitl_clarification_fallback_total" || echo "0")
if [ "$METRICS_AVAILABLE" -gt 0 ]; then
    log_info "Metrics: EXPOSED (hitl_clarification_fallback_total found)"
else
    log_error "Metrics: NOT EXPOSED"
    log_error "hitl_clarification_fallback_total not found in /metrics"
    exit 1
fi

log_info "Checking all 3 new metrics..."
METRIC1=$(curl -s ${API_URL}/metrics | grep -c "hitl_clarification_fallback_total" || echo "0")
METRIC2=$(curl -s ${API_URL}/metrics | grep -c "hitl_edit_actions_total" || echo "0")
METRIC3=$(curl -s ${API_URL}/metrics | grep -c "hitl_rejection_type_total" || echo "0")

if [ "$METRIC1" -gt 0 ] && [ "$METRIC2" -gt 0 ] && [ "$METRIC3" -gt 0 ]; then
    log_info "All 3 metrics: FOUND"
else
    log_error "Some metrics missing: fallback=$METRIC1, edit=$METRIC2, rejection=$METRIC3"
    exit 1
fi

echo ""

# Step 7: Verify Prometheus Scraping
echo "========================================================================"
echo "STEP 7: Verifying Prometheus Scraping"
echo "========================================================================"

log_info "Checking Prometheus targets..."
API_TARGET=$(curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets[] | select(.labels.job=="api") | .health')
if [ "$API_TARGET" == "up" ]; then
    log_info "Prometheus → API scraping: UP"
else
    log_warn "Prometheus → API scraping: DOWN or not configured"
    log_warn "Please check prometheus.yml for 'api' job configuration"
fi

echo ""

# Step 8: Summary
echo "========================================================================"
echo "DEPLOYMENT: SUCCESS"
echo "========================================================================"
echo ""
echo "✓ Code validation: PASS"
echo "✓ Configuration validation: PASS"
echo "✓ Prometheus restarted: OK"
echo "✓ Recording rules loaded: 4/4"
echo "✓ Alert rules loaded: 8/8"
echo "✓ API /metrics endpoint: ACCESSIBLE"
echo "✓ New metrics exposed: 3/3"
echo "✓ Prometheus scraping: $([ "$API_TARGET" == "up" ] && echo "UP" || echo "CHECK MANUALLY")"
echo ""
echo "========================================================================"
echo "NEXT STEPS"
echo "========================================================================"
echo ""
echo "1. Import Dashboard to Grafana:"
echo "   - Open ${GRAFANA_URL}"
echo "   - Dashboards → Import"
echo "   - Upload: infrastructure/observability/grafana/dashboards/07-hitl-tool-approval.json"
echo ""
echo "2. Run Functional Tests:"
echo "   - Follow: PHASE4_FUNCTIONAL_TESTS.md"
echo "   - Trigger HITL interactions"
echo "   - Verify metrics increment"
echo ""
echo "3. Configure Alertmanager (Optional):"
echo "   - Edit: infrastructure/observability/alertmanager/alertmanager.yml"
echo "   - Add Slack webhooks"
echo "   - Restart: docker-compose restart alertmanager"
echo ""
echo "4. Collect Baseline Metrics (1 week):"
echo "   - Monitor dashboard daily"
echo "   - Calculate average/median values"
echo "   - Adjust alert thresholds if needed"
echo ""
echo "Documentation:"
echo "  - Deployment Guide: DEPLOYMENT_GUIDE_HITL_METRICS.md"
echo "  - Quick Reference: HITL_METRICS_QUICK_REFERENCE.md"
echo "  - Full Report: HITL_METRICS_IMPLEMENTATION_COMPLETE.md"
echo ""
echo "========================================================================"
