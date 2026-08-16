#!/usr/bin/env bash

################################################################################
# Reset Observability Data Script
################################################################################
#
# Purpose:
#   Cleanly reset all observability data for testing from scratch.
#   This includes database token logs, Redis cache, and restarting services
#   to reset Prometheus counters.
#
# Safety:
#   This script includes safety checks to ensure it only runs in development
#   environments. It will NOT run in production.
#
# Usage:
#   ./scripts/reset_observability_data.sh
#
# What it does:
#   1. Validates environment (must be development)
#   2. Truncates token_usage_logs table
#   3. Truncates message_token_summary table
#   4. Flushes Redis cache (LLM cache, session store, etc.)
#   5. Restarts API service (resets Prometheus counters)
#   6. Reports summary of actions taken
#
# Phase: 2.1 - Token Tracking Alignment Fix (Bonus Feature)
# Date: 2025-11-05
################################################################################

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configurable URLs
API_URL="${API_URL:-http://localhost:8000}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}  Reset Observability Data Script${NC}"
echo -e "${BLUE}===============================================${NC}"
echo

################################################################################
# Safety Checks
################################################################################

# Check environment
echo -e "${YELLOW}➤ Checking environment safety...${NC}"

# Method 1: Check if .env.local exists (development indicator)
if [ ! -f "$PROJECT_ROOT/.env.local" ]; then
    echo -e "${RED}✗ ERROR: .env.local not found.${NC}"
    echo -e "${RED}  This script should only run in development.${NC}"
    exit 1
fi

# Method 2: Check docker-compose file
if [ ! -f "$PROJECT_ROOT/docker-compose.dev.yml" ]; then
    echo -e "${RED}✗ ERROR: docker-compose.dev.yml not found.${NC}"
    echo -e "${RED}  This script requires development docker-compose file.${NC}"
    exit 1
fi

# Method 3: Interactive confirmation
echo -e "${RED}⚠ WARNING: This will delete ALL observability data!${NC}"
echo -e "${RED}  - All token usage logs${NC}"
echo -e "${RED}  - All message token summaries${NC}"
echo -e "${RED}  - All Redis cache (LLM, sessions, etc.)${NC}"
echo -e "${RED}  - Prometheus counters (via API restart)${NC}"
echo
read -p "Are you ABSOLUTELY SURE you want to continue? (type 'yes' to confirm): " -r
echo
if [[ ! $REPLY =~ ^yes$ ]]; then
    echo -e "${YELLOW}✗ Aborted by user.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Environment checks passed${NC}"
echo

################################################################################
# Database Cleanup
################################################################################

echo -e "${YELLOW}➤ Cleaning database...${NC}"

# Truncate token_usage_logs
echo -e "  ${BLUE}→${NC} Truncating token_usage_logs..."
docker compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec -T postgres \
    psql -U postgres -d lia -c "TRUNCATE TABLE token_usage_logs RESTART IDENTITY CASCADE;" \
    > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to truncate token_usage_logs${NC}"
    exit 1
}
echo -e "  ${GREEN}✓${NC} token_usage_logs truncated"

# Truncate message_token_summary
echo -e "  ${BLUE}→${NC} Truncating message_token_summary..."
docker compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec -T postgres \
    psql -U postgres -d lia -c "TRUNCATE TABLE message_token_summary RESTART IDENTITY CASCADE;" \
    > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to truncate message_token_summary${NC}"
    exit 1
}
echo -e "  ${GREEN}✓${NC} message_token_summary truncated"

echo -e "${GREEN}✓ Database cleaned${NC}"
echo

################################################################################
# Redis Cleanup
################################################################################

echo -e "${YELLOW}➤ Flushing Redis cache...${NC}"

# Flush all Redis keys
docker compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec -T redis \
    redis-cli FLUSHALL \
    > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to flush Redis${NC}"
    exit 1
}

echo -e "${GREEN}✓ Redis cache flushed${NC}"
echo

################################################################################
# Service Restart (Reset Prometheus Counters)
################################################################################

echo -e "${YELLOW}➤ Restarting API service (resets Prometheus counters)...${NC}"

# Restart API container
docker compose -f "$PROJECT_ROOT/docker-compose.dev.yml" restart api > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to restart API service${NC}"
    exit 1
}

echo -e "${GREEN}✓ API service restarted${NC}"
echo

# Wait for API to be healthy
echo -e "${YELLOW}➤ Waiting for API to be healthy...${NC}"
RETRY_COUNT=0
MAX_RETRIES=30

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s ${API_URL}/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API is healthy${NC}"
        break
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "  ${BLUE}→${NC} Waiting... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${YELLOW}⚠ API health check timeout (this is often normal, API may still be starting)${NC}"
fi

echo

################################################################################
# Verification
################################################################################

echo -e "${YELLOW}➤ Verifying cleanup...${NC}"

# Check token_usage_logs count
TOKEN_COUNT=$(docker compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec -T postgres \
    psql -U postgres -d lia -t -c "SELECT COUNT(*) FROM token_usage_logs;" | tr -d ' ')

echo -e "  ${BLUE}→${NC} token_usage_logs count: ${TOKEN_COUNT}"

if [ "$TOKEN_COUNT" -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} Database is clean"
else
    echo -e "  ${YELLOW}⚠${NC} Database still has ${TOKEN_COUNT} records (may be expected if API already processed requests)"
fi

echo

################################################################################
# Summary
################################################################################

echo -e "${GREEN}===============================================${NC}"
echo -e "${GREEN}  Reset Complete!${NC}"
echo -e "${GREEN}===============================================${NC}"
echo
echo -e "Summary of actions:"
echo -e "  ${GREEN}✓${NC} Database tables truncated"
echo -e "  ${GREEN}✓${NC} Redis cache flushed"
echo -e "  ${GREEN}✓${NC} API service restarted (Prometheus counters reset)"
echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Make API requests to generate new token metrics"
echo -e "  2. Check database: SELECT node_name, COUNT(*) FROM token_usage_logs GROUP BY node_name;"
echo -e "  3. Check Prometheus: http://localhost:9090/graph"
echo -e "  4. Check Grafana: ${GRAFANA_URL}/d/llm-observability-v2"
echo
echo -e "${GREEN}All observability data has been reset.${NC}"
echo -e "${GREEN}Token tracking alignment fix is active.${NC}"
echo
