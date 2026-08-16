#!/bin/bash
# Diagnostic script for container health (ContainerDown runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Container Health Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/4] Container status...${NC}"
docker-compose ps
echo ""

echo -e "${BLUE}[2/4] Container resource usage...${NC}"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
echo ""

echo -e "${BLUE}[3/4] Container restart counts (last 24h)...${NC}"
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.RunningFor}}" | grep lia
echo ""

echo -e "${BLUE}[4/4] Recent container logs (errors)...${NC}"
for service in api postgres redis; do
    echo "=== $service ==="
    docker-compose logs --tail=20 $service 2>/dev/null | grep -i "error\|fatal\|exception" || echo "No errors"
    echo ""
done

echo "For detailed runbook, see: docs/runbooks/alerts/ContainerDown.md"
