"""
Domain Taxonomy for Multi-Domain Agent Architecture.

This module provides a declarative configuration system for managing domains
in the multi-agent system. It enables dynamic loading of manifests and tools
based on detected domains, preventing prompt explosion and improving scalability.

Architecture Pattern: v3.1 LLM-based (Pure LLM Reasoning)
- QueryAnalyzerService uses LLM to analyze queries and detect domains
- Registry provides domain metadata (relationships, agent bindings)
- No keyword matching - LLM intelligence handles domain detection

Best Practices:
- Declarative domain configuration (add new domain = config entry only)
- Generic architecture (no domain-specific logic in core nodes)
- Scalable to 10+ domains without prompt size explosion

Usage Example:
    >>> from domains.agents.registry.domain_taxonomy import get_domain_config
    >>> contacts_config = get_domain_config("contacts")
    >>> print(contacts_config.display_name)  # "Google Contacts"
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.domains.agents.constants import MCP_DOMAIN_PREFIX

if TYPE_CHECKING:
    from src.domains.agents.registry.catalogue import ToolManifest


@dataclass(frozen=True)
class DomainConfig:
    """
    Configuration for a single domain in the multi-agent system.

    Attributes:
        name: Internal domain identifier (e.g., "contacts", "email")
        display_name: Human-readable domain name (e.g., "Google Contacts")
        description: Brief description of domain capabilities
        agent_names: List of agent identifiers in this domain (e.g., ["contact_agent"])
        result_key: Canonical key for step results in $steps references (e.g., "contacts", "weathers").
                    This is THE source of truth for result naming - used by executor, prompts, and tools.
        related_domains: Domains often used together (for smart expansion)
        is_routable: Whether this domain can be selected by router
        metadata: Additional domain-specific metadata

    Design Notes:
        - Frozen dataclass ensures immutability (thread-safe)
        - v3.1: Domain detection handled by QueryAnalyzerService LLM
        - Related domains enable smart expansion (e.g., contacts → email)
        - result_key is the SINGLE source of truth for naming step results
    """

    name: str
    display_name: str
    description: str
    agent_names: list[str]
    result_key: str  # Canonical key for $steps.STEP_ID.{result_key} references
    related_domains: list[str] = field(default_factory=list)
    is_routable: bool = True  # Can be selected by router (False for internal/technical domains)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate domain configuration."""
        if not self.name:
            raise ValueError("Domain name cannot be empty")
        if not self.agent_names:
            raise ValueError(f"Domain '{self.name}' must have at least one agent")
        if not self.result_key:
            raise ValueError(f"Domain '{self.name}' must have a result_key")


# Domain Registry: Declarative configuration for all domains
# To add a new domain: Add entry here + implement agent + register in AgentRegistry
DOMAIN_REGISTRY: dict[str, DomainConfig] = {
    "contact": DomainConfig(
        name="contact",
        display_name="Contacts",
        description=(
            "Manage people in user's address book: search contacts by name, email or phone, "
            "create, update or delete. NOT for sending emails (use email)."
        ),
        agent_names=["contact_agent"],
        result_key="contacts",  # $steps.step_N.contacts
        related_domains=[],  # Reverse lookup: email→contact, event→contact cover adjacency
        metadata={
            "provider": "google",
            "requires_oauth": True,
            "api_version": "v1",
        },
    ),
    # Context domain: Cross-domain utilities (always included)
    # NOT ROUTABLE: Technical/internal domain, always auto-loaded
    "context": DomainConfig(
        name="context",
        display_name="Context Management",
        description="Cross-domain utilities for managing conversation context, resolving references, and tracking state",
        agent_names=["context_agent"],
        result_key="contexts",  # Internal domain, rarely referenced in $steps
        related_domains=[],  # Context is standalone, works with all domains
        is_routable=False,  # Internal domain - not selectable by router
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "cross_domain": True,  # Special flag: always included in filtered catalogues
            "description_long": (
                "The context domain provides cross-domain utilities for managing conversation "
                "context, resolving contextual references (first/last/previous), and tracking "
                "active state across multiple domains. These tools are essential for multi-turn "
                "conversations and should be available regardless of detected domains."
            ),
        },
    ),
    # Email domain: Email management (multi-provider)
    "email": DomainConfig(
        name="email",
        display_name="Email",
        description=(
            "Read, search, send, reply and forward emails in user's inbox. "
            "Manage labels and folders. NOT for looking up contact info (use contact)."
        ),
        agent_names=["email_agent"],
        result_key="emails",  # $steps.step_N.emails
        related_domains=["contact"],  # Emails mention people, meetings, action items
        metadata={
            "provider": "google",
            "requires_oauth": True,
            "api_version": "v1",
            "requires_hitl": True,  # Sending emails requires HITL approval
        },
    ),
    # Event domain: Calendar events management (multi-provider)
    "event": DomainConfig(
        name="event",
        display_name="Calendar",
        description=(
            "Manage calendar: search, create, update, cancel meetings and appointments. "
            "Check agenda and schedule. NOT for to-do items (use task) or time-based alerts (use reminder)."
        ),
        agent_names=["event_agent"],
        result_key="events",  # $steps.step_N.events
        related_domains=["contact"],  # Events involve people and may generate tasks
        metadata={
            "provider": "google",
            "requires_oauth": True,
            "api_version": "v3",
            "requires_hitl": True,  # Creating/modifying events requires HITL approval
            "default_calendar": None,  # User-configured via preferences
        },
    ),
    # File domain: Cloud file management (Google Drive)
    "file": DomainConfig(
        name="file",
        display_name="Drive / Files",
        description=(
            "Search and browse files in cloud drive: documents, spreadsheets, "
            "PDFs, images by name, type or content."
        ),
        agent_names=["file_agent"],
        result_key="files",  # $steps.step_N.files
        related_domains=["contact"],  # Files shared via email, owned by contacts
        metadata={
            "provider": "google",
            "requires_oauth": True,
            "api_version": "v3",
            "requires_hitl": False,  # Reading files doesn't require HITL
        },
    ),
    # Task domain: Task management (Google Tasks)
    "task": DomainConfig(
        name="task",
        display_name="Tasks",
        description=(
            "Manage persistent to-do items: search, create, update, complete or delete "
            "tasks with due dates. Organize into task lists. "
            "NOT for calendar events (use event) or alerts (use reminder)."
        ),
        agent_names=["task_agent"],
        result_key="tasks",  # $steps.step_N.tasks
        related_domains=[],  # Reverse lookup: event→task covers adjacency
        metadata={
            "provider": "google",
            "requires_oauth": True,
            "api_version": "v1",
            "requires_hitl": True,  # Creating/completing tasks requires HITL approval
            "default_task_list": None,  # User-configured via preferences
        },
    ),
    # Weather domain: Weather information
    "weather": DomainConfig(
        name="weather",
        display_name="Weather",
        description=(
            "Get current weather, multi-day forecasts and hourly predictions for any location. "
            "Temperature, wind, rain, humidity and alerts."
        ),
        agent_names=["weather_agent"],
        result_key="weathers",  # $steps.step_N.weathers
        related_domains=[
            "event"
        ],  # Weather for events; place adjacency via reverse (place→weather)
        metadata={
            "provider": "openweathermap",
            "requires_oauth": False,
            "requires_api_key": True,
            "api_key_env": "OPENWEATHERMAP_API_KEY",
        },
    ),
    # Query domain: Cross-domain data analysis (INTELLIA LocalQueryEngine)
    # NOT ROUTABLE: Technical/internal domain for post-retrieval analysis
    "query": DomainConfig(
        name="query",
        display_name="Data Analysis",
        description="Analyze, filter, sort, and find patterns in data already retrieved by other agents. Cross-domain queries and duplicate detection.",
        agent_names=["query_agent"],
        result_key="querys",  # $steps.step_N.querys (domain + "s" pattern)
        related_domains=[],  # Query works with all domains
        is_routable=False,  # Internal domain - not selectable by router
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "cross_domain": True,  # Works with data from all domains
            "description_long": (
                "The query domain provides the LocalQueryEngine for analyzing data "
                "already present in the registry. It can filter, sort, group, and find "
                "patterns (like duplicates) across data from multiple domains."
            ),
        },
    ),
    # Reminder domain: Personal reminders with FCM push notifications
    "reminder": DomainConfig(
        name="reminder",
        display_name="Reminders",
        description=(
            "Set one-time push notification at a specific date and time. "
            "List or cancel pending reminders. "
            "NOT for persistent tasks (use task) or meetings (use event)."
        ),
        agent_names=["reminder_agent"],
        result_key="reminders",  # $steps.step_N.reminders
        related_domains=["contact"],  # Reminders tied to events, tasks, and people
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "requires_hitl": False,  # Reminders are one-shot, no HITL needed
            "notification_type": "fcm",
            "description_long": (
                "The reminder domain handles personal reminders that are sent as push notifications "
                "at a specific time. Unlike tasks (persistent todo items) or calendar events "
                "(scheduled meetings), reminders are one-shot notifications that remind the user "
                "about something at a precise moment. The reminder message is personalized "
                "using the user's personality and long-term memory."
            ),
        },
    ),
    # Place domain: Location and place search (Google Places)
    "place": DomainConfig(
        name="place",
        display_name="Google Places",
        description=(
            "Find nearby businesses, restaurants, shops, healthcare, entertainment, services "
            "and points of interest by category or location. Ratings, hours, addresses. "
            "Also provides user geolocation (where am I). NOT for directions (use route)."
        ),
        agent_names=["place_agent"],
        result_key="places",  # $steps.step_N.places
        related_domains=[
            "weather",
            "event",
            "contact",
        ],  # Places often combined with weather or events
        metadata={
            "provider": "google",
            "requires_oauth": False,
            "requires_api_key": True,
            "api_key_env": "GOOGLE_API_KEY",
            "api_version": "v1",
        },
    ),
    # Route domain: Directions and travel time (Google Routes)
    "route": DomainConfig(
        name="route",
        display_name="Google Routes",
        description=(
            "Calculate driving, walking or transit directions between two locations. "
            "Distance, travel time, step-by-step itinerary. Compare via distance matrix. "
            "NOT for finding places (use place)."
        ),
        agent_names=["route_agent"],
        result_key="routes",  # $steps.step_N.routes
        related_domains=[
            "place",
            "weather",
            "event",
            "contact",
        ],  # Routes often involves places, events, or contact addresses
        metadata={
            "provider": "google",
            "requires_oauth": False,
            "requires_api_key": True,
            "api_key_env": "GOOGLE_API_KEY",
            "api_version": "v2",
        },
    ),
    # Wikipedia domain: Knowledge lookup
    "wikipedia": DomainConfig(
        name="wikipedia",
        display_name="Wikipedia",
        description=(
            "Encyclopedic knowledge from Wikipedia: search articles, read summaries or full content. "
            "Best for established facts, biographies, science. NOT for current news (use web_search)."
        ),
        agent_names=["wikipedia_agent"],
        result_key="wikipedias",  # $steps.step_N.wikipedias (domain + "s" pattern)
        related_domains=[],  # Wikipedia is standalone
        metadata={
            "provider": "wikipedia",
            "requires_oauth": False,
            "requires_api_key": False,  # Wikipedia API is free
            "default_language": "fr",
        },
    ),
    # Perplexity domain: Real-time web search with AI
    "perplexity": DomainConfig(
        name="perplexity",
        display_name="Web Search",
        description=(
            "AI-powered web search with synthesized answers and source citations. "
            "Deep explanations with real-time web context."
        ),
        agent_names=["perplexity_agent"],
        result_key="perplexitys",  # $steps.step_N.perplexitys (domain + "s" pattern)
        related_domains=[],  # Web search complements Wikipedia
        metadata={
            "provider": "perplexity",
            "requires_oauth": False,
            "requires_api_key": True,
            "api_key_env": "PERPLEXITY_API_KEY",
            "model": "sonar",
        },
    ),
    # Brave domain: Web and news search via Brave Search API
    "brave": DomainConfig(
        name="brave",
        display_name="Brave Search",
        description=(
            "Web and news search via Brave Search: web pages, articles "
            "and recent news with direct URLs and snippets."
        ),
        agent_names=["brave_agent"],
        result_key="braves",  # $steps.step_N.braves (domain + "s" pattern)
        related_domains=[],  # Web search related domains
        metadata={
            "provider": "brave",
            "requires_oauth": False,
            "requires_api_key": True,
            "api_key_env": "BRAVE_API_KEY",
        },
    ),
    # Web Search domain: Unified meta-search (Perplexity + Brave + Wikipedia)
    "web_search": DomainConfig(
        name="web_search",
        display_name="Web Search",
        description=(
            "Comprehensive web search combining multiple sources (AI synthesis, web results, "
            "encyclopedia). Preferred for general knowledge, current events, news or research "
            "beyond personal data."
        ),
        agent_names=["web_search_agent"],
        result_key="web_searchs",  # $steps.step_N.web_searchs (domain + "s" pattern)
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "internal",
            "is_meta_domain": True,
            "aggregates": ["perplexity", "brave", "wikipedia"],
            "requires_oauth": False,
            "description_long": (
                "Unified web search that orchestrates Perplexity (AI synthesis), "
                "Brave Search (URLs), and Wikipedia (encyclopedia) in parallel. "
                "Implements fallback chain - if one source fails, continues with others. "
                "Wikipedia is always available (no auth required)."
            ),
        },
    ),
    # Web Fetch domain: Web page content extraction (evolution F1)
    "web_fetch": DomainConfig(
        name="web_fetch",
        display_name="Web Fetch",
        description=(
            "Read full content of a web page from its URL. Extracts clean text. "
            "ONLY when user provides a specific URL or link. NOT for web search (use web_search)."
        ),
        agent_names=["web_fetch_agent"],
        result_key="web_fetchs",  # $steps.step_N.web_fetchs (domain + "s" pattern)
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "requires_api_key": False,
            "description_long": (
                "The web_fetch domain extracts and reads the full content of a web page "
                "from a URL. It converts HTML to clean Markdown text with SSRF protection. "
                "Use this when the user provides a specific URL to read, not for searching "
                "the web (use web_search for that)."
            ),
        },
    ),
    # Sub-Agent domain: Ephemeral sub-agent delegation (cross-cutting)
    # NOT ROUTABLE: Internal capability, force-injected via include_sub_agent_tools
    "sub_agent": DomainConfig(
        name="sub_agent",
        display_name="Sub-Agent Delegation",
        description="Delegate complex tasks to ephemeral specialized sub-agents",
        agent_names=["sub_agent_agent"],
        result_key="sub_agents",
        related_domains=[],
        is_routable=False,  # Internal/transversal — not selectable by router
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "cross_domain": True,
        },
    ),
    # MCP domain: External tools from MCP servers (evolution F2)
    "mcp": DomainConfig(
        name="mcp",
        display_name="MCP Tools",
        description=(
            "External tools from MCP (Model Context Protocol) servers: "
            "file systems, databases, APIs, code execution, custom tools"
        ),
        agent_names=["mcp_agent"],  # Virtual agent, not compiled
        result_key="mcps",  # $steps.step_N.mcps
        related_domains=[],
        is_routable=True,  # Router CAN detect MCP relevance
        metadata={
            "provider": "mcp",
            "requires_oauth": False,
            "requires_api_key": False,
            "dynamic": True,  # Tools discovered at runtime
            "description_long": (
                "The MCP domain groups all tools discovered from external MCP "
                "(Model Context Protocol) servers. These tools are dynamically "
                "registered at startup and can include file system access, database "
                "queries, API integrations, and custom functionality."
            ),
        },
    ),
    # Browser domain: Interactive web browsing (evolution F7)
    "browser": DomainConfig(
        name="browser",
        display_name="Browser",
        description=(
            "Interactive web browsing: navigate pages, click elements, fill forms, "
            "extract structured content. Use for tasks requiring direct web interaction "
            "beyond simple page fetching."
        ),
        agent_names=["browser_agent"],
        result_key="browsers",  # $steps.step_N.browsers (domain + "s" pattern)
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "requires_api_key": False,
        },
    ),
    # AI Image Generation (evolution)
    "image_generation": DomainConfig(
        name="image_generation",
        display_name="Image Generation",
        description=(
            "Generate images from text descriptions using AI. "
            "Create illustrations, logos, art, designs from natural language prompts. "
            "NOT for editing existing images or photos."
        ),
        agent_names=["image_generation_agent"],
        result_key="image_generations",
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "openai",
            "requires_oauth": False,
            "requires_api_key": False,  # Uses global OpenAI key from LLM Config
        },
    ),
    # Smart Home domains
    "hue": DomainConfig(
        name="hue",
        display_name="Philips Hue",
        description=(
            "Control Philips Hue smart lights: list lights, turn on/off, adjust brightness "
            "and color, control rooms, list and activate scenes. "
            "Covers all smart lighting control operations."
        ),
        agent_names=["hue_agent"],
        result_key="hues",
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "philips_hue",
            "requires_oauth": False,
            "requires_api_key": False,
        },
    ),
    # Health Metrics domain (v1.17.2) — steps, heart_rate, and any future
    # kind registered in HEALTH_KINDS. Per-user opt-in gated at tool entry.
    "health": DomainConfig(
        name="health",
        display_name="Health Metrics",
        description=(
            "Answer factual questions about the user's health data (steps, "
            "heart rate, etc.) ingested from their iPhone. Summaries, per-day "
            "breakdowns, comparison to a rolling 28-day baseline, and "
            "detection of notable recent variations. Never provides medical "
            "diagnosis or advice — reports figures only."
        ),
        agent_names=["health_agent"],
        result_key="health_signals",
        related_domains=[],
        is_routable=True,
        metadata={
            "provider": "internal",
            "requires_oauth": False,
            "requires_api_key": False,
            "per_user_opt_in": True,
        },
    ),
    "devops": DomainConfig(
        name="devops",
        display_name="DevOps (Claude CLI)",
        description=(
            "Writing and executing scripts and programs with Claude CLI. "
            "Server infrastructure and DevOps administration via SSH and CLI. "
            "Use for: Docker container logs, docker-compose status, server health checks, "
            "service restart, disk/memory/CPU monitoring, deployment diagnostics, "
            "production error analysis, infrastructure troubleshooting. "
            "NOT for calendar events, emails, contacts, weather, or any user-facing data."
        ),
        agent_names=["devops_agent"],
        result_key="server_results",
        related_domains=[],
        is_routable=True,
        metadata={
            "requires_admin": True,
            "uses_ssh": True,
        },
    ),
}


def slugify_mcp_server_name(name: str) -> str:
    """Slugify an MCP server name into a domain identifier.

    Produces ``mcp_<slug>`` where slug is lowercase alphanumeric with underscores,
    collapsed, stripped, and truncated to 40 chars max.

    Args:
        name: Raw MCP server name (e.g., "HuggingFace Hub").

    Returns:
        Slugified domain name (e.g., "mcp_huggingface_hub").
    """
    slug = re.sub(r"[^a-z0-9]", "_", name.lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    slug = slug[:40]
    if not slug:
        return "mcp_unnamed"
    return f"{MCP_DOMAIN_PREFIX}{slug}"


def deduplicate_mcp_slugs(server_names: list[str]) -> dict[str, str]:
    """Build a mapping of server names to unique domain slugs.

    When two servers produce the same slug, appends ``_2``, ``_3``, etc.

    Args:
        server_names: List of raw MCP server names.

    Returns:
        Dict mapping original server_name → unique domain slug.
    """
    result: dict[str, str] = {}
    slug_counts: dict[str, int] = {}
    for name in server_names:
        slug = slugify_mcp_server_name(name)
        count = slug_counts.get(slug, 0) + 1
        slug_counts[slug] = count
        if count > 1:
            result[name] = f"{slug}_{count}"
        else:
            result[name] = slug
    return result


def is_mcp_domain(domain_name: str) -> bool:
    """Check whether a domain name is a per-server MCP domain.

    The base ``"mcp"`` domain (admin/fallback) returns False.

    Args:
        domain_name: Domain identifier to check.

    Returns:
        True if the domain is a per-server MCP domain (``mcp_*``).
    """
    return domain_name.startswith(MCP_DOMAIN_PREFIX)


def filter_admin_mcp_disabled_manifests(
    manifests: list["ToolManifest"],
    admin_disabled: set[str] | None = None,
) -> list["ToolManifest"]:
    """Filter out tool manifests belonging to admin MCP servers disabled by the user.

    Extracts the server key from each manifest's agent field (e.g. ``mcp_excalidraw_agent``
    → ``excalidraw``) and removes it if the key is in ``admin_disabled``.

    If ``admin_disabled`` is None, reads from ``admin_mcp_disabled_ctx`` ContextVar.

    Args:
        manifests: List of ToolManifest objects.
        admin_disabled: Set of disabled server keys. If None, reads from ContextVar.

    Returns:
        Filtered list with disabled admin MCP tool manifests removed.
    """
    if admin_disabled is None:
        from src.core.context import admin_mcp_disabled_ctx

        admin_disabled = admin_mcp_disabled_ctx.get()

    if not admin_disabled:
        return manifests

    def _is_disabled(manifest: "ToolManifest") -> bool:
        # Extract domain from agent field: "mcp_excalidraw_agent" → "mcp_excalidraw"
        agent = getattr(manifest, "agent", None) or ""
        domain = agent.removesuffix("_agent") if agent else ""
        if not domain:
            # Fallback: extract from tool name "mcp_excalidraw_create_view" → "mcp_excalidraw"
            name = getattr(manifest, "name", "") or ""
            if name.startswith(MCP_DOMAIN_PREFIX):
                # Split after "mcp_" and take server key (first segment)
                rest = name[len(MCP_DOMAIN_PREFIX) :]
                parts = rest.split("_")
                # Server key can be multi-segment (e.g. "google_flights")
                # Use agent field preferentially; fallback heuristic: longest prefix match
                domain = MCP_DOMAIN_PREFIX + parts[0] if parts else ""
        if domain.startswith(MCP_DOMAIN_PREFIX):
            server_key = domain[len(MCP_DOMAIN_PREFIX) :]
            return server_key in admin_disabled
        return False

    return [m for m in manifests if not _is_disabled(m)]


def get_domain_config(domain_name: str) -> DomainConfig | None:
    """
    Retrieve domain configuration by name.

    For dynamic per-server MCP domains (``mcp_*``), synthesizes a DomainConfig
    on the fly with the same result_key as the base ``"mcp"`` domain.

    Args:
        domain_name: Domain identifier (e.g., "contacts", "mcp_huggingface_hub")

    Returns:
        DomainConfig if found (or synthesized for mcp_*), None otherwise

    Example:
        >>> config = get_domain_config("contacts")
        >>> if config:
        ...     print(config.display_name)  # "Google Contacts"
    """
    config = DOMAIN_REGISTRY.get(domain_name)
    if config is not None:
        return config
    # Fallback: synthesize DomainConfig for dynamic per-server MCP domains
    if is_mcp_domain(domain_name):
        return DomainConfig(
            name=domain_name,
            display_name=f"MCP: {domain_name.removeprefix(MCP_DOMAIN_PREFIX)}",
            description="Dynamic MCP server domain",
            agent_names=[f"{domain_name}_agent"],
            result_key="mcps",
            related_domains=[],
            is_routable=True,
            metadata={"provider": "mcp", "dynamic": True},
        )
    return None


def get_all_domains() -> list[str]:
    """
    Get list of all registered domain names.

    Returns:
        List of domain identifiers (e.g., ["contacts"])

    Example:
        >>> domains = get_all_domains()
        >>> print(domains)  # ["contacts"]
    """
    return list(DOMAIN_REGISTRY.keys())


def get_routable_domains() -> list[str]:
    """
    Get list of domains that can be selected by the router.

    Excludes internal/technical domains (is_routable=False) like:
    - context: Cross-domain utilities (always auto-loaded)
    - query: LocalQueryEngine for post-retrieval analysis

    Returns:
        List of routable domain identifiers (functional domains only)

    Example:
        >>> domains = get_routable_domains()
        >>> print(domains)  # ["contacts", "emails", "calendar", "weather", ...]
        >>> "query" in domains  # False
        >>> "context" in domains  # False
    """
    return [name for name, config in DOMAIN_REGISTRY.items() if config.is_routable]


def get_result_key(domain_name: str) -> str | None:
    """
    Get the canonical result_key for a domain.

    This is THE source of truth for how results are keyed in $steps references.
    For dynamic per-server MCP domains (``mcp_*``), always returns ``"mcps"``.

    Args:
        domain_name: Domain identifier (e.g., "weather", "mcp_huggingface_hub")

    Returns:
        Result key (e.g., "weathers") or None if domain not found

    Example:
        >>> get_result_key("weather")
        "weathers"
        >>> get_result_key("mcp_huggingface_hub")
        "mcps"
    """
    config = DOMAIN_REGISTRY.get(domain_name)
    if config is not None:
        return config.result_key
    # Fallback for dynamic per-server MCP domains
    if is_mcp_domain(domain_name):
        return "mcps"
    # Unknown domain → log normalization failure for dashboard 15
    try:
        from src.infrastructure.observability.metrics_agents import (
            domain_normalization_errors_total,
        )

        domain_normalization_errors_total.labels(
            domain=domain_name[:40], error_type="unknown_result_key"
        ).inc()
    except Exception:
        pass
    return None


def get_result_key_for_tool(tool_name: str) -> str | None:
    """
    Get the canonical result_key for a tool based on its name.

    This is THE source of truth for mapping tool names to result keys.
    Used by semantic_validator to validate $steps references.

    Naming convention v3.2:
    - Tools follow patterns: {action}_{domain}_tool, {action}_{domain}s_tool
    - Examples: get_contacts_tool, send_email_tool, get_events_tool
    - Returns the result_key from DOMAIN_REGISTRY for the detected domain

    Args:
        tool_name: Tool name (e.g., "get_contacts_tool", "send_email_tool")

    Returns:
        Result key (e.g., "contacts", "emails") or None if domain not found

    Example:
        >>> get_result_key_for_tool("get_contacts_tool")
        "contacts"
        >>> get_result_key_for_tool("get_weather_tool")
        "weathers"
        >>> get_result_key_for_tool("get_events_tool")
        "events"
    """
    if not tool_name:
        return None

    tool_lower = tool_name.lower()

    # Try to match domain from DOMAIN_REGISTRY
    # Check each domain name against the tool name
    # Patterns to match:
    # - {action}_{domain}_tool (e.g., get_weather_tool, send_email_tool)
    # - {action}_{domain}s_tool (e.g., get_contacts_tool, get_events_tool)
    # - {domain}_{action}_tool (e.g., perplexity_search_tool, wikipedia_search_tool)
    for domain_name, config in DOMAIN_REGISTRY.items():
        # Pattern 1: _{domain}_ (action_domain_tool)
        if f"_{domain_name}_" in tool_lower:
            return config.result_key
        # Pattern 2: _{domain}s_ (action_domains_tool - plural)
        if f"_{domain_name}s_" in tool_lower:
            return config.result_key
        # Pattern 3: {domain}_ at start (domain_action_tool)
        if tool_lower.startswith(f"{domain_name}_"):
            return config.result_key
        # Pattern 4: {domain}s_ at start (domains_action_tool - plural)
        if tool_lower.startswith(f"{domain_name}s_"):
            return config.result_key

    # Fallback: check if result_key itself appears in tool name
    # This handles edge cases where tool name uses plural directly
    for _domain_name, config in DOMAIN_REGISTRY.items():
        if f"_{config.result_key}_" in tool_lower:
            return config.result_key

    return None


def export_context_labels_for_router() -> str:
    """
    Export valid context_label values for router prompt schema.

    Dynamically generates the context_label enum from domain registry.

    Returns:
        Pipe-separated list of valid context labels.

    Example Output:
        "general|contact|email|calendar|drive|tasks|weather|info|places"

    Design Notes:
        - 'general' and 'info' are always included (not domain-specific)
        - Domain names are converted to context labels
        - Only routable domains are included
    """
    # Static labels that are always valid
    static_labels = ["general"]

    # Dynamic labels from routable domains
    domain_labels = get_routable_domains()

    # 'info' covers wikipedia, perplexity (knowledge domains)
    # This is a semantic grouping for conversational context
    all_labels = static_labels + domain_labels + ["info"]

    return "|".join(all_labels)


def validate_domain_registry() -> list[str]:
    """
    Validate domain registry configuration.

    Returns:
        List of validation errors (empty if valid)

    Checks:
        - All domain names are unique (implicit via dict keys)
        - All agent_names are unique across domains
        - Related domains exist in registry
        - No circular dependencies in related_domains

    Example:
        >>> errors = validate_domain_registry()
        >>> if errors:
        ...     for error in errors:
        ...         print(f"ERROR: {error}")
    """
    errors: list[str] = []

    # Check agent name uniqueness
    all_agent_names: list[str] = []
    for config in DOMAIN_REGISTRY.values():
        all_agent_names.extend(config.agent_names)

    duplicates = [name for name in all_agent_names if all_agent_names.count(name) > 1]
    if duplicates:
        errors.append(f"Duplicate agent names found: {set(duplicates)}")

    # Check related domains exist
    for domain_name, config in DOMAIN_REGISTRY.items():
        for related in config.related_domains:
            if related not in DOMAIN_REGISTRY:
                errors.append(
                    f"Domain '{domain_name}' references non-existent related domain '{related}'"
                )

    # Check for circular dependencies (basic check)
    for domain_name, config in DOMAIN_REGISTRY.items():
        for related in config.related_domains:
            related_config = DOMAIN_REGISTRY.get(related)
            if related_config and domain_name in related_config.related_domains:
                errors.append(f"Circular dependency detected: '{domain_name}' <-> '{related}'")

    return errors


# Validate registry on module import


def auto_generate_server_description(
    tool_descriptions: list[str | None],
    server_name: str,
    tool_names: list[str] | None = None,
) -> str:
    """Auto-generate a domain description from MCP tool descriptions.

    Builds a structured description optimized for LLM domain selection:
    - Starts with server identity prefix
    - Lists key capabilities extracted from first sentence of each tool description
    - Stays under MCP_DESCRIPTION_MAX_TOTAL_LENGTH chars for token efficiency

    Shared between admin MCP (registration.py) and user MCP (service.py).

    Args:
        tool_descriptions: Raw descriptions from discovered MCP tools.
        server_name: Fallback server name if no descriptions are available.
        tool_names: Optional tool names for richer context when descriptions
            are unavailable.

    Returns:
        Structured description string for LLM routing.
    """
    from src.core.constants import (
        MCP_DESCRIPTION_MAX_SENTENCE_LENGTH,
        MCP_DESCRIPTION_MAX_TOOLS,
        MCP_DESCRIPTION_MAX_TOTAL_LENGTH,
    )

    descs = [d.strip() for d in tool_descriptions if d and d.strip()]
    if not descs:
        if tool_names:
            names = ", ".join(tool_names[:MCP_DESCRIPTION_MAX_TOOLS])
            return f"MCP server {server_name}: {names}"
        return f"MCP server {server_name}"

    # Take first sentence (up to first period) of each description
    short_descs: list[str] = []
    for d in descs[:MCP_DESCRIPTION_MAX_TOOLS]:
        sentence = d.split(".")[0].strip()
        short_descs.append(sentence[:MCP_DESCRIPTION_MAX_SENTENCE_LENGTH])

    capabilities = "; ".join(short_descs)

    # Cap total length, truncate at last complete capability boundary
    result = f"MCP {server_name}: {capabilities}"
    if len(result) > MCP_DESCRIPTION_MAX_TOTAL_LENGTH:
        safe_cut = MCP_DESCRIPTION_MAX_TOTAL_LENGTH - 3  # room for "..."
        cut = result[:safe_cut].rfind("; ")
        result = (result[:cut] + "...") if cut > 0 else result[:safe_cut] + "..."
    return result


def collect_all_mcp_domains(
    admin_domains: dict[str, str],
    admin_disabled: set[str] | None,
    user_ctx: Any | None,
) -> list[dict[str, str]]:
    """Unified collection of all MCP per-server domains for query routing.

    Merges admin MCP (from startup registration) and user MCP (from per-request
    ContextVar) into a single list, filtering out admin servers disabled by the user.

    DRY: Single code path for both admin and user MCP domain injection into
    the query analyzer prompt. Replaces separate admin/user injection blocks.

    Args:
        admin_domains: slug → description from get_admin_mcp_domains().
        admin_disabled: Server keys disabled by user (from admin_mcp_disabled_ctx).
            None means no filtering.
        user_ctx: Per-request UserMCPToolsContext (may be None).

    Returns:
        List of {"name": domain_slug, "description": desc} dicts.
    """
    result: list[dict[str, str]] = []
    disabled = admin_disabled or set()

    # 1. Admin MCP domains (filtered by user preference)
    for slug, desc in admin_domains.items():
        # Extract server key from slug: "mcp_google_flights" → "google_flights"
        server_key = slug.removeprefix(MCP_DOMAIN_PREFIX)
        if server_key not in disabled:
            result.append({"name": slug, "description": desc})

    # 2. User MCP domains (from per-request ContextVar)
    if (
        user_ctx
        and getattr(user_ctx, "tool_manifests", None)
        and getattr(user_ctx, "server_domains", None)
    ):
        for srv_name, slug in user_ctx.server_domains.items():
            desc = user_ctx.server_descriptions.get(srv_name)
            if not desc:
                # Auto-generate from discovered tool descriptions
                server_tool_descs = [
                    m.description[:80] if m.description else m.name
                    for m in user_ctx.tool_manifests
                    if m.semantic_keywords and srv_name in m.semantic_keywords
                ]
                desc = auto_generate_server_description(server_tool_descs, srv_name)
            result.append({"name": slug, "description": desc})

    return result


_validation_errors = validate_domain_registry()
if _validation_errors:
    raise ValueError("Domain registry validation failed:\n" + "\n".join(_validation_errors))
