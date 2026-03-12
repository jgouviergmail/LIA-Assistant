#!/bin/bash
# Script de validation du provisioning automatique Grafana
# Usage: ./scripts/validate_grafana_provisioning.sh

set -e

echo "========================================================================"
echo "VALIDATION GRAFANA PROVISIONING - Dashboards Auto-Deployment"
echo "========================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Configurable URLs
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"

# Step 1: Verify configuration files
echo "========================================================================"
echo "STEP 1: Verify Configuration Files"
echo "========================================================================"

log_info "Checking provisioning configuration..."

# Check dashboards.yml
if [ -f "infrastructure/observability/grafana/provisioning/dashboards/dashboards.yml" ]; then
    log_success "Found dashboards.yml"

    # Verify path configuration
    if grep -q "path: /var/lib/grafana/dashboards" infrastructure/observability/grafana/provisioning/dashboards/dashboards.yml; then
        log_success "Dashboard path correctly configured: /var/lib/grafana/dashboards"
    else
        log_error "Dashboard path not configured correctly"
        exit 1
    fi

    # Verify update interval
    INTERVAL=$(grep "updateIntervalSeconds:" infrastructure/observability/grafana/provisioning/dashboards/dashboards.yml | awk '{print $2}')
    log_info "Update interval: ${INTERVAL}s (dashboards auto-reload every ${INTERVAL}s)"
else
    log_error "dashboards.yml not found!"
    exit 1
fi

# Check grafana.ini
if [ -f "infrastructure/observability/grafana/grafana.ini" ]; then
    log_success "Found grafana.ini"

    if grep -q "provisioning = /etc/grafana/provisioning" infrastructure/observability/grafana/grafana.ini; then
        log_success "Provisioning path configured in grafana.ini"
    else
        log_warn "Provisioning path not explicitly set (using default)"
    fi
else
    log_error "grafana.ini not found!"
    exit 1
fi

echo ""

# Step 2: Verify dashboard files
echo "========================================================================"
echo "STEP 2: Verify Dashboard Files"
echo "========================================================================"

log_info "Scanning dashboard directory..."

DASHBOARD_DIR="infrastructure/observability/grafana/dashboards"
DASHBOARD_COUNT=$(ls -1 ${DASHBOARD_DIR}/*.json 2>/dev/null | wc -l)

if [ $DASHBOARD_COUNT -gt 0 ]; then
    log_success "Found ${DASHBOARD_COUNT} dashboard(s)"

    # List dashboards
    for dashboard in ${DASHBOARD_DIR}/*.json; do
        filename=$(basename "$dashboard")

        # Validate JSON
        if python -c "import json; json.load(open('${dashboard}', encoding='utf-8'))" 2>/dev/null; then
            # Extract title
            title=$(python -c "import json; d=json.load(open('${dashboard}', encoding='utf-8')); print(d.get('title', 'Unknown'))" 2>/dev/null)
            panels=$(python -c "import json; d=json.load(open('${dashboard}', encoding='utf-8')); print(len(d.get('panels', [])))" 2>/dev/null)

            log_info "  ✓ ${filename}: '${title}' (${panels} panels)"
        else
            log_error "  ✗ ${filename}: Invalid JSON!"
            exit 1
        fi
    done
else
    log_error "No dashboard files found in ${DASHBOARD_DIR}"
    exit 1
fi

# Specifically check HITL dashboard
if [ -f "${DASHBOARD_DIR}/07-hitl-tool-approval.json" ]; then
    log_success "HITL dashboard found: 07-hitl-tool-approval.json"

    # Verify our new panels are present
    HITL_PANELS=$(python -c "import json; d=json.load(open('${DASHBOARD_DIR}/07-hitl-tool-approval.json', encoding='utf-8')); print(len(d['panels']))")

    if [ $HITL_PANELS -ge 18 ]; then
        log_success "HITL dashboard has ${HITL_PANELS} panels (including new HITL metrics panels)"
    else
        log_warn "HITL dashboard has only ${HITL_PANELS} panels (expected >= 18)"
    fi

    # Check for specific panel titles
    python -c "
import json
import sys

with open('${DASHBOARD_DIR}/07-hitl-tool-approval.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

panels_to_check = [
    (16, 'HITL Clarification Fallback Rate'),
    (17, 'HITL Edit Actions Distribution'),
    (18, 'HITL Rejection Types Distribution')
]

all_found = True
for panel_id, expected_title in panels_to_check:
    panel = next((p for p in d['panels'] if p.get('id') == panel_id), None)
    if panel:
        title = panel.get('title', '')
        if expected_title in title:
            print(f'  ✓ Panel {panel_id}: {title}')
        else:
            print(f'  ! Panel {panel_id}: Found \"{title}\" (expected \"{expected_title}\")')
            all_found = False
    else:
        print(f'  ✗ Panel {panel_id} not found!')
        all_found = False

sys.exit(0 if all_found else 1)
"

    if [ $? -eq 0 ]; then
        log_success "All 3 new HITL panels verified"
    else
        log_warn "Some new panels may be missing or misnamed"
    fi
else
    log_error "HITL dashboard not found: 07-hitl-tool-approval.json"
    exit 1
fi

echo ""

# Step 3: Verify Docker configuration
echo "========================================================================"
echo "STEP 3: Verify Docker Configuration"
echo "========================================================================"

log_info "Checking docker-compose configuration..."

COMPOSE_FILE=""
if [ -f "docker-compose.dev.yml" ]; then
    COMPOSE_FILE="docker-compose.dev.yml"
elif [ -f "docker-compose.yml" ]; then
    COMPOSE_FILE="docker-compose.yml"
else
    log_error "No docker-compose file found!"
    exit 1
fi

log_info "Using: ${COMPOSE_FILE}"

# Check volumes are mounted correctly
if grep -A 5 "grafana:" ${COMPOSE_FILE} | grep -q "./infrastructure/observability/grafana/dashboards:/var/lib/grafana/dashboards"; then
    log_success "Dashboard directory correctly mounted"
else
    log_error "Dashboard directory NOT mounted correctly!"
    log_error "Expected: ./infrastructure/observability/grafana/dashboards:/var/lib/grafana/dashboards"
    exit 1
fi

if grep -A 5 "grafana:" ${COMPOSE_FILE} | grep -q "./infrastructure/observability/grafana/provisioning:/etc/grafana/provisioning"; then
    log_success "Provisioning directory correctly mounted"
else
    log_error "Provisioning directory NOT mounted correctly!"
    exit 1
fi

echo ""

# Step 4: Check if Grafana is running
echo "========================================================================"
echo "STEP 4: Check Grafana Status"
echo "========================================================================"

log_info "Checking if Grafana container is running..."

if docker ps --format '{{.Names}}' | grep -q grafana; then
    CONTAINER_NAME=$(docker ps --format '{{.Names}}' | grep grafana)
    log_success "Grafana container running: ${CONTAINER_NAME}"

    # Check Grafana API
    log_info "Checking Grafana API..."

    # Check configured Grafana URL
    GRAFANA_REACHABLE=""
    if curl -s ${GRAFANA_URL}/api/health >/dev/null 2>&1; then
        GRAFANA_REACHABLE="true"
    fi

    if [ -n "$GRAFANA_REACHABLE" ]; then
        log_success "Grafana API accessible at: ${GRAFANA_URL}"

        # Check provisioned dashboards
        log_info "Checking provisioned dashboards via API..."

        DASHBOARD_COUNT_API=$(curl -s -u admin:admin "${GRAFANA_URL}/api/search?type=dash-db" | python -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

        if [ $DASHBOARD_COUNT_API -gt 0 ]; then
            log_success "Found ${DASHBOARD_COUNT_API} dashboard(s) in Grafana"

            # Check specifically for HITL dashboard
            HITL_EXISTS=$(curl -s -u admin:admin "${GRAFANA_URL}/api/search?query=HITL" | python -c "import sys, json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

            if [ $HITL_EXISTS -gt 0 ]; then
                log_success "HITL dashboard is provisioned and accessible"

                # Get dashboard UID
                HITL_UID=$(curl -s -u admin:admin "${GRAFANA_URL}/api/search?query=HITL" | python -c "import sys, json; data=json.load(sys.stdin); print(data[0]['uid'] if len(data) > 0 else '')" 2>/dev/null || echo "")

                if [ -n "$HITL_UID" ]; then
                    log_info "Dashboard URL: ${GRAFANA_URL}/d/${HITL_UID}/07-hitl-tool-approval"

                    # Verify panel count in provisioned dashboard
                    PROVISIONED_PANELS=$(curl -s -u admin:admin "${GRAFANA_URL}/api/dashboards/uid/${HITL_UID}" | python -c "import sys, json; data=json.load(sys.stdin); print(len(data['dashboard']['panels']))" 2>/dev/null || echo "0")

                    if [ $PROVISIONED_PANELS -ge 18 ]; then
                        log_success "Provisioned dashboard has ${PROVISIONED_PANELS} panels ✓"
                    else
                        log_warn "Provisioned dashboard has only ${PROVISIONED_PANELS} panels (expected >= 18)"
                        log_warn "Dashboard may need to be reloaded. Restart Grafana to force reload."
                    fi
                fi
            else
                log_warn "HITL dashboard not found in Grafana (may need restart)"
            fi
        else
            log_warn "No dashboards found in Grafana (provisioning may not have run yet)"
        fi
    else
        log_warn "Grafana API not accessible (may still be starting)"
    fi
else
    log_warn "Grafana container not running"
    log_info "Start with: docker-compose up -d grafana"
fi

echo ""

# Summary
echo "========================================================================"
echo "SUMMARY"
echo "========================================================================"
echo ""
echo "Configuration:"
echo "  ✓ Provisioning config: OK"
echo "  ✓ Dashboard files: ${DASHBOARD_COUNT} found"
echo "  ✓ HITL dashboard: Present with ${HITL_PANELS:-?} panels"
echo "  ✓ Docker volumes: Correctly mounted"
echo ""
echo "Auto-Deployment Process:"
echo "  1. Dashboard JSON files in: infrastructure/observability/grafana/dashboards/"
echo "  2. Mounted to container: /var/lib/grafana/dashboards/"
echo "  3. Grafana provisioning scans every ${INTERVAL}s"
echo "  4. Dashboards automatically created/updated in Grafana"
echo ""
echo "To apply dashboard changes:"
echo "  1. Edit: infrastructure/observability/grafana/dashboards/07-hitl-tool-approval.json"
echo "  2. Wait ${INTERVAL}s OR restart: docker-compose restart grafana"
echo "  3. Changes automatically appear in Grafana UI"
echo ""
echo "No manual import needed - everything is automatic! 🚀"
echo ""
echo "========================================================================"

log_success "Validation complete!"
