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

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.core.constants import DEFAULT_TOOL_TIMEOUT_MS

from .catalogue import AgentManifest

if TYPE_CHECKING:
    from .agent_registry import AgentRegistry

# ============================================================================
# Agent Manifest: contact_agent (domain=contact, result_key=contacts)
# ============================================================================

CONTACT_AGENT_MANIFEST = AgentManifest(
    name="contact_agent",
    description="Agent spécialisé dans les opérations Google Contacts (recherche, création, modification, suppression)",
    tools=[
        "get_contacts_tool",  # Unified tool (v2.0 - replaces search + list + details)
        "create_contact_tool",
        "update_contact_tool",
        "delete_contact_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: context_agent
# ============================================================================

CONTEXT_AGENT_MANIFEST = AgentManifest(
    name="context_agent",
    description=(
        "Agent générique pour la résolution de références contextuelles. "
        "Gère les références conversationnelles comme 'le premier', "
        "'la dernière', '2ème', etc. "
        "Supporte batch operations via get_context_list pour références plurielles. "
        "Compatible avec tous les domaines (contacts, emails, events)."
    ),
    tools=[
        "resolve_reference",
        "set_current_item",
        "get_context_state",
        "list_active_domains",
        "get_context_list",
    ],
    max_parallel_runs=5,  # Context operations are fast and local
    default_timeout_ms=5000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: email_agent (domain=email, result_key=emails)
# ============================================================================

EMAIL_AGENT_MANIFEST = AgentManifest(
    name="email_agent",
    description="Agent spécialisé dans les opérations Gmail (recherche, lecture, envoi, réponse, transfert, suppression d'emails)",
    tools=[
        "get_emails_tool",  # Unified tool (v2.0 - replaces search + details)
        "send_email_tool",
        "reply_email_tool",
        "forward_email_tool",
        "delete_email_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: event_agent (domain=event, result_key=events)
# ============================================================================

EVENT_AGENT_MANIFEST = AgentManifest(
    name="event_agent",
    description=(
        "Agent spécialisé dans les opérations Google Calendar. "
        "Liste des calendriers disponibles, recherche, création, modification et suppression d'événements. "
        "Gestion de l'agenda et des rendez-vous. "
        "Les opérations d'écriture (création, modification, suppression) "
        "nécessitent une confirmation utilisateur via HITL."
    ),
    tools=[
        "get_events_tool",  # Unified tool (v2.0 - replaces search + details)
        "create_event_tool",
        "update_event_tool",
        "delete_event_tool",
        "list_calendars_tool",  # Metadata tool (list containers)
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: file_agent (domain=file, result_key=files)
# ============================================================================

FILE_AGENT_MANIFEST = AgentManifest(
    name="file_agent",
    description=(
        "Agent spécialisé dans les opérations Google Drive. "
        "Recherche, liste et lecture de fichiers (documents, feuilles de calcul, "
        "présentations, PDFs, images). Accès au contenu des fichiers."
    ),
    tools=[
        "get_files_tool",  # Unified tool (v2.0 - replaces search + list + details)
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: task_agent (domain=task, result_key=tasks)
# ============================================================================

TASK_AGENT_MANIFEST = AgentManifest(
    name="task_agent",
    description=(
        "Agent spécialisé dans les opérations Google Tasks. "
        "Liste, création, modification, complétion et suppression de tâches. "
        "Gestion des listes de tâches et des todos. "
        "Les opérations d'écriture nécessitent une confirmation utilisateur via HITL."
    ),
    tools=[
        "get_tasks_tool",  # Unified tool (v2.0 - replaces list + details)
        "create_task_tool",
        "update_task_tool",
        "delete_task_tool",
        "complete_task_tool",
        "list_task_lists_tool",  # Metadata tool (list containers)
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: weather_agent (LOT 10)
# ============================================================================

WEATHER_AGENT_MANIFEST = AgentManifest(
    name="weather_agent",
    description=(
        "Agent spécialisé dans les informations météorologiques. "
        "Météo actuelle, prévisions sur plusieurs jours, prévisions horaires. "
        "Température, humidité, précipitations, vent, etc. "
        "Utilise l'API OpenWeatherMap."
    ),
    tools=[
        "get_current_weather_tool",
        "get_weather_forecast_tool",
        "get_hourly_forecast_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=10000,  # Weather API can be slower
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: wikipedia_agent (LOT 10)
# ============================================================================

WIKIPEDIA_AGENT_MANIFEST = AgentManifest(
    name="wikipedia_agent",
    description=(
        "Agent spécialisé dans la recherche d'informations encyclopédiques. "
        "Recherche Wikipedia, résumés, articles complets, articles connexes. "
        "Pour les questions de culture générale, biographies, histoire, etc."
    ),
    tools=[
        "search_wikipedia_tool",
        "get_wikipedia_summary_tool",
        "get_wikipedia_article_tool",
        "get_wikipedia_related_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=10000,  # Wikipedia API can be slower
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: query_agent (LOT 10 - INTELLIA LocalQueryEngine)
# ============================================================================

QUERY_AGENT_MANIFEST = AgentManifest(
    name="query_agent",
    description=(
        "Agent spécialisé dans l'analyse des données en mémoire. "
        "Permet de filtrer, trier, grouper et trouver des patterns "
        "(comme les doublons) dans les données déjà récupérées par d'autres agents. "
        "Fonctionne avec le LocalQueryEngine pour les requêtes cross-domain."
    ),
    tools=[
        "local_query_engine_tool",
    ],
    max_parallel_runs=5,  # Local operations are fast
    default_timeout_ms=5000,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: perplexity_agent (LOT 10 - Web Search)
# ============================================================================

PERPLEXITY_AGENT_MANIFEST = AgentManifest(
    name="perplexity_agent",
    description=(
        "Agent spécialisé dans la recherche web en temps réel. "
        "Utilise Perplexity AI pour rechercher des informations actuelles sur internet, "
        "répondre à des questions avec des citations de sources, "
        "et fournir des informations à jour sur les actualités et événements récents."
    ),
    tools=[
        "perplexity_search_tool",
        "perplexity_ask_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=60000,  # Perplexity can take time for complex queries
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: place_agent (domain=place, result_key=places)
# ============================================================================

PLACE_AGENT_MANIFEST = AgentManifest(
    name="place_agent",
    description=(
        "Agent spécialisé dans la recherche de lieux et points d'intérêt. "
        "Recherche de restaurants, hôtels, commerces, services à proximité. "
        "Détails sur les lieux: adresse, horaires, avis, prix. "
        "Localisation actuelle: reverse geocoding pour répondre à 'où suis-je?'. "
        "Utilise Google Places API et Geocoding API."
    ),
    tools=[
        "get_places_tool",  # Unified tool (v2.0 - replaces search + details)
        "get_current_location_tool",  # Reverse geocoding for location queries
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: route_agent (domain=route, result_key=routes)
# ============================================================================

ROUTE_AGENT_MANIFEST = AgentManifest(
    name="route_agent",
    description=(
        "Agent spécialisé dans les itinéraires et directions. "
        "Calcul de trajets entre deux points, temps de trajet, distance. "
        "Plusieurs modes de transport: voiture, à pied, vélo, transports en commun. "
        "Options: éviter péages, autoroutes, ferries. "
        "Matrice de distances pour optimisation multi-points. "
        "Utilise Google Routes API v2."
    ),
    tools=[
        "get_route_tool",  # Directions A to B
        "get_route_matrix_tool",  # Distance/duration matrix
    ],
    max_parallel_runs=1,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: brave_agent (domain=brave, result_key=braves)
# ============================================================================

BRAVE_AGENT_MANIFEST = AgentManifest(
    name="brave_agent",
    description=(
        "Agent spécialisé dans la recherche web via Brave Search API. "
        "Recherche web générale et recherche d'actualités. "
        "Utilise API key authentication (pas OAuth)."
    ),
    tools=[
        "brave_search_tool",
        "brave_news_tool",
    ],
    max_parallel_runs=3,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Agent Manifest: web_search_agent (Unified Triple Source Search)
# ============================================================================

WEB_SEARCH_AGENT_MANIFEST = AgentManifest(
    name="web_search_agent",
    description=(
        "Agent spécialisé dans la recherche web unifiée Triple Source. "
        "Combine Perplexity AI (synthèse), Brave Search (URLs), et Wikipedia (encyclopédie) "
        "en parallèle. Fallback chain: continue si une source échoue. "
        "Wikipedia toujours disponible (pas d'authentification requise)."
    ),
    tools=[
        "unified_web_search_tool",
    ],
    max_parallel_runs=2,  # Lower due to triple source orchestration
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS * 2,  # Double timeout for parallel calls
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# ============================================================================
# Agent Manifest: web_fetch_agent (Web Page Content Extraction — evolution F1)
# ============================================================================

WEB_FETCH_AGENT_MANIFEST = AgentManifest(
    name="web_fetch_agent",
    description=(
        "Agent spécialisé dans la récupération et l'extraction de contenu de pages web. "
        "Lit le contenu complet d'une URL, extrait l'article principal ou la page entière. "
        "Retourne du texte Markdown nettoyé. Ne recherche PAS sur le web "
        "(utiliser web_search_agent pour la recherche)."
    ),
    tools=[
        "fetch_web_page_tool",
    ],
    max_parallel_runs=2,
    default_timeout_ms=DEFAULT_TOOL_TIMEOUT_MS,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# ============================================================================
# Initialization Function
# ============================================================================


def initialize_catalogue(registry: AgentRegistry) -> None:
    """
    Initialise le catalogue avec les manifestes Phase 5 + LOT 9/10.

    NAMING CONVENTION: domain=entity(singular), result_key=domain+"s", agent=domain+"_agent"

    Cette fonction charge et enregistre :
    - 14 agent manifests :
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
        registry: Instance d'AgentRegistry

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
        create_event_catalogue_manifest,
        delete_event_catalogue_manifest,
        get_events_catalogue_manifest,  # Unified (v2.0)
        list_calendars_catalogue_manifest,
        update_event_catalogue_manifest,
    )
    from src.domains.agents.context.catalogue_manifests import (
        get_context_list_catalogue_manifest,
        get_context_state_catalogue_manifest,
        list_active_domains_catalogue_manifest,
        resolve_reference_catalogue_manifest,
        set_current_item_catalogue_manifest,
    )
    from src.domains.agents.drive.catalogue_manifests import (
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
    from src.domains.agents.google_contacts.catalogue_manifests import (
        create_contact_catalogue_manifest,
        delete_contact_catalogue_manifest,
        get_contacts_catalogue_manifest,  # Unified (v2.0)
        update_contact_catalogue_manifest,
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

    # Register agent manifests - Internal tools (No OAuth)
    registry.register_agent_manifest(REMINDER_AGENT_MANIFEST)

    # Register Google Contacts tool manifests (Unified v2.0)
    registry.register_tool_manifest(get_contacts_catalogue_manifest)  # Unified
    registry.register_tool_manifest(create_contact_catalogue_manifest)
    registry.register_tool_manifest(update_contact_catalogue_manifest)
    registry.register_tool_manifest(delete_contact_catalogue_manifest)

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

    # Register LOT 9 tool manifests (Google Calendar, Drive, Tasks) - Unified v2.0
    registry.register_tool_manifest(get_events_catalogue_manifest)  # Unified
    registry.register_tool_manifest(create_event_catalogue_manifest)
    registry.register_tool_manifest(update_event_catalogue_manifest)
    registry.register_tool_manifest(delete_event_catalogue_manifest)
    registry.register_tool_manifest(list_calendars_catalogue_manifest)  # Metadata

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

    # Register Skills tool manifests (agentskills.io standard)
    from src.domains.skills.catalogue_manifests import (
        activate_skill_catalogue_manifest,
        read_skill_resource_catalogue_manifest,
        run_skill_script_catalogue_manifest,
    )

    registry.register_tool_manifest(activate_skill_catalogue_manifest)
    registry.register_tool_manifest(read_skill_resource_catalogue_manifest)
    registry.register_tool_manifest(run_skill_script_catalogue_manifest)

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


def _validate_context_key_registrations(registry: AgentRegistry, logger) -> None:
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


def _register_tool_instances(registry: AgentRegistry, logger) -> None:
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
