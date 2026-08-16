#!/bin/bash
# Diagnostic script for checkpoint performance (CheckpointSaveSlowCritical runbook)

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Checkpoint Performance Diagnostics ===${NC}"
echo "Timestamp: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""

echo -e "${BLUE}[1/3] Checkpoint save latency (P95)...${NC}"
CHECKPOINT_P95=$(curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(checkpoint_save_duration_seconds_bucket[5m]))" | jq -r '.data.result[0].value[1] // "0"')
CHECKPOINT_MS=$(echo "$CHECKPOINT_P95 * 1000" | bc | cut -d. -f1)

if (( CHECKPOINT_MS > 5000 )); then
    echo -e "${RED}[CRITICAL] Checkpoint P95: ${CHECKPOINT_MS}ms (threshold: 3000ms)${NC}"
elif (( CHECKPOINT_MS > 3000 )); then
    echo -e "${YELLOW}[WARNING] Checkpoint P95: ${CHECKPOINT_MS}ms (threshold: 3000ms)${NC}"
else
    echo -e "${GREEN}[OK] Checkpoint P95: ${CHECKPOINT_MS}ms${NC}"
fi
echo ""

echo -e "${BLUE}[2/3] Checkpoint sizes (top 5)...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  conversation_id,
  pg_size_pretty(length(checkpoint_data::text)::bigint) AS size,
  created_at
FROM checkpoints
ORDER BY length(checkpoint_data::text) DESC
LIMIT 5;
" 2>/dev/null || echo "Cannot query checkpoint sizes"
echo ""

echo -e "${BLUE}[3/3] Database write performance...${NC}"
docker-compose exec -T postgres psql -U lia -c "
SELECT
  schemaname,
  tablename,
  n_tup_ins + n_tup_upd AS write_ops,
  n_dead_tup,
  last_autovacuum
FROM pg_stat_user_tables
WHERE tablename = 'checkpoints';
" 2>/dev/null || echo "Cannot query table stats"
echo ""

echo "For detailed runbook, see: docs/runbooks/alerts/CheckpointSaveSlowCritical.md"
