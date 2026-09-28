"""Agent manifest definitions (extracted from ``catalogue_loader``, 2026-08).

Pure declarative data: one ``AgentManifest`` per orchestrated agent. The
loader imports them and registers each; keeping the declarations here keeps
the loader an orchestration module (file-size ratchet doctrine).

NAMING: domain=entity(singular), agent_name=domain_agent (see the loader).
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.core.config import settings
from src.core.constants import DIAGNOSTICS_AGENT_NAME

from .catalogue import AgentManifest

# ============================================================================
# Agent Manifest: contact_agent (domain=contact, result_key=contacts)
# ============================================================================

CONTACT_AGENT_MANIFEST = AgentManifest(
    name="contact_agent",
    description="Agent specialised in contact operations (search, creation, update, deletion).",
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
        "Generic agent resolving contextual references. Handles conversational references such as "
        "'the first', 'the last', '2nd', etc. Supports batch operations through get_context_list "
        "for plural references. Works with every domain (contacts, emails, events)."
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
    description=(
        "Agent specialised in e-mail operations (search, read, send, reply, forward, delete)."
    ),
    tools=[
        "get_emails_tool",  # Unified tool (v2.0 - replaces search + details)
        "get_email_attachment_tool",  # One attachment, read (text or vision)
        "send_email_tool",
        "send_email_to_me_tool",  # To the user themselves: no draft (ADR-314)
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
        "Agent specialised in calendar operations. Lists the available calendars; searches, "
        "creates, updates and deletes events. Manages the agenda and appointments. Write "
        "operations (create, update, delete) require the user's confirmation through HITL."
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
        "Agent specialised in Google Drive operations. Searches, lists and reads files (documents, "
        "spreadsheets, presentations, PDFs, images), contents included."
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
        "Agent specialised in task operations. Lists, creates, updates, completes and deletes "
        "tasks; manages task lists. Write operations require the user's confirmation through HITL."
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
        "Agent specialised in weather information: current conditions, multi-day and hourly "
        "forecasts — temperature, humidity, precipitation, wind, etc. Served by the weather "
        "provider in use (Google Weather by default, OpenWeatherMap when configured)."
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
        "Agent specialised in encyclopaedic information: Wikipedia search, summaries, full "
        "articles, related articles. For general knowledge, biographies, history, etc."
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
        "Agent specialised in analysing data already in memory: filters, sorts, groups and finds "
        "patterns (such as duplicates) in what other agents retrieved. Works with the "
        "LocalQueryEngine for cross-domain queries."
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
        "Agent specialised in real-time web search. Uses Perplexity AI to look up current "
        "information on the internet, answer questions with source citations, and give up-to-date "
        "information on news and recent events."
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
        "Agent specialised in places and points of interest: restaurants, hotels, shops and "
        "services nearby. Place details: address, opening hours, reviews, prices. Current "
        "location: reverse geocoding to answer 'where am I?'. Uses the Google Places and Geocoding "
        "APIs."
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
        "Agent specialised in routes and directions: journeys between two points, travel time, "
        "distance. Several transport modes: car, walking, cycling, public transport. Options: "
        "avoid tolls, motorways, ferries. Distance matrix for multi-point optimisation. Uses the "
        "Google Routes API v2."
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
        "Agent specialised in web search through the Brave Search API: general web search and news "
        "search. Authenticates with an API key (not OAuth)."
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
        "Agent specialised in unified Triple Source web search: Perplexity AI (synthesis), Brave "
        "Search (URLs) and Wikipedia (encyclopaedia) in parallel. Fallback chain: it carries on "
        "when a source fails. Wikipedia is always available (no authentication)."
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
        "Agent specialised in fetching and extracting web page content: reads the full content of "
        "a URL, extracts the main article or the whole page, returns cleaned Markdown text. It "
        "does NOT search the web (web_search_agent does)."
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

DIAGNOSTICS_AGENT_MANIFEST = AgentManifest(
    name=DIAGNOSTICS_AGENT_NAME,
    description=(
        "Platform self-diagnostics agent (administrators only). Reads LIA's own "
        "telemetry: current health snapshot and firing alerts, curated platform "
        "metrics, bounded service logs, and the incident memory with stored "
        "diagnoses. Read-only — it never restarts or modifies anything "
        "(use devops_agent for actions on servers)."
    ),
    tools=[
        "platform_health_tool",
        "platform_metrics_tool",
        "platform_logs_tool",
        "platform_incidents_tool",
    ],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)

PYTHON_SANDBOX_AGENT_MANIFEST = AgentManifest(
    name="python_sandbox_agent",
    description=(
        "Ephemeral Python execution in an isolated sandbox (ADR-249). Runs a short "
        "script the assistant writes to compute what a language model computes "
        "badly: arithmetic over many rows, joins and deduplication on a key, "
        "durations across timezones, statistics. No network, no database, fresh "
        "container each run. ReAct mode only."
    ),
    tools=["run_python_tool"],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
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
    "DIAGNOSTICS_AGENT_MANIFEST",
    "PYTHON_SANDBOX_AGENT_MANIFEST",
]
