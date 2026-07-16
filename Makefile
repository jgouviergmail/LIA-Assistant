# =============================================================================
# LIA Makefile — thin compatibility shim over Task (audit F022)
# =============================================================================
#
# ⚠️  Task is the CANONICAL build interface (see Taskfile.yml and CLAUDE.md).
#     This Makefile exists only so that `make <cmd>` muscle memory keeps working;
#     every target below DELEGATES to the matching `task` target so the two
#     interfaces can never drift again. Prefer `task <cmd>` directly — run
#     `task --list` to see everything available.
#
#     Requires Task: https://taskfile.dev  (installed by `task setup` prereqs).
# =============================================================================

.PHONY: setup dev dev-up dev-down dev-restart dev-rebuild prod-build prod-up \
        prod-down prod-logs logs logs-api logs-web clean clean-models \
        download-models prune test-api test-web shell-api shell-web db-shell \
        redis-cli help

.DEFAULT_GOAL := help

# -----------------------------------------------------------------------------
# Delegating targets — single source of truth is the matching Task target.
# -----------------------------------------------------------------------------

## setup: Initial dev setup (delegates to `task setup`)
setup:
	task setup

## dev: Start dev environment (delegates to `task dev:detach`)
dev: dev-up
dev-up:
	task dev:detach

## dev-down: Stop dev containers (delegates to `task stop`)
dev-down:
	task stop

## dev-restart: Restart the dev stack (stop + start, via Task)
dev-restart:
	task stop
	task dev:detach

## prod-build: Build production Docker images (delegates to `task build`)
prod-build:
	task build

## prod-up: Start production stack locally (delegates to `task deploy`)
prod-up:
	task deploy

## logs: Tail all dev logs (delegates to `task logs`)
logs:
	task logs

## logs-api: Tail API logs (delegates to `task logs:api`)
logs-api:
	task logs:api

## logs-web: Tail Web logs (delegates to `task logs:web`)
logs-web:
	task logs:web

## test-api: Run backend unit tests (delegates to `task test:backend:unit`)
test-api:
	task test:backend:unit

## test-web: Run frontend tests (delegates to `task test:frontend`)
test-web:
	task test:frontend

## shell-api: Shell into the API container (delegates to `task shell:api`)
shell-api:
	task shell:api

## db-shell: PostgreSQL shell (delegates to `task shell:db` — correct dev role)
db-shell:
	task shell:db

## redis-cli: Redis CLI (delegates to `task shell:redis`)
redis-cli:
	task shell:redis

# -----------------------------------------------------------------------------
# Make-only conveniences (no Task equivalent — not a divergence risk).
# -----------------------------------------------------------------------------

## dev-rebuild: Rebuild and restart dev containers
dev-rebuild:
	docker compose -f docker-compose.dev.yml up -d --build --force-recreate

## prod-down: Stop the local production stack
prod-down:
	docker compose -f docker-compose.prod.yml down

## prod-logs: Tail local production logs
prod-logs:
	docker compose -f docker-compose.prod.yml logs -f

## clean: Stop containers and remove volumes (dev + prod)
clean:
	@docker compose -f docker-compose.dev.yml down -v 2>/dev/null || true
	@docker compose -f docker-compose.prod.yml down -v 2>/dev/null || true
	@echo "Cleaned up."

## clean-models: Remove downloaded ML models
clean-models:
	rm -rf apps/api/models/whisper-small
	rm -rf apps/web/public/models/whisper-tiny-en
	rm -rf apps/web/public/models/sherpa-wasm/*.wasm
	rm -rf apps/web/public/models/sherpa-wasm/*.data

## download-models: Download all ML models
download-models:
	@bash scripts/download-whisper-wasm-model.sh

## prune: Docker system prune
prune:
	docker system prune -f

## shell-web: Shell into the Web container
shell-web:
	docker compose -f docker-compose.dev.yml exec web sh

## help: Show this help message
help:
	@echo ""
	@echo "LIA — Make targets (thin shim over Task; prefer 'task <cmd>'):"
	@echo ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## /  /' | column -t -s ':'
	@echo ""
	@echo "Canonical interface: task --list"
	@echo ""
