"""
Type-to-domain mapping utilities.

Centralizes registry type to domain name mapping used throughout
response_node, SSE handlers, context_resolution_service, adaptive_replanner,
html_renderer, text_summary, and formatters.

This module is the SINGLE SOURCE OF TRUTH for:
- Type name to domain/items_key mapping (TYPE_TO_DOMAIN_MAP)
- All known result keys set (ALL_RESULT_KEYS)
- Domains that skip intelligent filtering (SKIP_FILTER_RESULT_KEYS)
- Domains that skip knowledge enrichment (SKIP_ENRICHMENT_DOMAINS)
- Domain name extraction utilities

All domain-related type mappings MUST use this module to avoid duplication.
When adding a new domain, add it to TYPE_TO_DOMAIN_MAP and update the
derived sets below — all consumers will pick it up automatically.
"""

# Type -> Domain mapping (used by response_node, SSE, formatters, context resolution)
# Format: type_name -> (domain_name, items_key)
# domain_name: The canonical domain identifier (singular: contact, email, event, etc.)
# items_key: The result key = domain + "s" (contacts, emails, events, weathers, etc.)
# Convention v3.2: items_key always follows the domain+"s" pattern
TYPE_TO_DOMAIN_MAP: dict[str, tuple[str, str]] = {
    # Google Workspace domain types
    "CONTACT": ("contact", "contacts"),
    "EMAIL": ("email", "emails"),
    "EVENT": ("event", "events"),
    "CALENDAR": ("calendar", "calendars"),  # Calendar list items (list_calendars_tool)
    "TASK": ("task", "tasks"),
    "FILE": ("file", "files"),
    # External API domain types
    "PLACE": ("place", "places"),
    "LOCATION": ("location", "locations"),  # GPS position (get_current_location_tool)
    "ROUTE": ("route", "routes"),  # Google Routes directions
    "WEATHER": ("weather", "weathers"),  # domain + "s" pattern
    "WIKIPEDIA_ARTICLE": ("wikipedia", "wikipedias"),  # domain + "s" pattern
    "SEARCH_RESULT": ("perplexity", "perplexitys"),  # domain + "s" pattern
    "WEB_SEARCH": ("web_search", "web_searchs"),  # Unified triple source search
    # Internal domain types (no OAuth)
    "REMINDER": ("reminder", "reminders"),  # User reminders (internal)
    "WEB_PAGE": ("web_fetch", "web_fetchs"),  # Fetched web page content (evolution F1)
    "MCP_RESULT": ("mcp", "mcps"),  # MCP tool results (evolution F2.3)
    "MCP_APP": ("mcp_app", "mcp_apps"),  # MCP Apps interactive widgets (evolution F2.5)
    "BROWSER_PAGE": ("browser", "browsers"),  # Browser page snapshot (evolution F7)
}

# ============================================================================
# DERIVED SETS — auto-computed from TYPE_TO_DOMAIN_MAP
# ============================================================================
# All known result keys (items_key / pluriel form)
# Used by adaptive_replanner to detect non-empty results
ALL_RESULT_KEYS: frozenset[str] = frozenset(
    items_key for _, items_key in TYPE_TO_DOMAIN_MAP.values()
)

# Domains where intelligent filtering should be SKIPPED
# (LLM filtering would incorrectly empty relevant results)
# - Search engines: results are always relevant (user explicitly asked for search)
# - Weather: temporal references ("vendredi") shouldn't empty results
# - MCP: tool provides its own data, filtering is meaningless
# Uses items_key (pluriel) to match result_domains from _detect_result_domains_from_registry
SKIP_FILTER_RESULT_KEYS: frozenset[str] = frozenset(
    {
        "weathers",  # temporal references shouldn't empty results
        "wikipedias",  # encyclopedia results are always relevant
        "perplexitys",  # search results are always relevant
        "braves",  # search results are always relevant (no RegistryItemType yet — defensive)
        "web_searchs",  # search results are always relevant
        "web_fetchs",  # fetched page content is always relevant
        "querys",  # query agent results are always relevant (no RegistryItemType yet — defensive)
        "mcps",  # MCP tools provide their own data
        "mcp_apps",  # MCP interactive widgets are always relevant
        "browsers",  # browser page content is always relevant (F7)
    }
)

# Primary domains (singular) that skip Brave knowledge enrichment
# (already have their own content source, enrichment would be redundant)
SKIP_ENRICHMENT_DOMAINS: frozenset[str] = frozenset(
    {
        "web_search",  # already includes Brave
        "web_fetch",  # user explicitly fetched a URL, content is self-contained
    }
)


def get_domain_from_type(type_name: str) -> tuple[str, str]:
    """
    Get (domain_name, items_key) from registry type.

    Args:
        type_name: Registry type name (e.g., "CONTACT", "EMAIL").

    Returns:
        Tuple of (domain_name, items_key).

    Example:
        >>> get_domain_from_type("EMAIL")
        ("emails", "emails")
        >>> get_domain_from_type("EVENT")
        ("calendar", "events")
    """
    domain_info = TYPE_TO_DOMAIN_MAP.get(type_name.upper())
    if domain_info:
        return domain_info
    # Fallback for unknown types
    domain_name = type_name.lower()
    return (domain_name, f"{domain_name}s")


def get_domain_name_from_type(type_name: str) -> str | None:
    """
    Get domain name (singulier) from registry type.

    Returns the conceptual domain name (singular form).
    For the technical result key (plural), use get_result_key_from_type().

    Args:
        type_name: Registry type name (e.g., "CONTACT", "EMAIL").

    Returns:
        Domain name string (singulier) or None if not found.

    Example:
        >>> get_domain_name_from_type("EMAIL")
        "email"
        >>> get_domain_name_from_type("EVENT")
        "event"
        >>> get_domain_name_from_type("CONTACT")
        "contact"
        >>> get_domain_name_from_type("UNKNOWN")
        None
    """
    domain_info = TYPE_TO_DOMAIN_MAP.get(type_name.upper())
    if domain_info:
        return domain_info[0]
    return None


def get_result_key_from_type(type_name: str) -> str | None:
    """
    Get result key (pluriel) from registry type.

    Returns the technical key used for CONTEXT_DOMAIN_* constants,
    HtmlRenderer components, and structured result data.

    Args:
        type_name: Registry type name (e.g., "CONTACT", "EMAIL").

    Returns:
        Result key string (pluriel) or None if not found.

    Example:
        >>> get_result_key_from_type("EMAIL")
        "emails"
        >>> get_result_key_from_type("EVENT")
        "events"
        >>> get_result_key_from_type("CONTACT")
        "contacts"
        >>> get_result_key_from_type("UNKNOWN")
        None
    """
    domain_info = TYPE_TO_DOMAIN_MAP.get(type_name.upper())
    if domain_info:
        return domain_info[1]
    return None


def get_all_domain_names() -> list[str]:
    """
    Get all registered domain names (singulier).

    Returns:
        List of unique domain names (singulier form).

    Example:
        >>> "contact" in get_all_domain_names()
        True
        >>> "email" in get_all_domain_names()
        True
    """
    return list({info[0] for info in TYPE_TO_DOMAIN_MAP.values()})


def get_domain_from_result_key(result_key: str) -> str | None:
    """
    Get domain name (singulier) from result_key (pluriel).

    This is the reverse lookup of the domain→result_key mapping.
    Used to identify domain from FOR_EACH field paths like "emails", "contacts".

    Args:
        result_key: Result key (e.g., "emails", "contacts", "events")

    Returns:
        Domain name (singulier) or None if not found

    Example:
        >>> get_domain_from_result_key("emails")
        "email"
        >>> get_domain_from_result_key("contacts")
        "contact"
        >>> get_domain_from_result_key("events")
        "event"
    """
    result_key_lower = result_key.lower()

    for domain_name, items_key in TYPE_TO_DOMAIN_MAP.values():
        if items_key.lower() == result_key_lower:
            return domain_name

    return None


# Items key → (RegistryItemType, unique_key_field) mapping
# Used for registry filtering after FOR_EACH HITL and entity resolution
# unique_key_field: The field in item payload used to generate registry ID
# via generate_registry_id(type, item.get(unique_key_field))
# Note: Import RegistryItemType only when needed (lazy import to avoid circular deps)
#
# ⚠ Domains with COMPOSITE registry IDs (locations, weathers, routes) use
# multi-field IDs (e.g., f"{lat}_{lon}", f"current_{name}_{date}") that cannot
# be reconstructed from a single payload field. Their unique_key_field is a
# best-effort approximation. FOR_EACH HITL filtering won't match for these
# domains — acceptable since FOR_EACH is only used for contacts/emails/events.
ITEMS_KEY_TO_REGISTRY_CONFIG: dict[str, tuple[str, str]] = {
    # items_key: (registry_type_name, unique_key_field)
    # --- Simple ID domains (unique_key_field matches payload → registry ID) ---
    "contacts": ("CONTACT", "resourceName"),
    "emails": ("EMAIL", "id"),
    "events": ("EVENT", "id"),
    "calendars": ("CALENDAR", "id"),
    "tasks": ("TASK", "id"),
    "files": ("FILE", "id"),
    "places": ("PLACE", "place_id"),
    "reminders": ("REMINDER", "id"),
    # --- Composite ID domains (FOR_EACH filtering NOT supported) ---
    # ROUTE ID: f"{origin}_{destination}_{mode}_{timestamp}" — no single payload field
    "routes": ("ROUTE", "id"),
    # LOCATION ID: f"{latitude}_{longitude}" — needs both lat+lon
    "locations": ("LOCATION", "latitude"),
    # WEATHER ID: f"current_{name}_{date}" — composite name+date
    "weathers": ("WEATHER", "name"),
}


def get_registry_config_for_items_key(items_key: str) -> tuple[str, str] | None:
    """
    Get registry configuration for an items_key (e.g., "emails", "contacts").

    Returns tuple of (registry_type_name, unique_key_field) for generating
    deterministic registry IDs from item payloads.

    Args:
        items_key: The items key (e.g., "emails", "contacts", "events")

    Returns:
        Tuple of (registry_type_name, unique_key_field) or None if not found

    Example:
        >>> get_registry_config_for_items_key("emails")
        ("EMAIL", "id")
        >>> get_registry_config_for_items_key("contacts")
        ("CONTACT", "resourceName")
    """
    return ITEMS_KEY_TO_REGISTRY_CONFIG.get(items_key.lower())


# Tool name substring → domain mapping
# Used for detecting domain from tool_name (e.g., "search_contacts_tool" → "contacts")
# IMPORTANT: Values MUST match CONTEXT_DOMAIN_* constants in constants.py
# Convention v3.2: domain+"s" pattern for all result_key/context_domain values
TOOL_PATTERN_TO_DOMAIN_MAP: dict[str, str] = {
    "email": "emails",  # CONTEXT_DOMAIN_EMAILS
    "contact": "contacts",  # CONTEXT_DOMAIN_CONTACTS
    "list_calendars": "calendars",  # CONTEXT_DOMAIN_CALENDARS (must precede "calendar")
    "calendar": "events",  # CONTEXT_DOMAIN_EVENTS (calendar event tools)
    "event": "events",  # CONTEXT_DOMAIN_EVENTS
    "drive": "files",  # CONTEXT_DOMAIN_FILES
    "file": "files",  # CONTEXT_DOMAIN_FILES
    "task": "tasks",  # CONTEXT_DOMAIN_TASKS
    "place": "places",  # CONTEXT_DOMAIN_PLACES
    "location": "locations",  # CONTEXT_DOMAIN_LOCATION (domain + "s")
    "weather": "weathers",  # CONTEXT_DOMAIN_WEATHER (domain + "s")
    "wikipedia": "wikipedias",  # CONTEXT_DOMAIN_WIKIPEDIA (domain + "s")
    "perplexity": "perplexitys",  # CONTEXT_DOMAIN_PERPLEXITY (domain + "s")
    "web_search": "web_searchs",  # CONTEXT_DOMAIN_WEB_SEARCH (unified triple source)
    "reminder": "reminders",  # User reminders (internal)
    "route": "routes",  # CONTEXT_DOMAIN_ROUTES (Google Routes directions)
    "query": "querys",  # CONTEXT_DOMAIN_QUERY (domain + "s")
    "web_fetch": "web_fetchs",  # CONTEXT_DOMAIN_WEB_FETCH (evolution F1)
    "mcp": "mcps",  # CONTEXT_DOMAIN_MCP (evolution F2 — global admin MCP tools)
    "mcp_user": "mcps",  # CONTEXT_DOMAIN_MCP (evolution F2.1 — per-user MCP tools)
}


def get_domain_from_tool_name(tool_name: str) -> str | None:
    """
    Extract domain from tool name using substring matching.

    Used by task_orchestrator_node and context_resolution_service
    to determine which domain a tool belongs to.

    Args:
        tool_name: Tool function name (e.g., "search_contacts_tool", "get_email_details_tool").

    Returns:
        Domain name (e.g., "contacts", "emails") or None if not found.

    Examples:
        >>> get_domain_from_tool_name("search_contacts_tool")
        "contacts"
        >>> get_domain_from_tool_name("get_email_details_tool")
        "emails"
        >>> get_domain_from_tool_name("search_events_tool")
        "events"
    """
    if not tool_name:
        return None

    tool_name_lower = tool_name.lower()
    for pattern, domain in TOOL_PATTERN_TO_DOMAIN_MAP.items():
        if pattern in tool_name_lower:
            return domain
    return None


def is_list_tool(tool_name: str) -> bool:
    """
    Check if a tool produces a list (search/list/find operations).

    LIST tools produce results that can be referenced ordinally
    (e.g., "detail du 2ème" after "recherche contacts").

    Args:
        tool_name: Tool function name (e.g., "search_contacts_tool").

    Returns:
        True if this is a LIST-type tool, False otherwise.

    Examples:
        >>> is_list_tool("search_contacts_tool")
        True
        >>> is_list_tool("get_contact_details_tool")
        False
        >>> is_list_tool("list_events_tool")
        True
    """
    if not tool_name:
        return False

    list_patterns = ("search_", "list_", "find_", "query_")
    tool_name_lower = tool_name.lower()
    return any(tool_name_lower.startswith(pattern) for pattern in list_patterns)
