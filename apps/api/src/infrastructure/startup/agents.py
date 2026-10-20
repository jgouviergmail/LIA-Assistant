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

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_BROWSER_CLEANUP
from src.infrastructure.startup.errors import StartupCompletenessError

if TYPE_CHECKING:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from src.domains.agents.registry import AgentRegistry
    from src.domains.conversations.checkpointer import InstrumentedAsyncPostgresSaver

logger = structlog.get_logger(__name__)


async def init_checkpointer() -> InstrumentedAsyncPostgresSaver | None:
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


#: One boot guard: the log event, the subject named in the refusal, the check.
BootGuard = tuple[str, str, Callable[[], None]]


def _run_boot_guards(guards: tuple[BootGuard, ...]) -> None:
    """Run each guard in order; the first that refuses STOPS the boot.

    One loop for every completeness guard of this step: a copy per guard is a
    place for the re-raise to be forgotten, which is exactly the defect where
    ``init_agent_registry`` caught its own guards and merely logged (ADR-263).

    Args:
        guards: ``(event, subject, guard)`` triples.

    Raises:
        StartupCompletenessError: Naming the subject of the guard that refused.
    """
    for event, subject, guard in guards:
        try:
            guard()
        except AssertionError as exc:
            logger.error(event, error=str(exc), exc_info=True)
            raise StartupCompletenessError(f"{subject} incomplete: {exc}") from exc


def _assert_catalogue_completeness(registry: Any) -> None:
    """Run the guards that read the loaded catalogue, and let a failure STOP the boot.

    They run here, not in ``startup/registries.py``, because the manifests only
    become checkable once ``initialize_catalogue`` has loaded them (ADR-085):

    - every user-invocable capability directive maps to a spec, and every spec
      to a REGISTERED tool (ADR-191);
    - every native manifest has a safety category (ADR-256): one with neither a
      declared ``tool_category`` nor a naming convention falls back to
      ``readonly``, which decides whether it counts as a mutation and whether
      the read-only initiative may run it — four writing tools sat there;
    - every acting tool says what confirmation it owes (ADR-263): measured
      2026-09-03, 13 native mutations had no gate in either execution mode;
    - every read tool keeping its data out of the pipeline's data block says
      why (ADR-347).

    Args:
        registry: The registry whose catalogue was just loaded.

    Raises:
        StartupCompletenessError: On the first guard that refuses.
    """
    from src.domains.agents.capability_directives import assert_registry_completeness
    from src.domains.agents.registry.catalogue import (
        assert_mutation_policy_completeness,
        assert_pipeline_data_channel_completeness,
        assert_tool_category_completeness,
    )

    _run_boot_guards(
        (
            (
                "capability_directive_registry_incomplete",
                "Capability directive registry",
                lambda: assert_registry_completeness(registry),
            ),
            (
                "tool_category_registry_incomplete",
                "Tool category registry",
                lambda: assert_tool_category_completeness(registry.list_tool_manifests()),
            ),
            (
                "mutation_policy_registry_incomplete",
                "Mutation policy registry",
                lambda: assert_mutation_policy_completeness(registry.list_tool_manifests()),
            ),
            (
                "pipeline_data_channel_registry_incomplete",
                "Pipeline data channel registry",
                lambda: assert_pipeline_data_channel_completeness(registry.list_tool_manifests()),
            ),
        )
    )


def _assert_effect_completeness(registry: Any) -> None:
    """Run the ADR-263 boot guards, and let a failure STOP the boot.

    Each guard asserts a property the code is supposed to guarantee rather than
    trusting that the code ran:

    - every registered capability, and every draft executor, goes through the
      effect gate (installation happens at registration; this found a second
      registration path the day it was written);
    - every capability that can ACT can say what it did — a register nobody can
      read is a log file;
    - every capability that can be CONSULTED can be named — a consultation
      register showing ``get_calls_tool`` to a user is a silent failure of the
      surface, and the surface has no other alarm;
    - every declared unattended stand-in can actually act where the draft it
      replaces is refused — a refusal naming a dead end sends the loop into a
      second refusal.

    Args:
        registry: The loaded registry, read by the naming guard.

    Raises:
        StartupCompletenessError: On the first guard that refuses.
    """
    from src.core.i18n_treatments import (
        assert_decision_wording_completeness,
        assert_stop_reason_wording_completeness,
    )
    from src.domains.agents.effects.gate import assert_unattended_stand_ins
    from src.domains.agents.effects.labels import assert_effect_label_completeness
    from src.domains.agents.effects.runtime import assert_effect_gate_completeness
    from src.domains.agents.effects.treatment_labels import (
        assert_treatment_domain_completeness,
    )

    guards: tuple[BootGuard, ...] = (
        ("effect_gate_incomplete", "Effect gate", assert_effect_gate_completeness),
        (
            "effect_labels_incomplete",
            "Effect labels",
            lambda: assert_effect_label_completeness(registry),
        ),
        (
            "unattended_stand_ins_incomplete",
            "Unattended stand-ins",
            lambda: assert_unattended_stand_ins(registry.list_tool_manifests()),
        ),
        (
            "treatment_domains_incomplete",
            "Treatment domains",
            lambda: assert_treatment_domain_completeness(registry),
        ),
        (
            "decision_wordings_incomplete",
            "Decision outcome wordings",
            assert_decision_wording_completeness,
        ),
        (
            "stop_reason_wordings_incomplete",
            "Turn stop-reason wordings",
            assert_stop_reason_wording_completeness,
        ),
    )
    _run_boot_guards(guards)


async def init_agent_registry(
    checkpointer: InstrumentedAsyncPostgresSaver | None,
    scheduler: AsyncIOScheduler,
) -> AgentRegistry | None:
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
    from src.infrastructure.proactive.context_sink import configure_proactive_context_writer

    configure_proactive_context_writer(None)
    from src.infrastructure.channels.assistant_gateway import configure_channel_gateway

    configure_channel_gateway(None)
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
        from uuid import UUID

        from pydantic import JsonValue

        async def write_proactive_context(actor_id: UUID, value: dict[str, JsonValue]) -> None:
            await store.aput((str(actor_id), "heartbeat_context"), "last_heartbeat", value)

        configure_proactive_context_writer(write_proactive_context)
        from src.domains.agents.api.channel_gateway import build_channel_gateway

        configure_channel_gateway(build_channel_gateway())

        # Create and configure global registry
        from src.domains.agents.registry import AgentRegistry

        registry = AgentRegistry(checkpointer=checkpointer, store=store)

        # Initialize catalogue with manifests (Phase 1 - Planner)
        from src.domains.agents.registry.catalogue_loader import initialize_catalogue

        initialize_catalogue(registry)
        logger.info("catalogue_manifests_initialized")

        # The manifests only become checkable once the catalogue above is
        # loaded: capability directives, safety categories, what an acting
        # tool owes the user, and where a read tool's data goes (ADR-347).
        _assert_catalogue_completeness(registry)

        # The draft executors register LAZILY (first use of ``DraftExecutor``),
        # so at this point the registry is empty — measured 2026-09-04: both
        # asserts below read it, and against an empty dict they passed on
        # anything. Populating it here is what makes their executor half mean
        # something at boot rather than only in CI.
        from src.domains.agents.services.draft_executor_registry import (
            ensure_executors_registered,
        )

        ensure_executors_registered()

        # The three ADR-263 completeness guards, run as one: they share a
        # shape, and four copies of it is four places for the re-raise to be
        # forgotten — which is exactly the defect the programme found, where
        # ``init_agent_registry`` caught its own guards and merely logged.
        _assert_effect_completeness(registry)

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

        if settings.sms_enabled:
            from src.domains.agents.graphs.sms_agent_builder import build_sms_agent

            registry.register_agent("sms_agent", build_sms_agent)

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

            # One agent, three mandates (phone-as-a-channel, lot 2): the dial
            # path indexes the mandate table without a fallback, so a call
            # kind nobody declared refuses the boot rather than running the
            # owner's call under the stranger's rules (ADR-085).
            try:
                from src.domains.telephony.mandates import assert_mandate_completeness

                assert_mandate_completeness()
            except RuntimeError as exc:
                logger.error("telephony_mandates_incomplete", error=str(exc), exc_info=True)
                raise StartupCompletenessError(f"Telephony mandates incomplete: {exc}") from exc

            # Live read-only tools of an owner call (lot 7): every allow-listed
            # tool must be a catalogue tool that only reads, exposing only
            # parameters its manifest declares — checked whether or not the
            # flag is on, so switching it on never discovers a stale list.
            try:
                from src.domains.agents.telephony.live_tools import (
                    assert_live_tools_completeness,
                )

                assert_live_tools_completeness(registry.list_tool_manifests(), registry=registry)
            except RuntimeError as exc:
                logger.error("telephony_live_tools_incomplete", error=str(exc), exc_info=True)
                raise StartupCompletenessError(f"Telephony live tools incomplete: {exc}") from exc

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

        # Validate the administrable capability registry (ADR-085 pattern):
        # a capability that names a catalogue agent — or, for the two that own
        # no agent, a TOOL — which does not exist would filter nothing while its
        # switch looks like it works. Checked here, after both the catalogue and
        # the agents are registered.
        try:
            from src.domains.feature_switches.registry import (
                assert_capability_agents_exist,
                assert_capability_tools_exist,
            )

            assert_capability_agents_exist(registry)
            assert_capability_tools_exist(registry)
        except AssertionError as exc:
            logger.error("capability_registry_incomplete", error=str(exc), exc_info=True)
            raise StartupCompletenessError(f"Capability registry incomplete: {exc}") from exc

        # Set as global registry
        set_global_registry(registry)

        logger.info(
            "agent_registry_initialized",
            registered_agents=list(registry.list_agents()),
            has_checkpointer=checkpointer is not None,
            has_store=store is not None,
        )
    except StartupCompletenessError:
        # A declaration defect: the promise of the guards above is that the
        # application refuses to start. Logging and continuing would leave the
        # global registry unset and the instance up with an EMPTY catalogue.
        logger.error("agent_registry_incomplete_boot_refused", exc_info=True)
        raise
    except (RuntimeError, ImportError, ValueError) as exc:
        logger.error("agent_registry_initialization_failed", error=str(exc), exc_info=True)
    return registry


async def init_semantic_services(registry: AgentRegistry | None) -> None:
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
        except Exception as exc:
            # Resilience boundary: semantic tool selection is an optimization
            # and its failure degrades to full-catalogue selection — it must
            # never kill the boot. The previous narrow tuple missed the
            # selector's FIRST real failure mode, the embeddings provider
            # refusing the call (GoogleGenerativeAIError extends Exception, not
            # RuntimeError): a depleted Gemini quota turned into "Application
            # startup failed" on every worker (demonstrator, 2026-08-15).
            # CancelledError is a BaseException and still propagates.
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


async def init_sandbox_egress() -> None:
    """Re-render the sandbox egress ruleset from the shared registry (ADR-298).

    The proxy holds one ruleset for the whole deployment and the live runs
    live in Redis: a worker that boots renders EVERY worker's runs, so a
    restart never revokes a token another worker is still serving. Best
    effort on purpose — a proxy that is down at boot must not stop the API;
    each network run is refused at act time, with the reason.
    """
    from src.infrastructure.observability.metrics_react import python_sandbox_egress_enabled

    # The gauge gates SandboxEgressProxyDown: without the overlay the proxy
    # does not exist, and its absence must not page anyone.
    python_sandbox_egress_enabled.set(1 if settings.python_sandbox_egress_enabled else 0)
    if not settings.python_sandbox_egress_enabled:
        return
    from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
    from src.domains.agents.python_sandbox.egress.service import deployment_publisher

    try:
        publisher = await deployment_publisher()
        await publisher.publish()
        logger.info("sandbox_egress_ruleset_published_at_boot")
    except EgressProxyUnavailable as exc:
        logger.warning("sandbox_egress_boot_publish_failed", reason=str(exc))
