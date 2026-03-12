#!/bin/bash
# Diagnostic script for disk space (DiskSpaceCritical runbook)
# Usage: ./diagnose_disk_space.sh [--detailed]

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

echo -e "${BLUE}=== Disk Space Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

# 1. Check current disk usage
echo -e "${BLUE}[1/6] Checking disk usage...${NC}"
USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')

if (( USAGE > 90 )); then
    echo -e "${RED}[CRITICAL] Disk usage: ${USAGE}% (threshold: 90%)${NC}"
elif (( USAGE > 80 )); then
    echo -e "${YELLOW}[WARNING] Disk usage: ${USAGE}% (threshold: 80%)${NC}"
else
    echo -e "${GREEN}[OK] Disk usage: ${USAGE}%${NC}"
fi

df -h / | grep -v Filesystem
echo ""

# 2. Check largest directories
echo -e "${BLUE}[2/6] Top 10 largest directories...${NC}"
docker-compose exec -T api du -h --max-depth=2 / 2>/dev/null | sort -hr | head -10 || echo "Cannot analyze directory sizes"
echo ""

# 3. Check Docker disk usage
echo -e "${BLUE}[3/6] Docker disk usage...${NC}"
docker system df
echo ""

# 4. Check PostgreSQL WAL size
echo -e "${BLUE}[4/6] PostgreSQL WAL directory size...${NC}"
WAL_SIZE=$(docker-compose exec -T postgres du -sh /var/lib/postgresql/data/pg_wal 2>/dev/null | cut -f1)
echo "WAL size: $WAL_SIZE"

WAL_COUNT=$(docker-compose exec -T postgres ls -1 /var/lib/postgresql/data/pg_wal 2>/dev/null | wc -l)
echo "WAL segments: $WAL_COUNT"

if (( WAL_COUNT > 100 )); then
    echo -e "${YELLOW}[WARNING] High number of WAL segments (>100)${NC}"
fi
echo ""

# 5. Check log files
echo -e "${BLUE}[5/6] Large log files...${NC}"
echo "Docker container logs:"
find /var/lib/docker/containers -name "*-json.log" -exec ls -lh {} + 2>/dev/null | awk '{if ($5 ~ /M|G/) print $9, $5}' | sort -k2 -hr | head -5 || echo "Cannot access Docker logs"
echo ""

# 6. Detailed analysis
if [[ "$DETAILED" == "true" ]]; then
    echo -e "${BLUE}[6/6] Detailed disk analysis...${NC}"

    echo "Database size:"
    docker-compose exec -T postgres psql -U lia -c "
    SELECT
      pg_database.datname,
      pg_size_pretty(pg_database_size(pg_database.datname)) AS size
    FROM pg_database
    ORDER BY pg_database_size(pg_database.datname) DESC;
    " 2>/dev/null || echo "Cannot query database size"

    echo ""
    echo "Largest tables:"
    docker-compose exec -T postgres psql -U lia -c "
    SELECT
      schemaname,
      tablename,
      pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
    FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
    LIMIT 5;
    " 2>/dev/null || echo "Cannot query table sizes"
    echo ""
fi

# Summary
echo -e "${BLUE}=== Summary & Recommendations ===${NC}"

if (( USAGE > 90 )); then
    echo -e "${RED}[CRITICAL] Disk >90% full - Immediate cleanup required${NC}"
    echo "Recommended actions:"
    echo "  1. Purge Docker logs: sudo truncate -s 0 /var/lib/docker/containers/*/*-json.log"
    echo "  2. Clean Docker artifacts: docker system prune -a --volumes --force"
    echo "  3. Check WAL directory: ${WAL_SIZE} (${WAL_COUNT} segments)"
    echo "  4. Review large directories above"
elif (( USAGE > 80 )); then
    echo -e "${YELLOW}[WARNING] Disk >80% full - Plan cleanup${NC}"
    echo "Recommended actions:"
    echo "  1. Review top disk consumers above"
    echo "  2. Implement log rotation: see docs/runbooks/alerts/DiskSpaceCritical.md"
    echo "  3. Schedule regular cleanup: ./cleanup_disk_space.sh"
else
    echo -e "${GREEN}[OK] Disk usage healthy${NC}"
fi

echo ""
echo "For detailed runbook, see: docs/runbooks/alerts/DiskSpaceCritical.md"
