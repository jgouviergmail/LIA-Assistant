#!/bin/bash
# Diagnostic script for agents performance (AgentsRouterLatencyHigh runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Agents Performance Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/3] Router latency (P95)...${NC}"
ROUTER_P95=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(agent_router_latency_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
ROUTER_MS=$(echo "$ROUTER_P95 * 1000" | bc | cut -d. -f1)

if (( ROUTER_MS > 3000 )); then
    echo -e "${RED}[CRITICAL] Router P95: ${ROUTER_MS}ms (threshold: 2000ms)${NC}"
elif (( ROUTER_MS > 2000 )); then
    echo -e "${YELLOW}[WARNING] Router P95: ${ROUTER_MS}ms (threshold: 2000ms)${NC}"
else
    echo -e "${GREEN}[OK] Router P95: ${ROUTER_MS}ms${NC}"
fi
echo ""

echo -e "${BLUE}[2/3] LLM calls by operation (last 5min)...${NC}"
curl -s "http://localhost:9090/api/v1/query?query=sum by (operation) (rate(llm_api_calls_total[5m]))" | jq -r '.data.result[] | "\(.metric.operation): \(.value[1])"'
echo ""

echo -e "${BLUE}[3/3] Agent errors (last 20)...${NC}"
docker-compose logs --tail=100 api 2>/dev/null | grep -i "agent.*error\|router.*error" | tail -20 || echo "No agent errors"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/AgentsRouterLatencyHigh.md"
