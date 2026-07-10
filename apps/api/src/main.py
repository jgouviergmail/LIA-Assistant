"""
FastAPI application entrypoint.
Configures middleware, routes, observability and lifecycle events.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.health import health_router
from src.api.v1.routes import api_router
from src.core.bootstrap import log_event_loop_configuration, log_rate_limiting_status
from src.core.config import settings
from src.core.constants import (
    API_VERSION,
    RATE_LIMIT_ENDPOINT_AUTH_LOGIN,
    RATE_LIMIT_ENDPOINT_AUTH_REGISTER,
    RATE_LIMIT_ENDPOINT_CHAT_STREAM,
)
from src.core.field_names import FIELD_STATUS
from src.core.middleware import setup_middleware
from src.core.rate_limit_config import build_default_limit, rate_limiting_enabled
from src.infrastructure.observability.logging import configure_logging
from src.infrastructure.observability.metrics import PrometheusMiddleware, metrics_endpoint
from src.infrastructure.observability.tracing import configure_tracing
from src.infrastructure.startup import (
    agents,
    caches,
    integrations,
    observability,
    registries,
    schedulers,
    shutdown,
)

# Configure logging before anything else
configure_logging()
logger = structlog.get_logger(__name__)


# Rate limiter with centralized configuration
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[build_default_limit(settings)],
    enabled=rate_limiting_enabled(settings),
)


def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors.

    Returns structured JSON response with retry information.
    """
    # Extract endpoint path for context-specific messaging
    endpoint_path = request.url.path

    # Determine endpoint type for better messaging
    endpoint_type = "default"
    if RATE_LIMIT_ENDPOINT_AUTH_LOGIN in endpoint_path:
        endpoint_type = "auth_login"
    elif RATE_LIMIT_ENDPOINT_AUTH_REGISTER in endpoint_path:
        endpoint_type = "auth_register"
    elif RATE_LIMIT_ENDPOINT_CHAT_STREAM in endpoint_path:
        endpoint_type = "sse"

    from src.core.rate_limit_config import get_rate_limit_message
    from src.infrastructure.observability.metrics import http_rate_limit_hits_total

    error_message = get_rate_limit_message(endpoint_type)

    # Track rate limit hit in metrics
    http_rate_limit_hits_total.labels(
        endpoint=endpoint_path,
        endpoint_type=endpoint_type,
    ).inc()

    # Log rate limit hit for monitoring
    logger.warning(
        "rate_limit_exceeded",
        endpoint=endpoint_path,
        remote_addr=get_remote_address(request),
        endpoint_type=endpoint_type,
    )

    return JSONResponse(
        status_code=429,
        content={
            **error_message,
            "retry_after": getattr(exc, "retry_after", 60),  # Default 60 seconds
        },
        headers={
            "Retry-After": str(getattr(exc, "retry_after", 60)),
        },
    )


# Scheduler for background tasks
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    Handles startup and shutdown events.

    Every step lives in src/infrastructure/startup/ (one module per
    subsystem, one function per contiguous segment — ADR-123); this function
    remains the SINGLE orchestration point and the only place where ordering
    is decided.
    """
    # ------------------------------------------------------------------
    # STARTUP ORDER DEPENDENCIES (do not reorder without reading this):
    # 1. Domain models first — SQLAlchemy mappers must be fully configured
    #    before any query (string-referenced relationships).
    # 2. Metrics server, then fail-fast validations + tool schemas, before
    #    anything touches LLM or tools: die at boot, not at first request.
    # 3. Redis before the pricing caches, leader election and the cache
    #    invalidation subscriber (they all need the connection).
    # 4. LLM config + model capabilities caches before any get_llm() call
    #    (agent registry, semantic selector, graph build, currency sync).
    # 5. Checkpointer before AgentRegistry (injected at construction).
    # 6. AgentRegistry before MCP — MCP registers its tools INTO the registry.
    # 7. MCP before the semantic tool selector (embeddings must cover MCP
    #    tools); selector before the graph build that consumes it.
    # 8. ALL scheduler jobs — including browser cleanup, registered with the
    #    agents — before schedulers.init_scheduler(): scheduler.start()
    #    happens inside the leader elector, which also logs the job summary.
    # SHUTDOWN: drain chat producers FIRST (they need checkpointer/DB/Redis
    # still alive — ADR-117); Redis closes LAST (the drain and the
    # invalidation subscriber both depend on it).
    # ------------------------------------------------------------------

    # Startup
    registries.import_domain_models()

    logger.info(
        "application_startup",
        environment=settings.environment,
        debug=settings.debug,
    )

    # Log event loop configuration (Windows-specific fix for psycopg v3)
    log_event_loop_configuration()

    observability.start_metrics_server()
    registries.run_failfast_validations()

    # Log rate limiting configuration
    log_rate_limiting_status()

    registries.init_tool_schemas()

    await caches.init_redis()
    await caches.init_pricing_caches()
    checkpointer = await agents.init_checkpointer()
    await caches.init_config_caches()

    registry = await agents.init_agent_registry(checkpointer, scheduler)
    mcp_manager = await integrations.init_mcp(registry)
    await integrations.init_user_mcp_pool()
    telegram_bot = await integrations.init_telegram_bot()
    await agents.init_semantic_services(registry)
    await agents.init_agent_graph()

    observability.init_langfuse()
    await integrations.sync_currency_rates_at_startup()
    await integrations.index_system_rag_spaces()

    leader_elector = await schedulers.init_scheduler(scheduler)

    lifetime_metrics_task = observability.start_lifetime_metrics()
    cache_invalidation_task = caches.start_cache_invalidation_subscriber()

    logger.info("application_ready")

    yield

    # Shutdown
    logger.info("application_shutdown")

    await shutdown.shutdown_application(
        shutdown.StartupHandles(
            leader_elector=leader_elector,
            mcp_manager=mcp_manager,
            telegram_bot=telegram_bot,
            lifetime_metrics_task=lifetime_metrics_task,
            cache_invalidation_task=cache_invalidation_task,
        )
    )


# Create FastAPI application
app = FastAPI(
    title="LIA API",
    description="AI Companion Platform Backend API",
    version=API_VERSION,  # PHASE 2.1: Use constant instead of hardcoded value
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# Configure tracing BEFORE adding other middlewares
# This must be done before app startup but after app creation
try:
    configure_tracing(app)
except (RuntimeError, ImportError, ValueError) as exc:
    logger.error("tracing_configuration_failed", error=str(exc), exc_info=True)

# Setup middleware
setup_middleware(app)

# Add Prometheus metrics middleware
app.add_middleware(PrometheusMiddleware)

# Add rate limiter with custom error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)


# Pydantic / FastAPI request validation error metric (dashboard 16).
# Counts 422 validation errors by field + error_type to surface bad-payload patterns.
@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Count validation errors then return FastAPI's default 422 response.

    Args:
        request: Incoming request (unused — kept for signature compliance).
        exc: The validation error raised by FastAPI/Pydantic.

    Returns:
        422 JSONResponse with the standard `detail` error structure.
    """
    del request  # unused
    # metrics must never break the handler
    with suppress(Exception):
        from src.infrastructure.observability.metrics_errors import (
            validation_errors_total,
        )

        # Cap at 10 errors per request to avoid cardinality blow-up on huge bodies.
        for err in exc.errors()[:10]:
            field = ".".join(str(p) for p in err.get("loc", ())) or "unknown"
            # Keep only the leaf field name and truncate to bound cardinality.
            field_leaf = field.rsplit(".", 1)[-1][:40]
            error_type = err.get("type", "unknown")[:40]
            validation_errors_total.labels(field=field_leaf, error_type=error_type).inc()

    # jsonable_encoder mirrors FastAPI's default handler: exc.errors() may
    # embed raw exception objects (ctx.error from field_validator ValueError),
    # which json.dumps cannot serialize — returning them raw turned every
    # such 422 into a 500.
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())},
    )


# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)

# Infrastructure probes: liveness (/health) + readiness (/ready) — src/api/health.py
app.include_router(health_router)

# Metrics endpoint
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)


# Root endpoint
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str | None]:
    """Root endpoint with API information."""
    return {
        "name": "LIA API",
        "version": API_VERSION,
        FIELD_STATUS: "operational",
        "environment": settings.environment,
        "docs": "/docs" if not settings.is_production else None,
    }


if __name__ == "__main__":
    import sys
    from typing import Literal

    import uvicorn

    # Configure event loop BEFORE uvicorn creates its own
    # This fixes psycopg v3 incompatibility with Windows ProactorEventLoop
    loop_type: Literal["asyncio", "uvloop", "auto", "none"] = "asyncio"  # Default for Unix/Linux

    if sys.platform == "win32":
        # On Windows, force SelectorEventLoop via asyncio policy
        # Uvicorn will respect this policy when creating its event loop
        import asyncio

        # CRITICAL: Set policy BEFORE uvicorn.run()
        # Uvicorn uses asyncio.new_event_loop() which respects the policy
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        loop=loop_type,  # Use asyncio (respects policy on Windows)
    )
