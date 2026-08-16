#!/bin/bash
# Diagnostic script for OAuth security (PKCEValidationFailures runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== OAuth Security Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/4] PKCE validation failure rate...${NC}"
PKCE_FAILURE_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=(rate(pkce_validation_failures_total[5m])/rate(pkce_validation_attempts_total[5m]))*100" | jq -r '.data.result[0].value[1] // "0"')
PKCE_FAILURE_INT=${PKCE_FAILURE_RATE%.*}

if (( PKCE_FAILURE_INT > 10 )); then
    echo -e "${RED}[CRITICAL] PKCE failure rate: ${PKCE_FAILURE_RATE}% (threshold: 5%)${NC}"
elif (( PKCE_FAILURE_INT > 5 )); then
    echo -e "${YELLOW}[WARNING] PKCE failure rate: ${PKCE_FAILURE_RATE}% (threshold: 5%)${NC}"
else
    echo -e "${GREEN}[OK] PKCE failure rate: ${PKCE_FAILURE_RATE}%${NC}"
fi
echo ""

echo -e "${BLUE}[2/4] Failures by reason (last 5min)...${NC}"
curl -s "http://localhost:9090/api/v1/query?query=sum by (reason) (rate(pkce_validation_failures_total[5m]))" | jq -r '.data.result[] | "\(.metric.reason): \(.value[1])"' 2>/dev/null || echo "No failure data"
echo ""

echo -e "${BLUE}[3/4] Redis PKCE state availability...${NC}"
docker-compose exec -T redis redis-cli ping 2>/dev/null && echo -e "${GREEN}[OK] Redis responding${NC}" || echo -e "${RED}[ERROR] Redis not responding${NC}"

PKCE_KEYS=$(docker-compose exec -T redis redis-cli --scan --pattern "pkce:*" 2>/dev/null | wc -l)
echo "Active PKCE states: $PKCE_KEYS"
echo ""

echo -e "${BLUE}[4/4] Recent OAuth errors...${NC}"
docker-compose logs --tail=100 api 2>/dev/null | grep -i "pkce\|oauth.*error" | tail -10 || echo "No recent OAuth errors"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/PKCEValidationFailures.md"
