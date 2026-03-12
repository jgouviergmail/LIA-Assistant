#!/bin/bash
# Diagnostic script for API latency (CriticalLatencyP99 runbook)
# Usage: ./diagnose_api_latency.sh [--detailed]

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

echo -e "${BLUE}=== API Latency Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# 1. Check P99 latency
echo -e "${BLUE}[1/6] Checking P99 latency...${NC}"
P99_LATENCY=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,rate(http_request_duration_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
P99_LATENCY_MS=$(echo "$P99_LATENCY * 1000" | bc | cut -d. -f1)

if (( P99_LATENCY_MS > 2000 )); then
    echo -e "${RED}[CRITICAL] P99 latency: ${P99_LATENCY_MS}ms (threshold: 1500ms)${NC}"
elif (( P99_LATENCY_MS > 1500 )); then
    echo -e "${YELLOW}[WARNING] P99 latency: ${P99_LATENCY_MS}ms (threshold: 1500ms)${NC}"
else
    echo -e "${GREEN}[OK] P99 latency: ${P99_LATENCY_MS}ms${NC}"
fi
echo ""

# 2. Check P50/P95 for comparison
echo -e "${BLUE}[2/6] Checking P50 and P95 latency...${NC}"
P50_LATENCY=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.50,rate(http_request_duration_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
P95_LATENCY=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')

P50_MS=$(echo "$P50_LATENCY * 1000" | bc | cut -d. -f1)
P95_MS=$(echo "$P95_LATENCY * 1000" | bc | cut -d. -f1)

echo "P50: ${P50_MS}ms"
echo "P95: ${P95_MS}ms"
echo "P99: ${P99_LATENCY_MS}ms"
echo ""

# 3. Check database slow queries
echo -e "${BLUE}[3/6] Checking for slow database queries...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  pid,
  EXTRACT(EPOCH FROM (now() - query_start)) AS duration_seconds,
  state,
  substring(query, 1, 80) AS query
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state != 'idle'
  AND query_start IS NOT NULL
ORDER BY duration_seconds DESC
LIMIT 5;
" 2>/dev/null || echo "Cannot connect to PostgreSQL"
echo ""

# 4. Check LLM API latency
echo -e "${BLUE}[4/6] Checking LLM API latency...${NC}"
LLM_P95_LATENCY=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(llm_api_latency_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
LLM_P95_MS=$(echo "$LLM_P95_LATENCY * 1000" | bc | cut -d. -f1)

if (( LLM_P95_MS > 10000 )); then
    echo -e "${RED}[CRITICAL] LLM P95 latency: ${LLM_P95_MS}ms${NC}"
elif (( LLM_P95_MS > 5000 )); then
    echo -e "${YELLOW}[WARNING] LLM P95 latency: ${LLM_P95_MS}ms${NC}"
else
    echo -e "${GREEN}[OK] LLM P95 latency: ${LLM_P95_MS}ms${NC}"
fi
echo ""

# 5. Check CPU and memory pressure
echo -e "${BLUE}[5/6] Checking container resources...${NC}"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemPerc}}" | grep lia || echo "No containers found"
echo ""

# 6. Detailed endpoint breakdown
if [[ "$DETAILED" == "true" ]]; then
    echo -e "${BLUE}[6/6] Latency by endpoint (P95, last 5min)...${NC}"
    curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,sum by (path) (rate(http_request_duration_seconds_bucket[5m])))" | jq -r '.data.result[] | "\(.metric.path): \((.value[1] | tonumber * 1000 | floor))ms"' | head -10
    echo ""
fi

# Summary
echo -e "${BLUE}=== Summary & Recommendations ===${NC}"

if (( P99_LATENCY_MS > 2000 )); then
    echo -e "${RED}[CRITICAL] P99 latency >2s - Immediate action required${NC}"
    echo "Recommended actions:"
    echo "  1. Check slow database queries above"
    echo "  2. Review LLM API latency (${LLM_P95_MS}ms)"
    echo "  3. Consider adding database indexes"
    echo "  4. Enable LLM streaming if not already active"
elif (( P99_LATENCY_MS > 1500 )); then
    echo -e "${YELLOW}[WARNING] P99 latency >1.5s - Monitor closely${NC}"
    echo "Recommended actions:"
    echo "  1. Identify slow endpoints (run with --detailed)"
    echo "  2. Check database query performance"
    echo "  3. Review container resource usage"
else
    echo -e "${GREEN}[OK] Latency within acceptable range${NC}"
fi

echo ""
echo "For detailed runbook, see: docs/runbooks/alerts/CriticalLatencyP99.md"
