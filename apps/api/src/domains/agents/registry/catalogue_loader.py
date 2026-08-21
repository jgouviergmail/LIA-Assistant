"""
Loader pour les manifestes du catalogue Phase 5 + LOT 9/10.

NAMING CONVENTION (2026-01 Unification):
  - domain = entity (singular): contact, email, event, file, task, place, route
  - result_key = domain + "s": contacts, emails, events, files, tasks, places, routes
  - agent_name = domain + "_agent": contact_agent, email_agent, etc.

Ce module charge les manifestes de production depuis:
- 14 agent manifests:
  * contact_agent (Google Contacts)
  * context_agent (Cross-domain utilities)
  * email_agent (Gmail)
  * event_agent (Google Calendar)
  * file_agent (Google Drive)
  * task_agent (Google Tasks)
  * weather_agent (OpenWeatherMap)
  * wikipedia_agent (Wikipedia)
  * query_agent (INTELLIA LocalQueryEngine)
  * perplexity_agent (Web Search)
  * place_agent (Google Places)
  * route_agent (Google Routes)
  * reminder_agent (Internal reminders)
  * web_fetch_agent (Web Page Content Extraction)
- 30+ tool manifests across all domains

Usage:
    from .catalogue_loader import initialize_catalogue
    from .agent_registry import AgentRegistry

    registry = AgentRegistry(...)
    initialize_catalogue(registry)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .agent_manifest_definitions import (
    BRAVE_AGENT_MANIFEST,
    BROWSER_AGENT_MANIFEST,
    CONTACT_AGENT_MANIFEST,
    CONTEXT_AGENT_MANIFEST,
    DEVOPS_AGENT_MANIFEST,
    EMAIL_AGENT_MANIFEST,
    EVENT_AGENT_MANIFEST,
    FILE_AGENT_MANIFEST,
    PERPLEXITY_AGENT_MANIFEST,
    PLACE_AGENT_MANIFEST,
    QUERY_AGENT_MANIFEST,
    ROUTE_AGENT_MANIFEST,
    TASK_AGENT_MANIFEST,
    WEATHER_AGENT_MANIFEST,
    WEB_FETCH_AGENT_MANIFEST,
    WEB_SEARCH_AGENT_MANIFEST,
    WIKIPEDIA_AGENT_MANIFEST,
)

if TYPE_CHECKING:
    import structlog

    from .agent_registry import AgentRegistry

# ============================================================================


def initialize_catalogue(registry: AgentRegistry) -> None:
    """
    Initialize the catalogue with Phase 5 + LOT 9/10 manifests.

    NAMING CONVENTION: domain=entity(singular), result_key=domain+"s", agent=domain+"_agent"

    This function loads and registers:
    - 14 agent manifests:
      * contact_agent (Google Contacts)
      * context_agent (Cross-domain utilities)
      * email_agent (Gmail)
      * event_agent (Google Calendar)
      * file_agent (Google Drive)
      * task_agent (Google Tasks)
      * weather_agent (OpenWeatherMap)
      * wikipedia_agent (Wikipedia)
      * query_agent (INTELLIA LocalQueryEngine)
      * perplexity_agent (Web Search)
      * place_agent (Google Places)
      * route_agent (Google Routes)
      * reminder_agent (Internal reminders)
      * web_fetch_agent (Web Page Content Extraction)

    - 30+ tool manifests across all domains

    Args:
        registry: AgentRegistry instance

    Example:
        >>> from .agent_registry import AgentRegistry
        >>> registry = AgentRegistry(...)
        >>> initialize_catalogue(registry)

    Note:
        Les manifestes de tools sont maintenant définis dans des fichiers séparés
        pour améliorer la maintenabilité et permettre une évolution indépendante
        de chaque domaine.
    """
    from src.infrastructure.observability.logging import get_logger

    logger = get_logger(__name__)

    # ============================================================================
    # PHASE 5 MIGRATION: Use production catalogue manifests
    # ============================================================================

    # Import Phase 5 manifests from dedicated modules
    # Import LOT 9 manifests (Google Calendar, Drive, Tasks)
    from src.domains.agents.brave.catalogue_manifests import (
        brave_news_catalogue_manifest,
        brave_search_catalogue_manifest,
    )
    from src.domains.agents.calendar.catalogue_manifests import (
        CALENDAR_TOOL_MANIFESTS,
    )
    from src.domains.agents.context.catalogue_manifests import (
        get_context_list_catalogue_manifest,
        get_context_state_catalogue_manifest,
        list_active_domains_catalogue_manifest,
        resolve_reference_catalogue_manifest,
        set_current_item_catalogue_manifest,
    )
    from src.domains.agents.drive.catalogue_manifests import (
        WORKSPACE_DOCS_TOOL_MANIFESTS,
        get_files_catalogue_manifest,  # Unified (v2.0)
    )
    from src.domains.agents.emails.catalogue_manifests import (
        apply_labels_catalogue_manifest,
        create_label_catalogue_manifest,
        delete_email_catalogue_manifest,
        delete_label_catalogue_manifest,
        forward_email_catalogue_manifest,
        get_emails_catalogue_manifest,  # Unified (v2.0)
        list_labels_catalogue_manifest,
        remove_labels_catalogue_manifest,
        reply_email_catalogue_manifest,
        send_email_catalogue_manifest,
        update_label_catalogue_manifest,
    )
    from src.domains.agents.emails.settings_catalogue_manifests import (
        GMAIL_SETTINGS_TOOL_MANIFESTS,
    )
    from src.domains.agents.google_contacts.catalogue_manifests import (
        ALL_CONTACTS_TOOL_MANIFESTS,
    )
    from src.domains.agents.perplexity.catalogue_manifests import (
        perplexity_ask_catalogue_manifest,
        perplexity_search_catalogue_manifest,
    )
    from src.domains.agents.places.catalogue_manifests import (
        get_current_location_catalogue_manifest,
        get_places_catalogue_manifest,  # Unified (v2.0)
    )
    from src.domains.agents.query.catalogue_manifests import (
        local_query_engine_catalogue_manifest,
    )

    # Import Reminder manifests (Internal tools - No OAuth)
    from src.domains.agents.reminders.catalogue_manifests import (
        REMINDER_AGENT_MANIFEST,
        cancel_reminder_catalogue_manifest,
        create_reminder_catalogue_manifest,
        list_reminders_catalogue_manifest,
    )
    from src.domains.agents.routes.catalogue_manifests import (
        get_route_catalogue_manifest,
        get_route_matrix_catalogue_manifest,
    )
    from src.domains.agents.tasks.catalogue_manifests import (
        complete_task_catalogue_manifest,
        create_task_catalogue_manifest,
        delete_task_catalogue_manifest,
        get_tasks_catalogue_manifest,  # Unified (v2.0)
        list_task_lists_catalogue_manifest,
        update_task_catalogue_manifest,
    )

    # Import LOT 10 manifests (Weather, Wikipedia, Perplexity, Places)
    from src.domains.agents.weather.catalogue_manifests import (
        ENVIRONMENT_TOOL_MANIFESTS,
        get_current_weather_catalogue_manifest,
        get_hourly_forecast_catalogue_manifest,
        get_weather_forecast_catalogue_manifest,
    )
    from src.domains.agents.web_fetch.catalogue_manifests import (
        fetch_web_page_catalogue_manifest,
    )
    from src.domains.agents.web_search.catalogue_manifests import (
        unified_web_search_catalogue_manifest,
    )
    from src.domains.agents.wikipedia.catalogue_manifests import (
        get_wikipedia_article_catalogue_manifest,
        get_wikipedia_related_catalogue_manifest,
        get_wikipedia_summary_catalogue_manifest,
        search_wikipedia_catalogue_manifest,
    )

    # Register agent manifests - Phase 5 (original agents)
    # NAMING: domain=entity(singular), agent_name=domain_agent
    registry.register_agent_manifest(CONTACT_AGENT_MANIFEST)
    registry.register_agent_manifest(CONTEXT_AGENT_MANIFEST)
    registry.register_agent_manifest(EMAIL_AGENT_MANIFEST)

    # Register agent manifests - LOT 9 (Google services)
    registry.register_agent_manifest(EVENT_AGENT_MANIFEST)
    registry.register_agent_manifest(FILE_AGENT_MANIFEST)
    registry.register_agent_manifest(TASK_AGENT_MANIFEST)

    # Register agent manifests - LOT 10 (External services + INTELLIA)
    registry.register_agent_manifest(WEATHER_AGENT_MANIFEST)
    registry.register_agent_manifest(WIKIPEDIA_AGENT_MANIFEST)
    registry.register_agent_manifest(QUERY_AGENT_MANIFEST)
    registry.register_agent_manifest(PERPLEXITY_AGENT_MANIFEST)
    registry.register_agent_manifest(PLACE_AGENT_MANIFEST)
    registry.register_agent_manifest(ROUTE_AGENT_MANIFEST)
    registry.register_agent_manifest(BRAVE_AGENT_MANIFEST)
    registry.register_agent_manifest(WEB_SEARCH_AGENT_MANIFEST)
    registry.register_agent_manifest(WEB_FETCH_AGENT_MANIFEST)

    # Register agent manifests - Browser (F7 - always registered, activation via admin panel)
    registry.register_agent_manifest(BROWSER_AGENT_MANIFEST)

    # Register Browser tool manifests (F7)
    from src.domains.agents.browser.catalogue_manifests import (
        browser_task_catalogue_manifest,
    )

    # Only register the primary task tool for planner discovery.
    # Individual tools (navigate, snapshot, click, fill, press_key) are used
    # internally by the browser_task_tool ReAct loop — NOT by the planner.
    registry.register_tool_manifest(browser_task_catalogue_manifest)

    # Register agent manifests - Internal tools (No OAuth)
    registry.register_agent_manifest(REMINDER_AGENT_MANIFEST)

    # Register Health Metrics agents + tools (v1.17.2, feature-flag gated)
    from src.core.config import settings as _app_settings

    if getattr(_app_settings, "health_metrics_enabled", False):
        from src.domains.agents.health.catalogue_manifests import (
            HEALTH_AGENT_MANIFESTS,
            HEALTH_TOOL_MANIFESTS,
        )

        for manifest in HEALTH_AGENT_MANIFESTS:
            registry.register_agent_manifest(manifest)
        for tool_manifest in HEALTH_TOOL_MANIFESTS:
            registry.register_tool_manifest(tool_manifest)

    # Register family manifest tuples: contacts (lot C), Gmail settings
    # (lot I), calendar incl. availability (lot B), workspace docs (lot F),
    # environment (lot E). Manifests register by name — relative order across
    # families is irrelevant.
    for family_manifest in (
        *ALL_CONTACTS_TOOL_MANIFESTS,
        *GMAIL_SETTINGS_TOOL_MANIFESTS,
        *CALENDAR_TOOL_MANIFESTS,
        *WORKSPACE_DOCS_TOOL_MANIFESTS,
        *ENVIRONMENT_TOOL_MANIFESTS,
    ):
        registry.register_tool_manifest(family_manifest)

    # Register Emails tool manifests (Unified v2.0)
    registry.register_tool_manifest(get_emails_catalogue_manifest)  # Unified
    registry.register_tool_manifest(send_email_catalogue_manifest)
    registry.register_tool_manifest(reply_email_catalogue_manifest)
    registry.register_tool_manifest(forward_email_catalogue_manifest)
    registry.register_tool_manifest(delete_email_catalogue_manifest)

    # Register Gmail Labels tool manifests
    registry.register_tool_manifest(list_labels_catalogue_manifest)
    registry.register_tool_manifest(create_label_catalogue_manifest)
    registry.register_tool_manifest(update_label_catalogue_manifest)
    registry.register_tool_manifest(delete_label_catalogue_manifest)
    registry.register_tool_manifest(apply_labels_catalogue_manifest)
    registry.register_tool_manifest(remove_labels_catalogue_manifest)

    # Register Context tool manifests (Phase 5 production manifests)
    registry.register_tool_manifest(resolve_reference_catalogue_manifest)
    registry.register_tool_manifest(set_current_item_catalogue_manifest)
    registry.register_tool_manifest(get_context_state_catalogue_manifest)
    registry.register_tool_manifest(list_active_domains_catalogue_manifest)
    registry.register_tool_manifest(get_context_list_catalogue_manifest)

    # Register LOT 9 tool manifests (Google Drive, Tasks) - Unified v2.0
    # (calendar + workspace docs families registered in the family loop above)
    registry.register_tool_manifest(get_files_catalogue_manifest)  # Unified

    registry.register_tool_manifest(get_tasks_catalogue_manifest)  # Unified
    registry.register_tool_manifest(create_task_catalogue_manifest)
    registry.register_tool_manifest(update_task_catalogue_manifest)
    registry.register_tool_manifest(delete_task_catalogue_manifest)
    registry.register_tool_manifest(complete_task_catalogue_manifest)
    registry.register_tool_manifest(list_task_lists_catalogue_manifest)  # Metadata

    # Register LOT 10 tool manifests (Weather, Wikipedia, Perplexity, Places)
    registry.register_tool_manifest(get_current_weather_catalogue_manifest)
    registry.register_tool_manifest(get_weather_forecast_catalogue_manifest)
    registry.register_tool_manifest(get_hourly_forecast_catalogue_manifest)
    # (environment family registered in the family loop above)

    registry.register_tool_manifest(search_wikipedia_catalogue_manifest)
    registry.register_tool_manifest(get_wikipedia_summary_catalogue_manifest)
    registry.register_tool_manifest(get_wikipedia_article_catalogue_manifest)
    registry.register_tool_manifest(get_wikipedia_related_catalogue_manifest)

    registry.register_tool_manifest(perplexity_search_catalogue_manifest)
    registry.register_tool_manifest(perplexity_ask_catalogue_manifest)

    # Brave Search tools
    registry.register_tool_manifest(brave_search_catalogue_manifest)
    registry.register_tool_manifest(brave_news_catalogue_manifest)

    # Register Web Search tool manifest (Unified Triple Source)
    registry.register_tool_manifest(unified_web_search_catalogue_manifest)

    # Register Web Fetch tool manifest (evolution F1 — Web Page Content Extraction)
    registry.register_tool_manifest(fetch_web_page_catalogue_manifest)

    registry.register_tool_manifest(get_places_catalogue_manifest)  # Unified
    registry.register_tool_manifest(get_current_location_catalogue_manifest)

    # Register Routes tool manifests (Google Routes - Directions)
    registry.register_tool_manifest(get_route_catalogue_manifest)
    registry.register_tool_manifest(get_route_matrix_catalogue_manifest)

    # Register Query tool manifests (INTELLIA LocalQueryEngine)
    registry.register_tool_manifest(local_query_engine_catalogue_manifest)

    # Register Reminder tool manifests (Internal tools - No OAuth)
    registry.register_tool_manifest(create_reminder_catalogue_manifest)
    registry.register_tool_manifest(list_reminders_catalogue_manifest)
    registry.register_tool_manifest(cancel_reminder_catalogue_manifest)

    # Register Hue tool manifests (Philips Hue Smart Home)
    # Import hue_tools to trigger ContextTypeRegistry.register() at module level
    import src.domains.agents.tools.hue_tools  # noqa: F401
    from src.domains.agents.hue.catalogue_manifests import (
        activate_hue_scene_catalogue_manifest,
        control_hue_light_catalogue_manifest,
        control_hue_room_catalogue_manifest,
        hue_agent_manifest,
        list_hue_lights_catalogue_manifest,
        list_hue_rooms_catalogue_manifest,
        list_hue_scenes_catalogue_manifest,
    )

    registry.register_agent_manifest(hue_agent_manifest)
    registry.register_tool_manifest(list_hue_lights_catalogue_manifest)
    registry.register_tool_manifest(control_hue_light_catalogue_manifest)
    registry.register_tool_manifest(list_hue_rooms_catalogue_manifest)
    registry.register_tool_manifest(control_hue_room_catalogue_manifest)
    registry.register_tool_manifest(list_hue_scenes_catalogue_manifest)
    registry.register_tool_manifest(activate_hue_scene_catalogue_manifest)

    # Register Skills tool manifests (agentskills.io standard)
    from src.domains.skills.catalogue_manifests import (
        activate_skill_catalogue_manifest,
        import_user_skill_catalogue_manifest,
        read_skill_resource_catalogue_manifest,
        run_skill_script_catalogue_manifest,
    )

    registry.register_tool_manifest(activate_skill_catalogue_manifest)
    registry.register_tool_manifest(read_skill_resource_catalogue_manifest)
    registry.register_tool_manifest(run_skill_script_catalogue_manifest)
    registry.register_tool_manifest(import_user_skill_catalogue_manifest)

    # Register Sub-Agent delegation tool (F6 — transversal, always in catalogue)
    from src.core.config import get_settings as _get_settings

    if getattr(_get_settings(), "sub_agents_enabled", False):
        from src.domains.agents.sub_agents.catalogue_manifests import (
            SUB_AGENT_MANIFEST,
            delegate_to_sub_agent_catalogue_manifest,
        )

        registry.register_agent_manifest(SUB_AGENT_MANIFEST)
        registry.register_tool_manifest(delegate_to_sub_agent_catalogue_manifest)

    # Register Image Generation tool manifest (feature-flagged)
    if getattr(_get_settings(), "image_generation_enabled", False):
        from src.domains.agents.image_generation import catalogue_manifests as _img_manifests

        registry.register_agent_manifest(_img_manifests.image_agent_manifest)
        registry.register_tool_manifest(_img_manifests.generate_image_catalogue_manifest)
        registry.register_tool_manifest(_img_manifests.edit_image_catalogue_manifest)

    # Register Document Generation manifests (feature-flagged, ADR-226)
    if getattr(_get_settings(), "document_generation_enabled", False):
        from src.domains.agents.document_generation import catalogue_manifests as _doc_manifests

        registry.register_agent_manifest(_doc_manifests.document_agent_manifest)
        registry.register_tool_manifest(_doc_manifests.generate_document_catalogue_manifest)

    # DevOps: Claude CLI remote server management (feature-flagged)
    if getattr(_get_settings(), "devops_enabled", False):
        from src.domains.agents.devops.catalogue_manifests import (
            claude_server_task_catalogue_manifest,
        )

        registry.register_agent_manifest(DEVOPS_AGENT_MANIFEST)
        registry.register_tool_manifest(claude_server_task_catalogue_manifest)

    # Telephony: agentic outbound calls (per-user connector, feature-flagged)
    if getattr(_get_settings(), "telephony_enabled", False):
        from src.domains.agents.telephony.catalogue_manifests import (
            TELEPHONY_AGENT_MANIFEST,
            place_phone_call_catalogue_manifest,
        )

        registry.register_agent_manifest(TELEPHONY_AGENT_MANIFEST)
        registry.register_tool_manifest(place_phone_call_catalogue_manifest)

    # Interdomain-program manifests (ADR-140/141+) — registration delegated
    # to one aggregator (loader is frozen at its size cap; net-zero here).
    # AFTER the flag-gated agent blocks above: the aggregator registers tools
    # belonging to those agents (e.g. get_calls_tool → telephony_agent), and a
    # tool registered before its agent logs catalogue_tool_orphan on every
    # boot of every worker (prod noise, 2026-08-20). Order guarded by
    # tests/unit/domains/agents/registry/test_tool_manifests_follow_their_agent.py.
    from src.domains.agents.registry.program_manifests import register_program_manifests

    register_program_manifests(registry)

    # Dynamic counting from registry (no more hardcoded values)
    registered_agents = list(registry._agent_manifests.keys())
    registered_tools = list(registry._tool_manifests.keys())

    logger.info(
        "catalogue_initialized",
        agent_count=len(registered_agents),
        tool_count=len(registered_tools),
        agents=sorted(registered_agents),
        tools=sorted(registered_tools),
        source="external_manifest_files",
    )

    # Phase 3: Build domain index for dynamic filtering (Multi-Domain Architecture)
    # This enables export_for_prompt_filtered() to efficiently load only relevant domains
    registry._build_domain_index()

    logger.info(
        "catalogue_domain_index_ready",
        message="Domain index built successfully. Dynamic filtering enabled.",
    )

    # Phase 4 Semantic Architecture: Register tool instances for direct invocation
    # This enables tool_executor_node to invoke tools without going through agent subgraphs
    # IMPORTANT: Must run BEFORE context_key validation because tool module imports
    # trigger ContextTypeRegistry.register() calls at module level.
    _register_tool_instances(registry, logger)

    # Phase 5: Validate context_key registration (fail-fast pattern)
    # Every context_key in a tool manifest MUST be registered in ContextTypeRegistry
    _validate_context_key_registrations(registry, logger)


def _validate_context_key_registrations(
    registry: AgentRegistry, logger: structlog.stdlib.BoundLogger
) -> None:
    """
    Validate that all context_key values in tool manifests are registered in ContextTypeRegistry.

    This is a fail-fast validation to catch configuration errors at startup.
    Missing registrations cause silent data loss (tools work but data isn't saved to registry).

    Args:
        registry: AgentRegistry instance with registered tool manifests
        logger: Logger instance

    Raises:
        ValueError: If any context_key is not registered (in development mode)

    Note:
        In production, missing registrations are logged as warnings but don't block startup.
        This allows graceful degradation while alerting operators.
    """
    from src.core.config import get_settings
    from src.domains.agents.context.registry import ContextTypeRegistry

    # Collect all unique context_keys from tool manifests
    context_keys_in_manifests: set[str] = set()
    tool_context_map: dict[str, list[str]] = {}  # context_key -> [tool_names]

    for tool_name, manifest in registry._tool_manifests.items():
        if hasattr(manifest, "context_key") and manifest.context_key:
            context_key = manifest.context_key
            context_keys_in_manifests.add(context_key)
            if context_key not in tool_context_map:
                tool_context_map[context_key] = []
            tool_context_map[context_key].append(tool_name)

    # Get registered context types
    registered_types = set(ContextTypeRegistry.list_all())

    # Find missing registrations
    missing_registrations = context_keys_in_manifests - registered_types

    if missing_registrations:
        # Build detailed error message
        details = []
        for context_key in sorted(missing_registrations):
            tools = tool_context_map.get(context_key, [])
            details.append(f"  - '{context_key}' used by: {', '.join(tools)}")

        error_msg = (
            f"Context type registration validation FAILED.\n"
            f"The following context_key values are used in tool manifests "
            f"but NOT registered in ContextTypeRegistry:\n"
            f"{chr(10).join(details)}\n\n"
            f"Fix: Add ContextTypeRegistry.register() calls in the corresponding tool modules.\n"
            f"See weather_tools.py for an example pattern.\n\n"
            f"Registered types: {sorted(registered_types)}"
        )

        settings = get_settings()
        if settings.debug:
            # In development: fail fast
            logger.error(
                "context_key_validation_failed",
                missing_count=len(missing_registrations),
                missing_keys=sorted(missing_registrations),
                registered_keys=sorted(registered_types),
            )
            raise ValueError(error_msg)
        else:
            # In production: warn but continue (graceful degradation)
            logger.warning(
                "context_key_validation_warning",
                message="Some context_key values are not registered. Data persistence may be affected.",
                missing_count=len(missing_registrations),
                missing_keys=sorted(missing_registrations),
                registered_keys=sorted(registered_types),
            )
    else:
        logger.info(
            "context_key_validation_passed",
            context_key_count=len(context_keys_in_manifests),
            all_registered=True,
            keys=sorted(context_keys_in_manifests),
        )


def _register_tool_instances(registry: AgentRegistry, logger: structlog.stdlib.BoundLogger) -> None:
    """
    Register tool instances from the central tool registry.

    This function uses the central tool_registry module which provides
    auto-registration via @registered_tool decorator and backward-compatible
    collection of tools using @tool decorator.

    Architecture (2025 Refactoring):
    - Central tool_registry is the single source of truth
    - Tools auto-register via @registered_tool decorator
    - Legacy tools using @tool are auto-collected on module import
    - This function copies tools to AgentRegistry for backward compatibility

    Args:
        registry: AgentRegistry instance
        logger: Logger instance

    Adding new tools:
        1. Create tool with @registered_tool decorator in *_tools.py
        2. That's it! Tool is automatically available everywhere.
    """
    from src.domains.agents.tools.tool_registry import (
        ensure_tools_loaded,
        get_all_tools,
    )

    # Load all tools from the central registry
    ensure_tools_loaded()

    # Get all registered tools
    all_tools = get_all_tools()

    # Copy tools to AgentRegistry for backward compatibility
    registered_count = 0
    for tool_name, tool_instance in all_tools.items():
        try:
            registry.register_tool_instance(tool_name, tool_instance)
            registered_count += 1
        except ValueError:
            # Already registered (shouldn't happen, but handle gracefully)
            logger.debug("tool_instance_already_in_agent_registry", tool_name=tool_name)

    logger.info(
        "tool_instances_registered_from_central_registry",
        registered_count=registered_count,
        tools=list(all_tools.keys()),
    )
