#!/bin/bash
# Diagnostic script for database health (DatabaseDown runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Database Health Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/4] PostgreSQL availability...${NC}"
if docker-compose exec -T postgres pg_isready -U lia 2>/dev/null | grep -q "accepting connections"; then
    echo -e "${GREEN}[OK] PostgreSQL accepting connections${NC}"
else
    echo -e "${RED}[CRITICAL] PostgreSQL not responding${NC}"
fi
echo ""

echo -e "${BLUE}[2/4] Database size and activity...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  pg_database.datname,
  pg_size_pretty(pg_database_size(pg_database.datname)) AS size,
  numbackends AS connections
FROM pg_database
LEFT JOIN pg_stat_database ON pg_database.datname = pg_stat_database.datname
WHERE pg_database.datname = 'lia';
" 2>/dev/null || echo "Cannot query database"
echo ""

echo -e "${BLUE}[3/4] Active queries...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  pid,
  state,
  EXTRACT(EPOCH FROM (now() - query_start)) AS duration_sec,
  substring(query, 1, 60) AS query
FROM pg_stat_activity
WHERE datname = 'lia' AND state != 'idle'
ORDER BY duration_sec DESC
LIMIT 5;
" 2>/dev/null || echo "Cannot query activity"
echo ""

echo -e "${BLUE}[4/4] Recent PostgreSQL errors...${NC}"
docker-compose logs --tail=50 postgres 2>/dev/null | grep -i "error\|fatal" || echo "No recent errors"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/DatabaseDown.md"
