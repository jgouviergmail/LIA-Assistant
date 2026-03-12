#!/bin/bash
# Diagnostic script for agents streaming (AgentsStreamingErrorRateHigh runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Agents Streaming Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/3] Streaming error rate...${NC}"
STREAMING_ERROR_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=(rate(agent_streaming_errors_total[5m])/rate(agent_streaming_requests_total[5m]))*100" | jq -r '.data.result[0].value[1] // "0"')
STREAMING_ERROR_INT=${STREAMING_ERROR_RATE%.*}

if (( STREAMING_ERROR_INT > 5 )); then
    echo -e "${RED}[CRITICAL] Streaming error rate: ${STREAMING_ERROR_RATE}% (threshold: 3%)${NC}"
elif (( STREAMING_ERROR_INT > 3 )); then
    echo -e "${YELLOW}[WARNING] Streaming error rate: ${STREAMING_ERROR_RATE}% (threshold: 3%)${NC}"
else
    echo -e "${GREEN}[OK] Streaming error rate: ${STREAMING_ERROR_RATE}%${NC}"
fi
echo ""

echo -e "${BLUE}[2/3] Streaming request duration (P95)...${NC}"
STREAMING_P95=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket{path=~\".*stream.*\"}[5m]))" | jq -r '.data.result[0].value[1] // "0"')
STREAMING_P95_MS=$(echo "$STREAMING_P95 * 1000" | bc | cut -d. -f1)

if (( STREAMING_P95_MS > 30000 )); then
    echo -e "${YELLOW}[WARNING] Streaming P95: ${STREAMING_P95_MS}ms (slow)${NC}"
else
    echo -e "${GREEN}[OK] Streaming P95: ${STREAMING_P95_MS}ms${NC}"
fi
echo ""

echo -e "${BLUE}[3/3] Recent streaming errors...${NC}"
docker-compose logs --tail=100 api 2>/dev/null | grep -i "streaming.*error\|websocket.*error\|sse.*error" | tail -10 || echo "No recent streaming errors"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/AgentsStreamingErrorRateHigh.md"
