"""Agent manifest definitions (extracted from ``catalogue_loader``, 2026-08).

Pure declarative data: one ``AgentManifest`` per orchestrated agent. The
loader imports them and registers each; keeping the declarations here keeps
the loader an orchestration module (file-size ratchet doctrine).

NAMING: domain=entity(singular), agent_name=domain_agent (see the loader).
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.config import settings

from .catalogue import AgentManifest

# ============================================================================
# Agent Manifest: contact_agent (domain=contact, result_key=contacts)
# ============================================================================

CONTACT_AGENT_MANIFEST = AgentManifest(
    name="contact_agent",
    description="Agent spécialisé dans les opérations Google Contacts (recherche, création, modification, suppression)",
    tools=[
        "get_contacts_tool",  # Unified tool (v2.0 - replaces search + list + details)
        "get_person_overview_tool",  # Cross-domain person-360 (ADR-141)
        "create_contact_tool",
        "update_contact_tool",
        "delete_contact_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
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
        "get_gmail_settings_tool",
        "set_vacation_responder_tool",
        "create_email_filter_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms,
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
        "read_spreadsheet_tool",
        "read_document_tool",
        "write_spreadsheet_tool",
        "append_document_text_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    default_timeout_ms=settings.default_tool_timeout_ms * 2,  # Double timeout for parallel calls
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

# ============================================================================
# Agent Manifest: web_fetch_agent (Web Page Content Extraction — evolution F1)
# ============================================================================

BROWSER_AGENT_MANIFEST = AgentManifest(
    name="browser_agent",
    description=(
        "Agent for interactive web browsing: navigate pages, click elements, "
        "fill forms, extract structured content via accessibility tree."
    ),
    tools=[
        "browser_task_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.browser_default_timeout_ms,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


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
    default_timeout_ms=settings.default_tool_timeout_ms,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


DEVOPS_AGENT_MANIFEST = AgentManifest(
    name="devops_agent",
    description=(
        "Remote server management agent using Claude CLI over SSH. "
        "Autonomously inspects logs, diagnoses issues, checks system health, "
        "and manages Docker containers on remote servers."
    ),
    tools=[
        "claude_server_task_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=360000,  # 6 min — must be > DEVOPS_COMMAND_TIMEOUT (300s)
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

__all__ = [
    "CONTACT_AGENT_MANIFEST",
    "CONTEXT_AGENT_MANIFEST",
    "EMAIL_AGENT_MANIFEST",
    "EVENT_AGENT_MANIFEST",
    "FILE_AGENT_MANIFEST",
    "TASK_AGENT_MANIFEST",
    "WEATHER_AGENT_MANIFEST",
    "WIKIPEDIA_AGENT_MANIFEST",
    "QUERY_AGENT_MANIFEST",
    "PERPLEXITY_AGENT_MANIFEST",
    "PLACE_AGENT_MANIFEST",
    "ROUTE_AGENT_MANIFEST",
    "BRAVE_AGENT_MANIFEST",
    "WEB_SEARCH_AGENT_MANIFEST",
    "BROWSER_AGENT_MANIFEST",
    "WEB_FETCH_AGENT_MANIFEST",
    "DEVOPS_AGENT_MANIFEST",
]
