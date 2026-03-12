#!/bin/bash
# Diagnostic script for service health (ServiceDown runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configurable URLs
API_URL="${API_URL:-http://localhost:8000}"

echo -e "${BLUE}=== Service Health Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/4] API availability...${NC}"
if curl -f -s ${API_URL}/health > /dev/null 2>&1; then
    echo -e "${GREEN}[OK] API responding on port 8000${NC}"
else
    echo -e "${RED}[CRITICAL] API not responding${NC}"
fi
echo ""

echo -e "${BLUE}[2/4] API container status...${NC}"
docker-compose ps api
echo ""

echo -e "${BLUE}[3/4] API resource usage...${NC}"
docker stats --no-stream lia_api_1 2>/dev/null || echo "Container not running"
echo ""

echo -e "${BLUE}[4/4] Recent API errors...${NC}"
docker-compose logs --tail=30 api 2>/dev/null | grep -i "error\|exception\|traceback" || echo "No recent errors"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/ServiceDown.md"
