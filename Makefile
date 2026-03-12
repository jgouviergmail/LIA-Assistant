# =============================================================================
# LIA Makefile - Development & Production Commands
# =============================================================================
#
# Usage:
#   make setup      - Initial dev setup (downloads models, etc.)
#   make dev        - Start dev environment
#   make prod-build - Build production images
#   make prod-up    - Start production environment
#   make logs       - View API logs
#   make clean      - Clean up containers and volumes
#
# =============================================================================

.PHONY: setup dev dev-up dev-down dev-restart prod-build prod-up prod-down logs logs-api logs-web clean help

# Default target
.DEFAULT_GOAL := help

# =============================================================================
# DEVELOPMENT
# =============================================================================

## setup: Initial dev setup - downloads ML models
setup:
	@echo "=== LIA Dev Setup ==="
	@bash scripts/setup-dev.sh

## dev: Start dev environment (alias for dev-up)
dev: dev-up

## dev-up: Start dev containers
dev-up:
	@echo "Starting dev environment..."
	docker compose -f docker-compose.dev.yml up -d
	@echo "Dev environment started. API: https://localhost:8000, Web: https://localhost:3000"

## dev-down: Stop dev containers
dev-down:
	docker compose -f docker-compose.dev.yml down

## dev-restart: Restart dev containers
dev-restart:
	docker compose -f docker-compose.dev.yml restart

## dev-rebuild: Rebuild and restart dev containers
dev-rebuild:
	docker compose -f docker-compose.dev.yml up -d --build --force-recreate

# =============================================================================
# PRODUCTION
# =============================================================================

## prod-build: Build production Docker images
prod-build:
	@echo "Building production images (includes STT model download)..."
	docker compose -f docker-compose.prod.yml build

## prod-up: Start production environment
prod-up:
	docker compose -f docker-compose.prod.yml up -d

## prod-down: Stop production environment
prod-down:
	docker compose -f docker-compose.prod.yml down

## prod-logs: View production logs
prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

# =============================================================================
# LOGS & MONITORING
# =============================================================================

## logs: View all dev logs
logs:
	docker compose -f docker-compose.dev.yml logs -f

## logs-api: View API logs only
logs-api:
	docker compose -f docker-compose.dev.yml logs -f api

## logs-web: View Web logs only
logs-web:
	docker compose -f docker-compose.dev.yml logs -f web

# =============================================================================
# MAINTENANCE
# =============================================================================

## clean: Stop containers and remove volumes
clean:
	@echo "Stopping containers..."
	docker compose -f docker-compose.dev.yml down -v 2>/dev/null || true
	docker compose -f docker-compose.prod.yml down -v 2>/dev/null || true
	@echo "Cleaned up."

## clean-models: Remove downloaded ML models
clean-models:
	rm -rf apps/api/models/whisper-small
	rm -rf apps/web/public/models/whisper-tiny-en
	rm -rf apps/web/public/models/sherpa-wasm/*.wasm
	rm -rf apps/web/public/models/sherpa-wasm/*.data

## download-models: Download all ML models
download-models:
	@echo "Downloading ML models..."
	@bash scripts/download-whisper-wasm-model.sh
	@echo "Models downloaded."

## prune: Docker system prune
prune:
	docker system prune -f

# =============================================================================
# TESTING
# =============================================================================

## test-api: Run API tests
test-api:
	docker compose -f docker-compose.dev.yml exec api pytest tests/ -v

## test-web: Run Web tests
test-web:
	docker compose -f docker-compose.dev.yml exec web pnpm test

# =============================================================================
# UTILITIES
# =============================================================================

## shell-api: Open shell in API container
shell-api:
	docker compose -f docker-compose.dev.yml exec api bash

## shell-web: Open shell in Web container
shell-web:
	docker compose -f docker-compose.dev.yml exec web sh

## db-shell: Open PostgreSQL shell
db-shell:
	docker compose -f docker-compose.dev.yml exec postgres psql -U lia -d lia

## redis-cli: Open Redis CLI
redis-cli:
	docker compose -f docker-compose.dev.yml exec redis redis-cli -a $${REDIS_PASSWORD}

# =============================================================================
# HELP
# =============================================================================

## help: Show this help message
help:
	@echo ""
	@echo "LIA - Available Commands:"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Quick Start:"
	@echo "  1. make setup    # First time setup"
	@echo "  2. make dev      # Start development"
	@echo ""
