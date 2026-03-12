#!/bin/bash
################################################################################
# Prepare Prometheus Configuration for Environment
################################################################################
#
# This script renders Prometheus alert templates with environment-specific
# thresholds before starting Docker containers.
#
# Usage:
#   ./prepare_config.sh [environment]
#
# Arguments:
#   environment: production | staging | development (default: development)
#
# Process:
#   1. Detects environment (from arg or $ENVIRONMENT)
#   2. Loads thresholds from thresholds/{environment}.env
#   3. Renders alert_rules.yml.template -> alert_rules.yml
#   4. Renders alerts.yml.template -> alerts.yml
#   5. Validates generated YAML syntax
#
# Requirements:
#   - Python 3.10+ with jinja2, pyyaml, python-dotenv
#   - Template files: alert_rules.yml.template, alerts.yml.template
#   - Threshold files: thresholds/{production,staging,development}.env
#
# Author: Infrastructure Team
# Date: 2025-11-23
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default environment
ENVIRONMENT="${1:-${ENVIRONMENT:-development}}"

# Validate environment
case "$ENVIRONMENT" in
    production|staging|development)
        ;;
    *)
        echo -e "${RED}ERROR: Invalid environment '${ENVIRONMENT}'${NC}"
        echo "Usage: $0 [production|staging|development]"
        exit 1
        ;;
esac

echo "================================================================================"
echo "PREPARE PROMETHEUS CONFIGURATION - ${ENVIRONMENT}"
echo "================================================================================"
echo ""

# Check if threshold file exists
THRESHOLD_FILE="${SCRIPT_DIR}/thresholds/${ENVIRONMENT}.env"
if [ ! -f "$THRESHOLD_FILE" ]; then
    echo -e "${RED}ERROR: Threshold file not found: ${THRESHOLD_FILE}${NC}"
    exit 1
fi

echo -e "${GREEN}[1/4] Loading thresholds from: ${THRESHOLD_FILE}${NC}"
# Count thresholds
THRESHOLD_COUNT=$(grep -c "^ALERT_" "$THRESHOLD_FILE" || true)
echo "      Found ${THRESHOLD_COUNT} threshold variables"
echo ""

# Check if render_alerts.py exists
if [ ! -f "${SCRIPT_DIR}/render_alerts.py" ]; then
    echo -e "${RED}ERROR: render_alerts.py not found${NC}"
    exit 1
fi

# Check if templates exist
ALERT_RULES_TEMPLATE="${SCRIPT_DIR}/alert_rules.yml.template"
ALERTS_TEMPLATE="${SCRIPT_DIR}/alerts.yml.template"

if [ ! -f "$ALERT_RULES_TEMPLATE" ]; then
    echo -e "${RED}ERROR: Template not found: ${ALERT_RULES_TEMPLATE}${NC}"
    exit 1
fi

if [ ! -f "$ALERTS_TEMPLATE" ]; then
    echo -e "${RED}ERROR: Template not found: ${ALERTS_TEMPLATE}${NC}"
    exit 1
fi

echo -e "${GREEN}[2/4] Rendering alert_rules.yml${NC}"
# Detect Python command (python3 on Linux/Mac, python on Windows)
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo -e "${RED}ERROR: Python not found${NC}"
    exit 1
fi

# Render alert_rules.yml
$PYTHON_CMD "${SCRIPT_DIR}/render_alerts.py" \
    --env-file "$THRESHOLD_FILE" \
    --template "$ALERT_RULES_TEMPLATE" \
    --output "${SCRIPT_DIR}/alert_rules.yml"

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to render alert_rules.yml${NC}"
    exit 1
fi
echo ""

echo -e "${GREEN}[3/4] Rendering alerts.yml${NC}"
# Render alerts.yml
$PYTHON_CMD "${SCRIPT_DIR}/render_alerts.py" \
    --env-file "$THRESHOLD_FILE" \
    --template "$ALERTS_TEMPLATE" \
    --output "${SCRIPT_DIR}/alerts.yml"

if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to render alerts.yml${NC}"
    exit 1
fi
echo ""

echo -e "${GREEN}[4/4] Validating generated files${NC}"
# Check if files were created
if [ -f "${SCRIPT_DIR}/alert_rules.yml" ]; then
    ALERT_RULES_LINES=$(wc -l < "${SCRIPT_DIR}/alert_rules.yml")
    ALERT_RULES_ALERTS=$(grep -c "alert:" "${SCRIPT_DIR}/alert_rules.yml" || true)
    echo "      alert_rules.yml: ${ALERT_RULES_LINES} lines, ${ALERT_RULES_ALERTS} alerts"
else
    echo -e "${RED}ERROR: alert_rules.yml was not generated${NC}"
    exit 1
fi

if [ -f "${SCRIPT_DIR}/alerts.yml" ]; then
    ALERTS_LINES=$(wc -l < "${SCRIPT_DIR}/alerts.yml")
    ALERTS_COUNT=$(grep -c "alert:" "${SCRIPT_DIR}/alerts.yml" || true)
    echo "      alerts.yml: ${ALERTS_LINES} lines, ${ALERTS_COUNT} alerts"
else
    echo -e "${RED}ERROR: alerts.yml was not generated${NC}"
    exit 1
fi

echo ""
echo "================================================================================"
echo -e "${GREEN}SUCCESS${NC} - Prometheus configuration prepared for ${ENVIRONMENT}"
echo "================================================================================"
echo ""
echo "Files generated:"
echo "  - ${SCRIPT_DIR}/alert_rules.yml (${ALERT_RULES_ALERTS} alerts)"
echo "  - ${SCRIPT_DIR}/alerts.yml (${ALERTS_COUNT} alerts)"
echo ""
echo "Next steps:"
echo "  1. Review generated files"
echo "  2. Start Docker containers: docker-compose up -d"
echo "  3. Verify Prometheus loaded alerts: http://localhost:9090/alerts"
echo ""
