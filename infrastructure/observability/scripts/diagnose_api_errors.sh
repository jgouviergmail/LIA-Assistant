#!/bin/bash
# Diagnostic script for API errors (HighErrorRate runbook)
# Usage: ./diagnose_api_errors.sh [--detailed]

set -euo pipefail

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DETAILED=false
if [[ "${1:-}" == "--detailed" ]]; then
    DETAILED=true
fi

echo -e "${BLUE}=== API Error Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# 1. Check current error rate
echo -e "${BLUE}[1/7] Checking current API error rate...${NC}"
ERROR_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total{status=~\"5..\"}[5m]))*100/sum(rate(http_requests_total[5m]))" | jq -r '.data.result[0].value[1] // "0"')
ERROR_RATE_INT=${ERROR_RATE%.*}

if (( ERROR_RATE_INT > 10 )); then
    echo -e "${RED}[CRITICAL] Error rate: ${ERROR_RATE}% (threshold: 3%)${NC}"
elif (( ERROR_RATE_INT > 3 )); then
    echo -e "${YELLOW}[WARNING] Error rate: ${ERROR_RATE}% (threshold: 3%)${NC}"
else
    echo -e "${GREEN}[OK] Error rate: ${ERROR_RATE}%${NC}"
fi
echo ""

# 2. Check database connection pool
echo -e "${BLUE}[2/7] Checking database connection pool...${NC}"
DB_CONNECTIONS=$(docker-compose exec -T postgres psql -U lia -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia';" 2>/dev/null || echo "N/A")
DB_MAX_CONNECTIONS=$(docker-compose exec -T postgres psql -U lia -t -c "SHOW max_connections;" 2>/dev/null || echo "100")

DB_CONNECTIONS_TRIMMED=$(echo "$DB_CONNECTIONS" | tr -d ' ')
DB_MAX_CONNECTIONS_TRIMMED=$(echo "$DB_MAX_CONNECTIONS" | tr -d ' ')

if [[ "$DB_CONNECTIONS_TRIMMED" != "N/A" ]]; then
    DB_USAGE=$((DB_CONNECTIONS_TRIMMED * 100 / DB_MAX_CONNECTIONS_TRIMMED))
    if (( DB_USAGE > 90 )); then
        echo -e "${RED}[CRITICAL] DB connections: ${DB_CONNECTIONS_TRIMMED}/${DB_MAX_CONNECTIONS_TRIMMED} (${DB_USAGE}%)${NC}"
    elif (( DB_USAGE > 70 )); then
        echo -e "${YELLOW}[WARNING] DB connections: ${DB_CONNECTIONS_TRIMMED}/${DB_MAX_CONNECTIONS_TRIMMED} (${DB_USAGE}%)${NC}"
    else
        echo -e "${GREEN}[OK] DB connections: ${DB_CONNECTIONS_TRIMMED}/${DB_MAX_CONNECTIONS_TRIMMED} (${DB_USAGE}%)${NC}"
    fi
else
    echo -e "${RED}[ERROR] Cannot connect to PostgreSQL${NC}"
fi
echo ""

# 3. Check LLM API health
echo -e "${BLUE}[3/7] Checking LLM API health...${NC}"
LLM_ERROR_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=sum(rate(llm_api_calls_total{result=\"error\"}[5m]))*100/sum(rate(llm_api_calls_total[5m]))" | jq -r '.data.result[0].value[1] // "0"')
LLM_ERROR_RATE_INT=${LLM_ERROR_RATE%.*}

if (( LLM_ERROR_RATE_INT > 5 )); then
    echo -e "${RED}[CRITICAL] LLM error rate: ${LLM_ERROR_RATE}%${NC}"
elif (( LLM_ERROR_RATE_INT > 1 )); then
    echo -e "${YELLOW}[WARNING] LLM error rate: ${LLM_ERROR_RATE}%${NC}"
else
    echo -e "${GREEN}[OK] LLM error rate: ${LLM_ERROR_RATE}%${NC}"
fi
echo ""

# 4. Check container resource usage
echo -e "${BLUE}[4/7] Checking container resource usage...${NC}"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep lia || echo "No containers found"
echo ""

# 5. Check recent error logs
echo -e "${BLUE}[5/7] Recent error logs (last 20 errors)...${NC}"
docker-compose logs --tail=100 api 2>/dev/null | grep -i "error\|exception\|traceback" | tail -20 || echo "No recent errors found"
echo ""

# 6. Check error breakdown by status code
if [[ "$DETAILED" == "true" ]]; then
    echo -e "${BLUE}[6/7] Error breakdown by status code (last 5min)...${NC}"
    curl -s "http://localhost:9090/api/v1/query?query=sum by (status) (rate(http_requests_total{status=~\"5..\"}[5m]))" | jq -r '.data.result[] | "\(.metric.status): \(.value[1])"'
    echo ""
fi

# 7. Check container health
echo -e "${BLUE}[7/7] Container health status...${NC}"
docker-compose ps | grep -E "api|postgres|redis" || echo "Services not running"
echo ""

# Summary and recommendations
echo -e "${BLUE}=== Summary & Recommendations ===${NC}"

if (( ERROR_RATE_INT > 10 )); then
    echo -e "${RED}[CRITICAL] Error rate >10% - Immediate action required${NC}"
    echo "Recommended actions:"
    echo "  1. Check database connection pool (current: ${DB_CONNECTIONS_TRIMMED}/${DB_MAX_CONNECTIONS_TRIMMED})"
    echo "  2. Restart API: docker-compose restart api"
    echo "  3. Check recent logs: docker-compose logs api --tail=100"
elif (( ERROR_RATE_INT > 3 )); then
    echo -e "${YELLOW}[WARNING] Error rate >3% - Monitor closely${NC}"
    echo "Recommended actions:"
    echo "  1. Review error logs above for patterns"
    echo "  2. Check LLM API status (error rate: ${LLM_ERROR_RATE}%)"
    echo "  3. Monitor database connection pool"
else
    echo -e "${GREEN}[OK] Error rate within acceptable range${NC}"
fi

echo ""
echo "For detailed runbook, see: docs/runbooks/alerts/HighErrorRate.md"
echo "Run with --detailed flag for extended diagnostics"
