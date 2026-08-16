#!/bin/bash
# Diagnostic script for database connections (CriticalDatabaseConnections runbook)
# Usage: ./diagnose_db_connections.sh [--detailed]

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

echo -e "${BLUE}=== Database Connection Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# 1. Check current connection count
echo -e "${BLUE}[1/6] Checking database connection pool...${NC}"
CURRENT_CONNECTIONS=$(docker-compose exec -T postgres psql -U lia -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia';" 2>/dev/null | tr -d ' ')
MAX_CONNECTIONS=$(docker-compose exec -T postgres psql -U lia -t -c "SHOW max_connections;" 2>/dev/null | tr -d ' ')

if [[ -n "$CURRENT_CONNECTIONS" && -n "$MAX_CONNECTIONS" ]]; then
    USAGE_PERCENT=$((CURRENT_CONNECTIONS * 100 / MAX_CONNECTIONS))

    echo "Current connections: $CURRENT_CONNECTIONS"
    echo "Max connections: $MAX_CONNECTIONS"
    echo "Usage: ${USAGE_PERCENT}%"

    if (( USAGE_PERCENT > 85 )); then
        echo -e "${RED}[CRITICAL] Connection pool >85% - Risk of exhaustion${NC}"
    elif (( USAGE_PERCENT > 70 )); then
        echo -e "${YELLOW}[WARNING] Connection pool >70% - Monitor closely${NC}"
    else
        echo -e "${GREEN}[OK] Connection pool usage normal${NC}"
    fi
else
    echo -e "${RED}[ERROR] Cannot connect to PostgreSQL${NC}"
fi
echo ""

# 2. Check connection states
echo -e "${BLUE}[2/6] Connection states breakdown...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT state, COUNT(*) as count
FROM pg_stat_activity
WHERE datname = 'lia'
GROUP BY state
ORDER BY count DESC;
" 2>/dev/null || echo "Cannot query connection states"
echo ""

# 3. Check for long-running transactions
echo -e "${BLUE}[3/6] Long-running transactions (>1 min)...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  pid,
  usename,
  application_name,
  state,
  EXTRACT(EPOCH FROM (now() - xact_start)) AS duration_seconds,
  substring(query, 1, 100) AS query
FROM pg_stat_activity
WHERE datname = 'lia'
  AND xact_start IS NOT NULL
  AND now() - xact_start > interval '1 minute'
ORDER BY xact_start ASC
LIMIT 10;
" 2>/dev/null || echo "No long transactions found"
echo ""

# 4. Check for idle connections
echo -e "${BLUE}[4/6] Idle connections...${NC}"
IDLE_CONNECTIONS=$(docker-compose exec -T postgres psql -U lia -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='lia' AND state='idle';" 2>/dev/null | tr -d ' ')

if [[ -n "$IDLE_CONNECTIONS" ]]; then
    echo "Idle connections: $IDLE_CONNECTIONS"
    if (( IDLE_CONNECTIONS > 20 )); then
        echo -e "${YELLOW}[WARNING] High number of idle connections${NC}"
    fi
else
    echo "Cannot query idle connections"
fi
echo ""

# 5. Check for connection leaks (idle in transaction)
echo -e "${BLUE}[5/6] Checking for connection leaks (idle in transaction)...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  pid,
  usename,
  application_name,
  state,
  EXTRACT(EPOCH FROM (now() - state_change)) AS idle_seconds,
  substring(query, 1, 80) AS last_query
FROM pg_stat_activity
WHERE datname = 'lia'
  AND state = 'idle in transaction'
  AND now() - state_change > interval '30 seconds'
ORDER BY state_change ASC
LIMIT 10;
" 2>/dev/null || echo "No connection leaks detected"
echo ""

# 6. Detailed connection info
if [[ "$DETAILED" == "true" ]]; then
    echo -e "${BLUE}[6/6] Detailed connection information...${NC}"
    docker-compose exec -T postgres psql -U lia -c "
    SELECT
      pid,
      usename,
      application_name,
      client_addr,
      state,
      EXTRACT(EPOCH FROM (now() - backend_start)) AS connection_age_seconds,
      substring(query, 1, 60) AS query
    FROM pg_stat_activity
    WHERE datname = 'lia'
    ORDER BY backend_start ASC
    LIMIT 20;
    " 2>/dev/null
    echo ""
fi

# Summary
echo -e "${BLUE}=== Summary & Recommendations ===${NC}"

if [[ -n "$CURRENT_CONNECTIONS" && -n "$MAX_CONNECTIONS" ]]; then
    USAGE_PERCENT=$((CURRENT_CONNECTIONS * 100 / MAX_CONNECTIONS))

    if (( USAGE_PERCENT > 85 )); then
        echo -e "${RED}[CRITICAL] Connection pool >85% - Immediate action required${NC}"
        echo "Recommended actions:"
        echo "  1. Kill idle connections: SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state='idle' AND state_change < NOW() - INTERVAL '5 minutes';"
        echo "  2. Restart API: docker-compose restart api"
        echo "  3. Increase max_connections in PostgreSQL config"
    elif (( USAGE_PERCENT > 70 )); then
        echo -e "${YELLOW}[WARNING] Connection pool >70% - Monitor closely${NC}"
        echo "Recommended actions:"
        echo "  1. Review long-running transactions above"
        echo "  2. Check for connection leaks (idle in transaction)"
        echo "  3. Consider increasing pool size"
    else
        echo -e "${GREEN}[OK] Connection pool usage healthy${NC}"
    fi

    if [[ -n "$IDLE_CONNECTIONS" ]] && (( IDLE_CONNECTIONS > 20 )); then
        echo ""
        echo -e "${YELLOW}Note: ${IDLE_CONNECTIONS} idle connections detected - may indicate connection pool misconfiguration${NC}"
    fi
else
    echo -e "${RED}[ERROR] Cannot connect to PostgreSQL - database may be down${NC}"
fi

echo ""
echo "For detailed runbook, see: docs/runbooks/alerts/CriticalDatabaseConnections.md"
