#!/bin/bash
# Diagnostic script for LLM API health (LLMAPIFailureRateHigh runbook)
# Usage: ./diagnose_llm_api.sh [--detailed]

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

DETAILED=false
if [[ "${1:-}" == "--detailed" ]]; then
    DETAILED=true
fi

echo -e "${BLUE}=== LLM API Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# 1. Check LLM API error rate
echo -e "${BLUE}[1/5] Checking LLM API error rate...${NC}"
ERROR_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_api_calls_total{result=\"error\"}[5m]))*100/sum(rate(llm_api_calls_total[5m]))" | jq -r '.data.result[0].value[1] // "0"')
ERROR_RATE_INT=${ERROR_RATE%.*}

if (( ERROR_RATE_INT > 5 )); then
    echo -e "${RED}[CRITICAL] LLM error rate: ${ERROR_RATE}% (threshold: 3%)${NC}"
elif (( ERROR_RATE_INT > 3 )); then
    echo -e "${YELLOW}[WARNING] LLM error rate: ${ERROR_RATE}% (threshold: 3%)${NC}"
else
    echo -e "${GREEN}[OK] LLM error rate: ${ERROR_RATE}%${NC}"
fi
echo ""

# 2. Check Anthropic API status
echo -e "${BLUE}[2/5] Checking Anthropic API status...${NC}"
STATUS=$(curl -s https://status.anthropic.com/api/v2/status.json 2>/dev/null | jq -r '.status.description // "unknown"')
UPDATED=$(curl -s https://status.anthropic.com/api/v2/status.json 2>/dev/null | jq -r '.page.updated_at // "unknown"')

echo "Status: $STATUS"
echo "Last updated: $UPDATED"

if [[ "$STATUS" != "All Systems Operational" ]]; then
    echo -e "${YELLOW}[WARNING] Anthropic API may be experiencing issues${NC}"
fi
echo ""

# 3. Check LLM API latency
echo -e "${BLUE}[3/5] Checking LLM API latency...${NC}"
P95_LATENCY=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_latency_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
P95_MS=$(echo "$P95_LATENCY * 1000" | bc | cut -d. -f1)

if (( P95_MS > 10000 )); then
    echo -e "${YELLOW}[WARNING] P95 latency: ${P95_MS}ms (high)${NC}"
else
    echo -e "${GREEN}[OK] P95 latency: ${P95_MS}ms${NC}"
fi
echo ""

# 4. Check recent LLM errors in logs
echo -e "${BLUE}[4/5] Recent LLM errors (last 10)...${NC}"
docker-compose logs --tail=200 api 2>/dev/null | grep -i "anthropic\|llm.*error\|rate.*limit" | tail -10 || echo "No recent LLM errors found"
echo ""

# 5. Detailed error breakdown
if [[ "$DETAILED" == "true" ]]; then
    echo -e "${BLUE}[5/5] Error breakdown by model (last 1h)...${NC}"
    curl -s "http://localhost:9090/api/v1/query?query=sum by (model) (increase(llm_api_calls_total{result=\"error\"}[1h]))" | jq -r '.data.result[] | "\(.metric.model): \(.value[1])"'
    echo ""

    echo "Cost impact (last 24h):"
    curl -s "http://localhost:9090/api/v1/query?query=llm_cost_last_24h" | jq -r '.data.result[0].value[1] // "0"' | xargs printf "Total: $%.2f\n"
    echo ""
fi

# Summary
echo -e "${BLUE}=== Summary & Recommendations ===${NC}"

if (( ERROR_RATE_INT > 5 )); then
    echo -e "${RED}[CRITICAL] LLM error rate >5% - Immediate action required${NC}"
    echo "Recommended actions:"
    echo "  1. Check Anthropic status page: https://status.anthropic.com"
    echo "  2. Verify API key is valid: echo \$ANTHROPIC_API_KEY"
    echo "  3. Review error logs above for rate limiting or quota issues"
    echo "  4. Consider implementing retry logic with exponential backoff"
elif (( ERROR_RATE_INT > 3 )); then
    echo -e "${YELLOW}[WARNING] LLM error rate >3% - Monitor closely${NC}"
    echo "Recommended actions:"
    echo "  1. Check if Anthropic API is degraded (status: $STATUS)"
    echo "  2. Review recent error patterns in logs"
else
    echo -e "${GREEN}[OK] LLM API healthy${NC}"
fi

echo ""
echo "For detailed runbook, see: docs/runbooks/alerts/LLMAPIFailureRateHigh.md"
