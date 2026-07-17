"""Startup steps: LangGraph agent subsystem.

Checkpointer, AgentRegistry (agents + catalogue + browser agent), semantic
tool selector and the main agent graph.

ORDER (enforced by the lifespan in ``src/main.py``): the checkpointer must
exist before the registry (injected at construction); MCP registration runs
BETWEEN ``init_agent_registry`` and ``init_semantic_services`` so the
selector's embeddings cover MCP tools.

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling, same feature-flag guards.
"""

from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_BROWSER_CLEANUP

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from src.domains.agents.registry import AgentRegistry
    from src.domains.conversations.checkpointer import InstrumentedAsyncPostgresSaver

logger = structlog.get_logger(__name__)


async def init_checkpointer() -> "InstrumentedAsyncPostgresSaver | None":
    """Initialize the LangGraph checkpointer (non-fatal on failure).

    Returns:
        The checkpointer instance, or None if initialization failed.
    """
    checkpointer = None
    try:
        from src.domains.conversations.checkpointer import get_checkpointer

        checkpointer = await get_checkpointer()
        logger.info("checkpointer_initialized")
    except (RuntimeError, ImportError, ConnectionError) as exc:
        logger.error("checkpointer_initialization_failed", error=str(exc), exc_info=True)
    return checkpointer


async def init_agent_registry(
    checkpointer: "InstrumentedAsyncPostgresSaver | None",
    scheduler: "AsyncIOScheduler",
) -> "AgentRegistry | None":
    """Initialize the AgentRegistry with checkpointer and store, register all agents.

    Note: Legacy tool catalogue (tools/catalogue.py) removed in Phase 5.
    All tool manifests now loaded via registry/catalogue_loader.py.

    Args:
        checkpointer: LangGraph checkpointer injected into the registry (may be None).
        scheduler: APScheduler instance — the browser cleanup job is registered
            here so it exists before ``leader_elector.start()``.

    Returns:
        The registry consumed by the MCP and semantic-selector steps. On a
        mid-initialization failure this returns the PARTIALLY built registry
        (not None) — downstream steps deliberately consume the partial object,
        matching the historical lifespan behavior. None only if construction
        never happened.
    """
    registry = None  # Pre-init: used by MCP + semantic tool selector downstream
    try:
        from src.domains.agents.context import get_tool_context_store
        from src.domains.agents.graphs import (
            build_brave_agent,
            build_calendar_agent,
            build_contacts_agent,
            build_drive_agent,
            build_emails_agent,
            build_hue_agent,
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
        # Smart Home agents
        registry.register_agent("hue_agent", build_hue_agent)
        # Internal agents (no external API - operate on Registry data)
        registry.register_agent("query_agent", build_query_agent)

        # Health Metrics agent (v1.17.2) — gated on feature flag
        if getattr(settings, "health_metrics_enabled", False):
            from src.domains.agents.graphs import build_health_agent

            registry.register_agent("health_agent", build_health_agent)
            logger.info("health_agent_registered")

        # Agentic telephony agent (ADR-127) — gated on feature flag, symmetric
        # with the catalogue-manifest registration in catalogue_loader.py
        if getattr(settings, "telephony_enabled", False):
            from src.domains.agents.graphs import build_telephony_agent

            registry.register_agent("telephony_agent", build_telephony_agent)
            logger.info("telephony_agent_registered")

        # Browser agent (F7 - lazy-initialized, Chromium only starts on first browser tool call)
        # Pool.initialize() deferred to first acquire_session() to save ~1.5 GB RAM at boot.
        # Cleanup job is registered on ALL workers (leader election requires it) but is
        # a no-op until a worker actually initializes the pool on first browser request.
        try:
            import importlib.util

            if importlib.util.find_spec("playwright") is not None:
                from src.domains.agents.graphs.browser_agent_builder import (
                    build_browser_agent,
                )
                from src.infrastructure.browser.pool import cleanup_browser_sessions

                registry.register_agent("browser_agent", build_browser_agent)
                scheduler.add_job(
                    cleanup_browser_sessions,
                    "interval",
                    seconds=60,
                    id=SCHEDULER_JOB_BROWSER_CLEANUP,
                    replace_existing=True,
                )
                logger.info("browser_agent_registered_lazy")
            else:
                logger.info("browser_agent_skipped_playwright_not_installed")
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
    return registry


async def init_semantic_services(registry: "AgentRegistry | None") -> None:
    """Initialize v3.1 Semantic Services (Architecture v3.1 - LLM-Based Intelligence).

    Note: SemanticIntentDetector and SemanticDomainSelector removed in v3.1.
    Intent and domain detection now handled by QueryAnalyzerService (LLM-based).
    SemanticToolSelector still used for tool selection within domains.

    Args:
        registry: The agent registry (its catalogue must already include MCP
            tools so the selector's embeddings cover them); may be None.
    """
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


async def init_agent_graph() -> None:
    """Initialize the LangGraph agent service (builds graph with registry)."""
    try:
        from src.domains.agents.api.router import get_agent_service

        agent_service = get_agent_service()
        await agent_service._ensure_graph_built()
        logger.info("agent_graph_initialized", graph_compiled=agent_service.graph is not None)
    except (RuntimeError, ImportError, ValueError) as exc:
        logger.error("agent_graph_initialization_failed", error=str(exc), exc_info=True)
