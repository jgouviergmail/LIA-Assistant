#!/bin/bash
# Diagnostic script for LLM costs (DailyCostBudgetExceeded runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

BUDGET=${DAILY_COST_BUDGET_USD:-100}

echo -e "${BLUE}=== LLM Cost Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "Daily budget: \$${BUDGET}"
echo ""

echo -e "${BLUE}[1/4] 24-hour cost...${NC}"
COST_24H=$(curl -s "http://localhost:9090/api/v1/query?query=llm_cost_last_24h" | jq -r '.data.result[0].value[1] // "0"')
COST_24H_INT=${COST_24H%.*}

if (( COST_24H_INT > BUDGET * 2 )); then
    echo -e "${RED}[CRITICAL] 24h cost: \$${COST_24H} (budget: \$${BUDGET})${NC}"
elif (( COST_24H_INT > BUDGET )); then
    echo -e "${YELLOW}[WARNING] 24h cost: \$${COST_24H} (budget: \$${BUDGET})${NC}"
else
    echo -e "${GREEN}[OK] 24h cost: \$${COST_24H} (budget: \$${BUDGET})${NC}"
fi
echo ""

echo -e "${BLUE}[2/4] Cost by model (last 24h)...${NC}"
curl -s "http://localhost:9090/api/v1/query?query=llm_cost_by_model_last_24h" | jq -r '.data.result[] | "\(.metric.model): $\(.value[1])"'
echo ""

echo -e "${BLUE}[3/4] Token consumption (last 24h)...${NC}"
curl -s "http://localhost:9090/api/v1/query?query=llm_tokens_consumed_last_24h" | jq -r '.data.result[] | "\(.metric.token_type): \(.value[1])"'
echo ""

echo -e "${BLUE}[4/4] LLM cache hit rate...${NC}"
CACHE_HIT_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=(sum(rate(llm_cache_hits_total[1h]))/sum(rate(llm_cache_requests_total[1h])))*100" | jq -r '.data.result[0].value[1] // "0"')
CACHE_HIT_INT=${CACHE_HIT_RATE%.*}

echo "Cache hit rate: ${CACHE_HIT_RATE}%"
if (( CACHE_HIT_INT < 40 )); then
    echo -e "${YELLOW}[WARNING] Low cache hit rate (<40%) - opportunity for cost savings${NC}"
else
    echo -e "${GREEN}[OK] Cache hit rate acceptable${NC}"
fi
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/DailyCostBudgetExceeded.md"
