"""
Infrastructure probe endpoints: liveness (``GET /health``) and readiness (``GET /ready``).

Both endpoints live at the application root (outside ``/api/v1``) because they
serve infrastructure, not API consumers: Docker healthchecks, deploy
verification and operators. A third, static endpoint (``GET /api/v1/health``,
see ``src/api/v1/routes.py``) exposes process-alive + version information in
the OpenAPI schema and is unrelated to the probes defined here.

Contract (ADR-115, ``docs/runbooks/alerts/ServiceDown.md``):

- ``GET /health`` — **liveness**. Returns 200 as long as the process can serve
  requests, even when PostgreSQL or Redis are down (the payload degrades to
  ``status: degraded`` with per-dependency detail). Restarting the API cannot
  repair a dependency outage, so orchestrators polling this endpoint (the
  Docker healthchecks in ``docker-compose.{dev,prod}.yml`` and
  ``Dockerfile.prod``) must not kill the container on dependency failures.
- ``GET /ready`` — **readiness**. Returns 200 only when every critical
  dependency (PostgreSQL, Redis) answers a probe, 503 otherwise. This is the
  endpoint deploy verification and user-impact monitoring should poll.

Scope note: readiness deliberately covers PostgreSQL + Redis only. LangGraph
subsystems (checkpointer, agent registry, graph build) can fail at startup
while both probes stay green — after any API (re)start, the startup logs
remain the authoritative signal (see ``infrastructure/claude-cli/CLAUDE.server.md``).
"""

import structlog
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.core.config import settings
from src.core.field_names import FIELD_STATUS
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)

health_router = APIRouter()

# Payload status vocabulary (machine-facing, not user-visible — no i18n).
_STATUS_HEALTHY = "healthy"
_STATUS_UNHEALTHY = "unhealthy"
_STATUS_DEGRADED = "degraded"
_STATUS_READY = "ready"
_STATUS_NOT_READY = "not_ready"

_CHECK_REDIS = "redis"
_CHECK_DATABASE = "database"


async def _probe_dependencies() -> tuple[dict[str, str], bool]:
    """
    Probe the critical dependencies (Redis, PostgreSQL) shared by both endpoints.

    Probe failures must degrade the result, never crash to a 500: raw driver
    exceptions bypass typed wraps (asyncpg auth errors are re-raised unwrapped
    by SQLAlchemy's greenlet bridge; redis-py ConnectionError is NOT the
    builtin ConnectionError), so only a broad except is actually exhaustive.

    Returns:
        Tuple of (per-dependency check results, True when every check passed).
    """
    checks: dict[str, str] = {}
    all_healthy = True

    # Check Redis
    try:
        redis = await get_redis_cache()
        await redis.ping()
        checks[_CHECK_REDIS] = _STATUS_HEALTHY
    except Exception as exc:
        logger.error("health_check_redis_failed", error=str(exc))
        checks[_CHECK_REDIS] = _STATUS_UNHEALTHY
        all_healthy = False

    # Check database
    try:
        # Imported lazily so importing this module never triggers engine
        # creation (unit tests exercise the router without a database).
        from sqlalchemy import text

        from src.infrastructure.database.session import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks[_CHECK_DATABASE] = _STATUS_HEALTHY
    except Exception as exc:
        logger.error("health_check_database_failed", error=str(exc))
        checks[_CHECK_DATABASE] = _STATUS_UNHEALTHY
        all_healthy = False

    return checks, all_healthy


@health_router.get("/health", include_in_schema=False)
async def health_check() -> JSONResponse:
    """
    Liveness probe for container orchestration.

    Always returns HTTP 200 while the process is able to serve requests —
    deliberately, even when PostgreSQL or Redis are down: restarting the API
    cannot repair a dependency outage, and a 503 here would send Docker into a
    restart loop during incidents. Dependency failures are surfaced in the
    payload (``status: degraded`` + per-dependency ``checks``) for humans and
    dashboards; ``GET /ready`` is the endpoint that turns them into a 503.

    Returns:
        JSONResponse (200) with overall status, environment and dependency checks.
    """
    checks, all_healthy = await _probe_dependencies()
    payload = {
        FIELD_STATUS: _STATUS_HEALTHY if all_healthy else _STATUS_DEGRADED,
        "environment": settings.environment,
        "checks": checks,
    }
    return JSONResponse(content=payload, status_code=status.HTTP_200_OK)


@health_router.get("/ready", include_in_schema=False)
async def readiness_check() -> JSONResponse:
    """
    Readiness probe: can the service serve users right now?

    Returns HTTP 200 with ``status: ready`` only when every critical
    dependency (PostgreSQL, Redis) answers its probe, HTTP 503 with
    ``status: not_ready`` otherwise. Poll this endpoint for deploy
    verification and user-impact monitoring; keep container healthchecks on
    ``GET /health`` (liveness — see module docstring).

    Returns:
        JSONResponse (200 or 503) with overall readiness and dependency checks.
    """
    checks, all_healthy = await _probe_dependencies()
    payload = {
        FIELD_STATUS: _STATUS_READY if all_healthy else _STATUS_NOT_READY,
        "environment": settings.environment,
        "checks": checks,
    }
    return JSONResponse(
        content=payload,
        status_code=status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
