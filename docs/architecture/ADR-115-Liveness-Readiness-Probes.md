# ADR-115: Liveness/Readiness Probe Split — /health stays 200, /ready owns the 503

**Status**: ✅ IMPLEMENTED (2026-07-09)
**Author**: Claude Code (Fable 5)
**Related**: `apps/api/src/api/health.py`, [ServiceDown runbook](../runbooks/alerts/ServiceDown.md), [GUIDE_DEPLOYMENT.md](../guides/GUIDE_DEPLOYMENT.md), `infrastructure/claude-cli/CLAUDE.server.md`

## Context

`GET /health` (app root, `src/main.py`) genuinely probed PostgreSQL and Redis,
but a probe failure only ever set the payload status to `degraded` — never
`unhealthy` — so the `status_code = 503 if unhealthy` branch was **unreachable
since inception**. The endpoint therefore behaved as a liveness probe while
carrying the dead contract of a readiness probe, and no readiness endpoint
existed at all: nothing could answer "can the service serve users right now?"
with an HTTP status code.

A consumer census found every prober tolerating (and implicitly relying on)
the always-200 behavior: the Docker healthchecks
(`docker-compose.{dev,prod}.yml`, `Dockerfile.prod`), Taskfile status checks,
monitoring scripts, and manual runbook curls. The `ServiceDown` alert uses the
Prometheus scrape (`up{job="api"}`), not `/health`. Since a 503 was never
observable, no consumer could have depended on it — removing the dead branch
carries no compatibility risk.

Adjacent doc-truth defects fixed in the same change (rule: a doc describing
behavior the code does not have is a bug):

- `GUIDE_DEPLOYMENT.md` documented a **fictional** `src/api/health.py` that
  raised 503 on dependency failure — behavior the real endpoint never had.
- Both compose files justified the API healthcheck's `start_period: 60s` with
  "E5 model loading", but the local E5 model was replaced by Gemini embeddings
  (`context/store.py`). Boot-log measurement (dev, 2026-07-09) shows the real
  cost: alembic migrations ~13s + full app import (LangGraph graph + tool
  registry) ~14s per process — Whisper STT loads lazily on first voice use,
  not at boot.
- `CLAUDE.server.md` (in-container DevOps CLI doctrine) still claimed a single
  uvicorn worker (prod runs 4 per `Dockerfile.prod` CMD) and "no auto-reconnect"
  LangGraph persistence (obsolete since the ADR-111 pools re-check connections
  on checkout).

## Decision

**Split the two concerns into two endpoints, both in a new
`src/api/health.py` module** (the path the deployment guide already
referenced), registered at the app root and excluded from HTTP request
logging (`HTTP_LOG_EXCLUDE_PATHS`):

| Endpoint | Role | Returns |
|---|---|---|
| `GET /health` | **Liveness** | Always `200` while the process serves requests; payload `status: healthy\|degraded` + per-dependency `checks` |
| `GET /ready` | **Readiness** | `200` + `ready` only when PostgreSQL **and** Redis answer their probe; `503` + `not_ready` otherwise |

- **Docker healthchecks stay on `/health`** — restarting the API cannot fix a
  dependency outage, so a dependency failure must never send the container
  into a restart loop.
- **`/ready` is for deploy verification, uptime/user-impact monitoring and
  post-incident checks** (runbooks updated accordingly).
- **Readiness scope is deliberately PostgreSQL + Redis only.** LangGraph
  subsystems (checkpointer, agent registry, graph build) can fail at startup
  while both probes stay green; probing them per-request would be flaky and
  expensive. The compensating control stays: scan startup logs after any API
  (re)start (documented in `CLAUDE.server.md` and the ServiceDown runbook).
- The pre-existing static `GET /api/v1/health` (process-alive + version,
  OpenAPI-documented) is untouched and unrelated.

## Alternatives considered

1. **Make `/health` return 503 on dependency failure** (resurrect the dead
   branch): rejected — every Docker healthcheck polls it; a PostgreSQL outage
   would flip the API container to `unhealthy` and invite restart loops that
   fix nothing.
2. **Keep the dead 503 branch as-is**: rejected — a contract that cannot fire
   is a standing doc-lie and keeps inviting "is this a readiness probe?"
   confusion (this audit finding).
3. **Probe LangGraph subsystems in `/ready`**: rejected — no cheap, reliable
   signal exists (graph build happens at startup; a per-request probe would
   re-run LLM-adjacent wiring). Startup-log scan remains the control.

## Consequences

- Deploy verification and monitoring finally get a real 503 signal
  (`/ready`), demonstrated live: Redis stopped → `/ready` 503 +
  `/health` 200 `degraded`; Redis restarted → both 200.
- `main.py` sheds the endpoint (monolith remediation B1); the probe logic is
  unit-testable without importing `src.main`
  (`tests/unit/api/test_health_endpoints.py`, 8 tests pinning the contract).
- `/ready` joins `/health` and `/metrics` in the HTTP-log exclusion default
  (`HTTP_LOG_EXCLUDE_PATHS_DEFAULT`) and in the `.env` templates. A clean 503
  response on an excluded path produces no request-log line (exclusion only
  yields to unhandled exceptions); each failing probe still logs one
  `health_check_*_failed` ERROR — the desired incident signal.
- Runbooks and guides now document which endpoint to poll for which usage
  (ServiceDown runbook is the canonical table).

## Verification

- 8 unit tests green (all four dependency up/down combinations × both
  endpoints, probes mocked at their lookup points).
- Live demo on the dev stack: `/health` 200 `healthy` and `/ready` 200
  `ready` with all dependencies up; `docker stop lia-redis-dev` →
  `/health` 200 `degraded` (`checks.redis: unhealthy`) and `/ready` 503
  `not_ready`; Redis restarted → both back to 200.
- `docker compose config` valid for both compose files; ruff/black/mypy clean.
