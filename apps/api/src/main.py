"""
FastAPI application entrypoint.
Configures middleware, routes, observability and lifecycle events.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.v1.routes import api_router
from src.core.bootstrap import (
    log_event_loop_configuration,
    log_rate_limiting_status,
    register_tool_schemas,
    validate_llm_configuration,
    validate_tool_error_codes,
)
from src.core.config import settings
from src.core.constants import (
    API_VERSION,
    CURRENCY_SYNC_HOUR,
    CURRENCY_SYNC_MINUTE,
    RATE_LIMIT_ENDPOINT_AUTH_LOGIN,
    RATE_LIMIT_ENDPOINT_AUTH_REGISTER,
    RATE_LIMIT_ENDPOINT_CHAT_STREAM,
    SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
    SCHEDULER_JOB_ATTACHMENT_CLEANUP,
    SCHEDULER_JOB_BROWSER_CLEANUP,
    SCHEDULER_JOB_CURRENCY_SYNC,
    SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
    SCHEDULER_JOB_INTEREST_CLEANUP,
    SCHEDULER_JOB_INTEREST_NOTIFICATION,
    SCHEDULER_JOB_MEMORY_CLEANUP,
    SCHEDULER_JOB_OAUTH_HEALTH,
    SCHEDULER_JOB_REMINDER_NOTIFICATION,
    SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
    SCHEDULER_JOB_SUBAGENT_STALE_RECOVERY,
    SCHEDULER_JOB_TOKEN_REFRESH,
    SCHEDULER_JOB_UNVERIFIED_CLEANUP,
    SCHEDULER_JOB_USER_MCP_EVICTION,
    UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
)
from src.core.field_names import FIELD_STATUS
from src.core.middleware import setup_middleware
from src.core.rate_limit_config import build_default_limit, rate_limiting_enabled
from src.infrastructure.cache.redis import close_redis, get_redis_cache
from src.infrastructure.database.session import close_db
from src.infrastructure.observability.logging import configure_logging
from src.infrastructure.observability.metrics import PrometheusMiddleware, metrics_endpoint
from src.infrastructure.observability.tracing import configure_tracing
from src.infrastructure.scheduler.currency_sync import sync_currency_rates
from src.infrastructure.scheduler.interest_cleanup import cleanup_interests
from src.infrastructure.scheduler.interest_notification import process_interest_notifications
from src.infrastructure.scheduler.memory_cleanup import cleanup_memories
from src.infrastructure.scheduler.oauth_health import check_oauth_health_all_users
from src.infrastructure.scheduler.reminder_notification import process_pending_reminders
from src.infrastructure.scheduler.scheduled_action_executor import process_scheduled_actions
from src.infrastructure.scheduler.token_refresh import refresh_expiring_tokens
from src.infrastructure.scheduler.unverified_account_cleanup import cleanup_unverified_accounts

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
    """
    # Startup
    # Eagerly import all domain models so SQLAlchemy mappers are fully configured
    # before any query. Required for models referenced via string in relationships
    # (e.g., User.skill_states → UserSkillState).
    import src.domains.skills.models  # noqa: F401

    logger.info(
        "application_startup",
        environment=settings.environment,
        debug=settings.debug,
    )

    # Log event loop configuration (Windows-specific fix for psycopg v3)
    log_event_loop_configuration()

    # Start dedicated HTTP-only Prometheus metrics server
    # Separate from the main HTTPS uvicorn server so Prometheus can scrape
    # without TLS handshake issues between Docker containers
    metrics_port = settings.prometheus_metrics_port
    try:
        from prometheus_client import start_http_server

        start_http_server(metrics_port)  # Daemon thread, auto-stops on process exit
        logger.info("prometheus_metrics_server_started", port=metrics_port)
    except OSError as exc:
        logger.warning("prometheus_metrics_server_failed", port=metrics_port, error=str(exc))

    # Validate LLM configuration (fail-fast if config is incomplete)
    try:
        validate_llm_configuration()
    except ValueError as exc:
        logger.error("llm_configuration_invalid", error=str(exc), exc_info=True)
        raise RuntimeError(f"Invalid LLM configuration: {exc}") from exc

    # Validate ToolErrorCode enum completeness (fail-fast if codes are missing)
    try:
        validate_tool_error_codes()
    except RuntimeError as exc:
        logger.error("tool_error_codes_invalid", error=str(exc), exc_info=True)
        raise

    # Log rate limiting configuration
    log_rate_limiting_status()

    # Register tool schemas (Phase 2.1 - Issue #32)
    # Must be called early to populate schema registry before first request
    try:
        register_tool_schemas()
    except RuntimeError as exc:
        logger.error("tool_schema_registration_failed", error=str(exc), exc_info=True)
        raise RuntimeError(f"Failed to register tool schemas: {exc}") from exc

    # Initialize Redis connections
    try:
        await get_redis_cache()
        logger.info("redis_initialized")
    except (ConnectionError, TimeoutError, OSError) as exc:
        logger.error("redis_initialization_failed", error=str(exc), exc_info=True)

    # Initialize global pricing cache (for callback safety - no DB access in callbacks)
    # See: src/infrastructure/cache/pricing_cache.py for implementation
    try:
        from src.infrastructure.cache.pricing_cache import refresh_pricing_cache

        await refresh_pricing_cache()
        logger.info("pricing_cache_initialized")
    except Exception as exc:
        # Non-critical - callbacks will use default prices (0.0 cost)
        logger.warning("pricing_cache_initialization_failed", error=str(exc))

    # Initialize Google API pricing cache (for cost tracking in tools and endpoints)
    try:
        from src.domains.google_api.pricing_service import GoogleApiPricingService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await GoogleApiPricingService.load_pricing_cache(db)
        logger.info("google_api_pricing_cache_initialized")
    except Exception as exc:
        # Non-critical - tracking will use zero cost if cache not loaded
        logger.warning("google_api_pricing_cache_initialization_failed", error=str(exc))

    # Initialize LangGraph checkpointer
    checkpointer = None
    try:
        from src.domains.conversations.checkpointer import get_checkpointer

        checkpointer = await get_checkpointer()
        logger.info("checkpointer_initialized")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("checkpointer_initialization_failed", error=str(exc), exc_info=True)

    # Initialize LLM config override cache (must be before any get_llm() call)
    try:
        from src.domains.llm_config.cache import LLMConfigOverrideCache
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            await LLMConfigOverrideCache.load_from_db(db)
        logger.info("llm_config_cache_initialized")

        # Warn about missing provider API keys (DB is the sole source of truth)
        from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_PROVIDERS

        required_providers = {cfg.provider for cfg in LLM_DEFAULTS.values()}
        for provider in sorted(required_providers):
            if not LLMConfigOverrideCache.get_api_key(provider):
                display = LLM_PROVIDERS.get(provider, provider)
                logger.warning(
                    "provider_api_key_missing",
                    provider=provider,
                    msg=f"No API key in DB for provider '{display}'. "
                    "Configure via Settings > Administration > LLM Configuration.",
                )
    except Exception as exc:
        logger.warning("llm_config_cache_initialization_failed", error=str(exc))

    # Initialize Skills cache (agentskills.io standard — SKILL.md files on disk)
    # Then sync DB (skills + user_skill_states) with disk state.
    if getattr(settings, "skills_enabled", False):
        try:
            from src.domains.skills.cache import SkillsCache

            SkillsCache.load_from_disk(settings.skills_system_path, settings.skills_users_path)
            logger.info("skills_cache_initialized")

            # Sync DB with disk (create new skills, remove orphans, ensure user states)
            from src.domains.skills.preference_service import SkillPreferenceService
            from src.infrastructure.database.session import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                svc = SkillPreferenceService(db)
                sync_result = await svc.sync_from_disk()
                await db.commit()
                logger.info(
                    "skills_db_synced",
                    created=len(sync_result.created),
                    removed=len(sync_result.removed),
                    updated=len(sync_result.updated),
                )
        except Exception as exc:
            logger.warning("skills_cache_initialization_failed", error=str(exc))

    # Initialize AgentRegistry with checkpointer and store
    # Note: Legacy tool catalogue (tools/catalogue.py) removed in Phase 5
    # All tool manifests now loaded via registry/catalogue_loader.py
    registry = None  # Pre-init: used by MCP + semantic tool selector below
    try:
        from src.domains.agents.context import get_tool_context_store
        from src.domains.agents.graphs import (
            build_brave_agent,
            build_calendar_agent,
            build_contacts_agent,
            build_drive_agent,
            build_emails_agent,
            build_perplexity_agent,
            build_places_agent,
            build_query_agent,
            build_routes_agent,
            build_tasks_agent,
            build_weather_agent,
            build_web_fetch_agent,
            build_web_search_agent,
            build_wikipedia_agent,
        )
        from src.domains.agents.registry import set_global_registry

        # Get tool context store (AsyncPostgresStore for persistent contextual references)
        store = await get_tool_context_store()

        # Create and configure global registry
        from src.domains.agents.registry import AgentRegistry

        registry = AgentRegistry(checkpointer=checkpointer, store=store)

        # Initialize catalogue with manifests (Phase 1 - Planner)
        from src.domains.agents.registry.catalogue_loader import initialize_catalogue

        initialize_catalogue(registry)
        logger.info("catalogue_manifests_initialized")

        # Register all available agents
        # NAMING: domain=entity(singular), agent=domain+"_agent"
        # OAuth agents (Google)
        registry.register_agent("contact_agent", build_contacts_agent)
        registry.register_agent("email_agent", build_emails_agent)
        registry.register_agent("event_agent", build_calendar_agent)
        registry.register_agent("file_agent", build_drive_agent)
        registry.register_agent("task_agent", build_tasks_agent)
        # API key agents
        registry.register_agent("weather_agent", build_weather_agent)
        registry.register_agent("wikipedia_agent", build_wikipedia_agent)
        registry.register_agent("perplexity_agent", build_perplexity_agent)
        registry.register_agent("brave_agent", build_brave_agent)
        registry.register_agent("web_search_agent", build_web_search_agent)
        registry.register_agent("web_fetch_agent", build_web_fetch_agent)
        registry.register_agent("place_agent", build_places_agent)
        registry.register_agent("route_agent", build_routes_agent)
        # Internal agents (no external API - operate on Registry data)
        registry.register_agent("query_agent", build_query_agent)

        # Browser agent (F7 - auto-detected, no feature flag needed)
        # Activation is managed via admin connector panel, not .env.
        # If Playwright/Chromium is installed → agent available. If not → graceful skip.
        try:
            from src.infrastructure.browser.pool import get_browser_pool

            browser_pool = await get_browser_pool()
            if browser_pool and browser_pool.is_healthy:
                from src.domains.agents.graphs.browser_agent_builder import build_browser_agent

                registry.register_agent("browser_agent", build_browser_agent)
                scheduler.add_job(
                    browser_pool.cleanup_expired,
                    "interval",
                    seconds=60,
                    id=SCHEDULER_JOB_BROWSER_CLEANUP,
                    replace_existing=True,
                )
                logger.info("browser_agent_initialized")
            else:
                logger.info("browser_agent_skipped_chromium_not_available")
        except ImportError:
            logger.info("browser_agent_skipped_playwright_not_installed")

        # Set as global registry
        set_global_registry(registry)

        logger.info(
            "agent_registry_initialized",
            registered_agents=list(registry.list_agents()),
            has_checkpointer=checkpointer is not None,
            has_store=store is not None,
        )
    except (RuntimeError, ImportError, ValueError) as exc:
        logger.error("agent_registry_initialization_failed", error=str(exc), exc_info=True)

    # Initialize MCP Client Manager (evolution F2 — MCP Support)
    mcp_manager = None
    if getattr(settings, "mcp_enabled", False) and registry is not None:
        try:
            from src.infrastructure.mcp.client_manager import initialize_mcp_client_manager
            from src.infrastructure.mcp.registration import register_mcp_tools
            from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

            mcp_manager = await initialize_mcp_client_manager()
            if mcp_manager and mcp_manager.discovered_tools:
                # Create adapters for each discovered tool
                adapters: dict[str, MCPToolAdapter] = {}
                for server_name, tools in mcp_manager.discovered_tools.items():
                    for tool in tools:
                        adapter = MCPToolAdapter.from_mcp_tool(
                            server_name=server_name,
                            tool_name=tool.tool_name,
                            description=tool.description,
                            input_schema=tool.input_schema,
                            app_resource_uri=tool.app_resource_uri,
                        )
                        adapters[adapter.name] = adapter

                # Register in AgentRegistry + tool_registry
                tool_count = register_mcp_tools(
                    registry=registry,
                    discovered_tools=mcp_manager.discovered_tools,
                    adapters=adapters,
                    server_configs=mcp_manager.server_configs,
                    global_hitl_required=getattr(settings, "mcp_hitl_required", True),
                    reference_content=mcp_manager.reference_content,
                )

                # Rebuild domain index to include the "mcp" domain
                registry.rebuild_domain_index()

                logger.info(
                    "mcp_initialized",
                    servers=mcp_manager.connected_server_count,
                    tools=tool_count,
                )
        except Exception as exc:
            logger.error("mcp_initialization_failed", error=str(exc), exc_info=True)

    # Initialize User MCP Pool (evolution F2.1 — MCP Per-User)
    if getattr(settings, "mcp_user_enabled", False):
        try:
            from src.infrastructure.mcp.user_pool import initialize_user_mcp_pool

            await initialize_user_mcp_pool()
            logger.info("user_mcp_pool_initialized")
        except Exception as exc:
            logger.error("user_mcp_pool_initialization_failed", error=str(exc), exc_info=True)

    # Initialize Telegram Bot (evolution F3 — Multi-Channel)
    telegram_bot = None
    if getattr(settings, "channels_enabled", False):
        try:
            from src.infrastructure.channels.telegram.bot import initialize_telegram_bot

            telegram_bot = await initialize_telegram_bot()
            if telegram_bot:
                logger.info("telegram_bot_initialized")
        except Exception as exc:
            logger.error("telegram_bot_initialization_failed", error=str(exc), exc_info=True)

        # Initialize channel_active_bindings gauge from DB (survives API restarts)
        try:
            from sqlalchemy import func, select

            from src.domains.channels.models import UserChannelBinding
            from src.infrastructure.database.session import get_db_context
            from src.infrastructure.observability.metrics_channels import (
                channel_active_bindings,
            )

            async with get_db_context() as db:
                rows = await db.execute(
                    select(
                        UserChannelBinding.channel_type,
                        func.count(),
                    )
                    .where(UserChannelBinding.is_active.is_(True))
                    .group_by(UserChannelBinding.channel_type)
                )
                for channel_type, count in rows.all():
                    channel_active_bindings.labels(channel_type=channel_type).set(count)
            logger.info("channel_active_bindings_gauge_initialized")
        except Exception as exc:
            # Non-critical — gauge starts at 0 and self-corrects on create/delete
            logger.warning(
                "channel_active_bindings_gauge_failed",
                error=str(exc),
            )

    # Initialize v3.1 Semantic Services (Architecture v3.1 - LLM-Based Intelligence)
    # Note: SemanticIntentDetector and SemanticDomainSelector removed in v3.1
    # Intent and domain detection now handled by QueryAnalyzerService (LLM-based)
    # SemanticToolSelector still used for tool selection within domains
    if registry is None:
        logger.error("semantic_services_skipped_no_registry")
    else:
        try:
            # Initialize SemanticToolSelector via registry (requires tool manifests)
            # This uses the manifests already registered in the catalogue
            await registry.initialize_semantic_tool_selector()

            logger.info(
                "v3_semantic_services_initialized",
                services=["SemanticToolSelector"],
                note="Intent/domain detection now LLM-based (QueryAnalyzerService)",
            )
        except (RuntimeError, ValueError, AttributeError) as exc:
            logger.error(
                "v3_semantic_services_initialization_failed",
                error=str(exc),
                exc_info=True,
            )

    # Initialize LangGraph agent service (builds graph with registry)
    try:
        from src.domains.agents.api.router import get_agent_service

        agent_service = get_agent_service()
        await agent_service._ensure_graph_built()
        logger.info("agent_graph_initialized", graph_compiled=agent_service.graph is not None)
    except (RuntimeError, ImportError, ValueError) as exc:
        logger.error("agent_graph_initialization_failed", error=str(exc), exc_info=True)

    # Initialize Langfuse callback factory for LLM observability
    try:
        from src.infrastructure.llm.callback_factory import init_callback_factory

        callback_factory = init_callback_factory(settings)
        if callback_factory.is_enabled():
            logger.info(
                "langfuse_callback_factory_initialized",
                host=settings.langfuse_host,
                release=settings.langfuse_release,
            )
        else:
            logger.info("langfuse_tracing_disabled")
    except (RuntimeError, ImportError, ValueError, ConnectionError) as exc:
        logger.error("langfuse_initialization_failed", error=str(exc), exc_info=True)

    # Initialize currency rates on startup (critical for token cost tracking)
    try:
        logger.info("currency_rates_startup_sync_starting")
        await sync_currency_rates()
        logger.info("currency_rates_startup_sync_completed")
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        # Don't fail startup, but log error prominently
        logger.error(
            "currency_rates_startup_sync_failed",
            error=str(exc),
            exc_info=True,
            remediation="Token cost tracking may fail until rates are synced",
        )

    # Start APScheduler for background tasks
    try:
        # Schedule daily currency sync at configured time (default: 3:00 AM UTC)
        scheduler.add_job(
            sync_currency_rates,
            trigger="cron",
            hour=CURRENCY_SYNC_HOUR,
            minute=CURRENCY_SYNC_MINUTE,
            id=SCHEDULER_JOB_CURRENCY_SYNC,
            name="Sync USD→EUR rates from API to DB",
            replace_existing=True,
        )

        # Schedule daily memory cleanup (Phase 6 - Long-Term Memory Purge)
        # Runs at configured hour (default: 4:00 AM UTC)
        # NOTE: Memory features are always enabled
        scheduler.add_job(
            cleanup_memories,
            trigger="cron",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
            id=SCHEDULER_JOB_MEMORY_CLEANUP,
            name="Cleanup old unused memories (hybrid retention algorithm)",
            replace_existing=True,
        )
        logger.info(
            "memory_cleanup_job_scheduled",
            hour=settings.memory_cleanup_hour,
            minute=settings.memory_cleanup_minute,
        )

        # Schedule daily interest cleanup (dormant marking + deletion)
        # Runs at 3:00 AM UTC (before memory cleanup at 4 AM)
        # NOTE: Interest features are always enabled
        scheduler.add_job(
            cleanup_interests,
            trigger="cron",
            hour=3,  # 3 AM UTC
            minute=0,
            id=SCHEDULER_JOB_INTEREST_CLEANUP,
            name="Cleanup dormant and old interests",
            replace_existing=True,
        )
        logger.info("interest_cleanup_job_scheduled", hour=3, minute=0)

        # Schedule reminder notification job (every minute)
        # Checks for pending reminders and sends notifications
        if settings.fcm_enabled:
            scheduler.add_job(
                process_pending_reminders,
                trigger="interval",
                minutes=1,
                id=SCHEDULER_JOB_REMINDER_NOTIFICATION,
                name="Process pending reminder notifications",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=30,  # Allow 30s delay before considering job missed
            )
            logger.info("reminder_notification_job_scheduled", interval_minutes=1)

        # Schedule scheduled action executor (every 60s)
        # Checks for due scheduled actions and executes them through the agent pipeline
        scheduler.add_job(
            process_scheduled_actions,
            trigger="interval",
            seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
            id=SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,
            name="Process scheduled actions",
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=30,
        )
        logger.info(
            "scheduled_action_executor_job_scheduled",
            interval_seconds=SCHEDULED_ACTIONS_EXECUTOR_INTERVAL_SECONDS,
        )

        # Schedule sub-agent stale recovery (feature-flagged)
        if getattr(settings, "sub_agents_enabled", False):
            from src.domains.sub_agents.executor import SubAgentExecutor

            stale_interval = getattr(settings, "subagent_stale_recovery_interval_seconds", 120)
            scheduler.add_job(
                SubAgentExecutor.recover_stale_subagents,
                trigger="interval",
                seconds=stale_interval,
                id=SCHEDULER_JOB_SUBAGENT_STALE_RECOVERY,
                name="Recover stale sub-agents",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=30,
            )
            logger.info(
                "subagent_stale_recovery_job_scheduled",
                interval_seconds=stale_interval,
            )

        # Schedule proactive interest notifications (configurable interval, default 15 min)
        # Sends personalized content about user's interests (Wikipedia, Perplexity, LLM)
        # NOTE: Interest features are always enabled (no feature flag check)
        scheduler.add_job(
            process_interest_notifications,
            trigger="interval",
            minutes=settings.interest_notification_interval_minutes,
            id=SCHEDULER_JOB_INTEREST_NOTIFICATION,
            name="Proactive interest notifications",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            misfire_grace_time=60,  # Allow 1 min delay before considering job missed
        )
        logger.info(
            "interest_notification_job_scheduled",
            interval_minutes=settings.interest_notification_interval_minutes,
        )

        # Schedule unverified account cleanup (daily at 5 AM UTC)
        # Deletes non-OAuth accounts that haven't verified email after 1 day
        scheduler.add_job(
            cleanup_unverified_accounts,
            trigger="cron",
            hour=UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
            minute=0,
            id=SCHEDULER_JOB_UNVERIFIED_CLEANUP,
            name="Cleanup unverified accounts older than 1 day",
            replace_existing=True,
        )
        logger.info(
            "unverified_account_cleanup_job_scheduled",
            hour=UNVERIFIED_ACCOUNT_CLEANUP_HOUR,
        )

        # Schedule proactive OAuth token refresh (configurable interval)
        # Refreshes tokens expiring within configurable margin to prevent disconnections
        # NOTE: Proactive refresh is always enabled for production reliability
        scheduler.add_job(
            refresh_expiring_tokens,
            trigger="interval",
            minutes=settings.oauth_proactive_refresh_interval_minutes,
            id=SCHEDULER_JOB_TOKEN_REFRESH,
            name="Proactive OAuth token refresh",
            replace_existing=True,
            max_instances=1,  # Prevent concurrent runs
            misfire_grace_time=60,  # Allow 1 min delay before considering job missed
        )
        logger.info(
            "token_refresh_job_scheduled",
            interval_minutes=settings.oauth_proactive_refresh_interval_minutes,
            margin_seconds=settings.oauth_proactive_refresh_margin_seconds,
        )

        # Schedule OAuth health check (push notifications for broken connectors)
        # Only notifies on status=ERROR (refresh failed, needs manual re-auth)
        # NOTE: Only enabled if oauth_health_check_enabled is True
        if settings.oauth_health_check_enabled:
            scheduler.add_job(
                check_oauth_health_all_users,
                trigger="interval",
                minutes=settings.oauth_health_check_interval_minutes,
                id=SCHEDULER_JOB_OAUTH_HEALTH,
                name="OAuth health check notifications",
                replace_existing=True,
                max_instances=1,  # Prevent concurrent runs
                misfire_grace_time=60,  # Allow 1 min delay before considering job missed
            )
            logger.info(
                "oauth_health_check_job_scheduled",
                interval_minutes=settings.oauth_health_check_interval_minutes,
            )

        # Schedule user MCP pool eviction (evolution F2.1)
        if getattr(settings, "mcp_user_enabled", False):

            async def _evict_user_mcp_idle() -> None:
                from src.infrastructure.mcp.user_pool import get_user_mcp_pool

                pool = get_user_mcp_pool()
                if pool:
                    await pool.evict_idle()

            eviction_interval = getattr(settings, "mcp_user_pool_eviction_interval", 60)
            scheduler.add_job(
                _evict_user_mcp_idle,
                trigger="interval",
                seconds=eviction_interval,
                id=SCHEDULER_JOB_USER_MCP_EVICTION,
                name="User MCP pool idle eviction",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=30,
            )
            logger.info(
                "user_mcp_eviction_job_scheduled",
                interval_seconds=eviction_interval,
            )

        # Schedule proactive heartbeat notifications (evolution F5 — Heartbeat Autonome)
        # Only registered if feature flag enabled (pattern: channels_enabled)
        if getattr(settings, "heartbeat_enabled", False):
            from src.infrastructure.scheduler.heartbeat_notification import (
                process_heartbeat_notifications,
            )

            scheduler.add_job(
                process_heartbeat_notifications,
                trigger="interval",
                minutes=settings.heartbeat_notification_interval_minutes,
                id=SCHEDULER_JOB_HEARTBEAT_NOTIFICATION,
                name="Proactive heartbeat notifications",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info(
                "heartbeat_notification_job_scheduled",
                interval_minutes=settings.heartbeat_notification_interval_minutes,
            )

        # Schedule attachment cleanup (evolution F4 — File Attachments)
        # Runs every 6 hours as TTL safety net for orphan files
        if getattr(settings, "attachments_enabled", False):
            from src.infrastructure.scheduler.attachment_cleanup import (
                cleanup_expired_attachments,
            )

            scheduler.add_job(
                cleanup_expired_attachments,
                trigger="interval",
                hours=6,
                id=SCHEDULER_JOB_ATTACHMENT_CLEANUP,
                name="Cleanup expired attachments",
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=60,
            )
            logger.info("attachment_cleanup_job_scheduled", interval_hours=6)

        scheduler.start()
        scheduled_jobs = [
            SCHEDULER_JOB_CURRENCY_SYNC,
            SCHEDULER_JOB_INTEREST_CLEANUP,  # Always enabled (interest learning)
            SCHEDULER_JOB_INTEREST_NOTIFICATION,  # Always enabled (proactive notifications)
            SCHEDULER_JOB_UNVERIFIED_CLEANUP,
            SCHEDULER_JOB_TOKEN_REFRESH,  # Always enabled (proactive OAuth refresh)
            SCHEDULER_JOB_MEMORY_CLEANUP,  # Always enabled (memory features)
            SCHEDULER_JOB_SCHEDULED_ACTION_EXECUTOR,  # Always enabled (scheduled actions)
        ]
        if settings.fcm_enabled:
            scheduled_jobs.append(SCHEDULER_JOB_REMINDER_NOTIFICATION)
        if settings.oauth_health_check_enabled:
            scheduled_jobs.append(SCHEDULER_JOB_OAUTH_HEALTH)
        if getattr(settings, "mcp_user_enabled", False):
            scheduled_jobs.append(SCHEDULER_JOB_USER_MCP_EVICTION)
        if getattr(settings, "heartbeat_enabled", False):
            scheduled_jobs.append(SCHEDULER_JOB_HEARTBEAT_NOTIFICATION)
        if getattr(settings, "attachments_enabled", False):
            scheduled_jobs.append(SCHEDULER_JOB_ATTACHMENT_CLEANUP)
        logger.info("scheduler_started", jobs=scheduled_jobs)
    except (RuntimeError, ValueError) as exc:
        logger.error("scheduler_initialization_failed", error=str(exc), exc_info=True)

    # Start lifetime metrics updater (Phase 1.2 - DB-Backed Gauges)
    # Solves RC1: Prometheus counter resets on restart
    lifetime_metrics_task = None
    try:
        import asyncio

        from src.infrastructure.observability.lifetime_metrics import update_lifetime_metrics

        lifetime_metrics_task = asyncio.create_task(update_lifetime_metrics())
        logger.info(
            "lifetime_metrics_updater_started",
            message="DB-backed Prometheus gauges will sync every 30s (restart-safe)",
        )
    except (RuntimeError, ImportError) as exc:
        logger.error("lifetime_metrics_updater_failed", error=str(exc), exc_info=True)

    logger.info("application_ready")

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Stop lifetime metrics updater
    if lifetime_metrics_task:
        try:
            lifetime_metrics_task.cancel()
            try:
                await lifetime_metrics_task
            except asyncio.CancelledError:
                pass
            logger.info("lifetime_metrics_updater_stopped")
        except RuntimeError as exc:
            logger.error("lifetime_metrics_updater_shutdown_failed", error=str(exc))

    # Flush and shutdown Langfuse (Phase 6 - LLM Observability)
    try:
        from src.infrastructure.llm.callback_factory import (
            flush_callbacks,
            shutdown_callback_factory,
        )

        flush_callbacks()
        shutdown_callback_factory()
        logger.info("langfuse_shutdown_complete")
    except (RuntimeError, ImportError) as exc:
        logger.error("langfuse_shutdown_failed", error=str(exc))

    # Stop scheduler
    try:
        scheduler.shutdown()
        logger.info("scheduler_stopped")
    except RuntimeError as exc:
        logger.error("scheduler_shutdown_failed", error=str(exc))

    # Reset v3.1 Semantic Services (clear cached embeddings)
    # Note: SemanticIntentDetector and SemanticDomainSelector removed in v3.1
    try:
        from src.domains.agents.services.tool_selector import reset_tool_selector

        reset_tool_selector()
        logger.info("v3_semantic_services_reset", services=["SemanticToolSelector"])
    except (RuntimeError, ImportError) as exc:
        logger.error("v3_semantic_services_reset_failed", error=str(exc))

    # Clear agent registry cache
    try:
        from src.domains.agents.registry import reset_global_registry

        reset_global_registry()
        logger.info("agent_registry_cleared")
    except (RuntimeError, ImportError) as exc:
        logger.error("agent_registry_cleanup_failed", error=str(exc))

    # Close MCP connections (evolution F2)
    if mcp_manager:
        try:
            from src.infrastructure.mcp.client_manager import cleanup_mcp_client_manager

            await cleanup_mcp_client_manager()
            logger.info("mcp_connections_closed")
        except (RuntimeError, ImportError) as exc:
            logger.error("mcp_shutdown_failed", error=str(exc))

    # Close user MCP pool connections (evolution F2.1)
    if getattr(settings, "mcp_user_enabled", False):
        try:
            from src.infrastructure.mcp.user_pool import cleanup_user_mcp_pool

            await cleanup_user_mcp_pool()
            logger.info("user_mcp_pool_closed")
        except (RuntimeError, ImportError) as exc:
            logger.error("user_mcp_pool_shutdown_failed", error=str(exc))

    # Close browser pool (evolution F7)
    try:
        from src.infrastructure.browser.pool import close_browser_pool

        await close_browser_pool()
        logger.info("browser_pool_closed")
    except (RuntimeError, ImportError):
        pass  # Browser not installed — nothing to close

    # Shutdown Telegram Bot (evolution F3)
    if telegram_bot:
        try:
            from src.infrastructure.channels.telegram.bot import shutdown_telegram_bot

            await shutdown_telegram_bot()
            logger.info("telegram_bot_shutdown")
        except (RuntimeError, ImportError) as exc:
            logger.error("telegram_bot_shutdown_failed", error=str(exc))

    # Close checkpointer connection
    try:
        from src.domains.conversations.checkpointer import cleanup_checkpointer

        await cleanup_checkpointer()
        logger.info("checkpointer_closed")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("checkpointer_shutdown_failed", error=str(exc))

    # Close tool context store connection
    try:
        from src.domains.agents.context import cleanup_tool_context_store

        await cleanup_tool_context_store()
        logger.info("tool_context_store_closed")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("tool_context_store_shutdown_failed", error=str(exc))

    # Close geocoding HTTP client (connection pooling cleanup)
    try:
        from src.domains.connectors.clients.google_geocoding_helpers import (
            close_geocoding_client,
        )

        await close_geocoding_client()
        logger.info("geocoding_client_closed")
    except (RuntimeError, ImportError) as exc:
        logger.error("geocoding_client_shutdown_failed", error=str(exc))

    # Close GeoIP reader
    try:
        from src.infrastructure.observability.geoip import geoip_resolver

        geoip_resolver.close()
        logger.info("geoip_reader_closed")
    except Exception as exc:
        logger.error("geoip_reader_close_failed", error=str(exc))

    # Close database connections
    await close_db()
    logger.info("database_closed")

    # Close Redis connections
    await close_redis()
    logger.info("redis_closed")


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

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)

# Metrics endpoint
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)


# Root endpoint
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str | None]:
    """Root endpoint with API information."""
    return {
        "name": "LIA API",
        "version": "0.1.0",
        FIELD_STATUS: "operational",
        "environment": settings.environment,
        "docs": f"{settings.api_prefix}/docs" if not settings.is_production else None,
    }


# Health check endpoint
@app.get("/health", include_in_schema=False)
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring and load balancers.
    Verifies database and Redis connectivity.
    """
    health_status: dict[str, str | dict[str, str]] = {
        FIELD_STATUS: "healthy",
        "environment": settings.environment,
        "checks": {},
    }

    # Check Redis
    try:
        redis = await get_redis_cache()
        await redis.ping()  # type: ignore[misc]
        health_status["checks"]["redis"] = "healthy"  # type: ignore[index]
    except (ConnectionError, TimeoutError, OSError) as exc:
        logger.error("health_check_redis_failed", error=str(exc))
        health_status["checks"]["redis"] = "unhealthy"  # type: ignore[index]
        health_status[FIELD_STATUS] = "degraded"

    # Check database
    try:
        from sqlalchemy import text
        from sqlalchemy.exc import OperationalError
        from sqlalchemy.exc import TimeoutError as SATimeoutError

        from src.infrastructure.database.session import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "healthy"  # type: ignore[index]
    except (OperationalError, SATimeoutError, ConnectionError, OSError) as exc:
        logger.error("health_check_database_failed", error=str(exc))
        health_status["checks"]["database"] = "unhealthy"  # type: ignore[index]
        health_status[FIELD_STATUS] = "degraded"

    status_code = 200 if health_status[FIELD_STATUS] != "unhealthy" else 503

    return JSONResponse(content=health_status, status_code=status_code)


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
