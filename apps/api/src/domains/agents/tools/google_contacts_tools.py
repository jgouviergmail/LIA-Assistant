"""
LangChain v1 tools for Google Contacts operations.

Migration to LangChain v1.0 best practices:
- Tools use ToolRuntime for unified access to config, store, state, etc.
- ToolRuntime replaces InjectedStore + RunnableConfig pattern

Data Registry Mode (LOT 5):
- Tools return UnifiedToolOutput with registry items
- Data Registry mode enabled via registry_enabled=True class attribute
- Uses ToolOutputMixin for registry item creation
- LIAToolNode handles UnifiedToolOutput in the graph

Migration (2025-12-30):
    Migrated from StandardToolOutput to UnifiedToolOutput.
    - All tool functions now return UnifiedToolOutput
    - Draft functions delegated to drafts module (to be migrated separately)

Pattern:
    @tool
    async def my_tool(
        arg: str,
        runtime: ToolRuntime,  # Unified access to runtime resources
    ) -> UnifiedToolOutput:
        user_id = runtime.config.get("configurable", {}).get("user_id")
        data = await runtime.store.get(...)
        # Use runtime.config, runtime.store, runtime.state, etc.
"""

import time
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.field_names import (
    FIELD_CACHED_AT,
    FIELD_ERROR_TYPE,
    FIELD_METADATA,
    FIELD_QUERY,
    FIELD_RESOURCE_NAME,
)
from src.core.i18n_api_messages import APIMessages
from src.core.time_utils import calculate_cache_age_seconds
from src.domains.agents.constants import AGENT_CONTACT, CONTEXT_DOMAIN_CONTACTS
from src.domains.agents.context import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.exceptions import ConnectorNotEnabledError, ToolValidationError
from src.domains.agents.tools.formatters import ContactsFormatter
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.agents.tools.validation_helpers import (
    require_field,
    validate_positive_int_or_default,
)
from src.domains.connectors.clients import GooglePeopleClient
from src.domains.connectors.models import ConnectorType
from src.infrastructure.observability.metrics_agents import (
    contacts_api_calls,
    contacts_api_latency,
    contacts_queries_by_type,
    contacts_results_count,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# URL HELPERS
# ============================================================================


def _build_contact_url(resource_name: str | None) -> str | None:
    """
    Build Google Contacts URL from resource_name.

    Google Contacts URL format: https://contacts.google.com/person/{person_id}
    resource_name format: people/c{person_id} (e.g., people/c6737050419687533025)

    Args:
        resource_name: Contact resource name (e.g., "people/c6737050419687533025")

    Returns:
        Google Contacts URL or None if resource_name is invalid

    Example:
        >>> _build_contact_url("people/c6737050419687533025")
        "https://contacts.google.com/person/c6737050419687533025"
    """
    if not resource_name:
        return None

    # Extract person_id from resource_name
    # Format: people/{person_id} where person_id starts with 'c'
    if resource_name.startswith("people/"):
        person_id = resource_name.replace("people/", "")
        return f"https://contacts.google.com/person/{person_id}"

    return None


# ============================================================================
# FIELD NAME NORMALIZATION (Manifest-Based)
# ============================================================================


def normalize_field_names(tool_name: str, fields: list[str] | None) -> list[str] | None:
    """
    Normalize user-friendly field names to API-specific field names using manifest.

    This generic function reads field_mappings from the tool's manifest in the registry,
    allowing any tool to define custom field name normalization without hardcoding.

    IMPORTANT: Filters out system identifiers (like "resource_name") that are not valid
    API fields and are always returned automatically by the API.

    Args:
        tool_name: Name of the tool (e.g., "search_contacts_tool")
        fields: List of user-friendly or API field names, or None for all fields

    Returns:
        List of normalized API field names (excluding system identifiers), or None if input is None

    Example:
        >>> normalize_field_names("search_contacts_tool", ["name", "emails"])
        ["names", "emailAddresses"]

        >>> normalize_field_names("search_contacts_tool", ["resource_name", "name"])
        ["names"]  # resource_name filtered out - it's not an API field

        >>> normalize_field_names("search_contacts_tool", None)
        None

    Note:
        - Field mappings are read from the tool's manifest in the AgentRegistry
        - System identifiers (resource_name, etc.) are filtered out as they're always returned
        - Unknown field names are passed through as-is (fail-fast with clear API errors)
        - If no field_mappings defined in manifest, all fields pass through unchanged
    """
    if fields is None:
        return None

    # System identifiers that are NOT valid API fields and must be filtered out
    # These are always returned automatically and should never be passed to the API
    SYSTEM_IDENTIFIERS = {"resource_name", "resourceName", "etag"}

    # Import registry to get field_mappings from manifest
    from src.domains.agents.registry import get_global_registry

    registry = get_global_registry()
    tool_manifest = registry.get_tool_manifest(tool_name)

    # Filter out system identifiers BEFORE normalization
    filtered_fields = [f for f in fields if f not in SYSTEM_IDENTIFIERS]

    # If no fields remain after filtering, return None (fetch all fields)
    if not filtered_fields:
        return None

    # If no manifest or no field_mappings, pass through filtered fields unchanged
    if (
        not tool_manifest
        or not hasattr(tool_manifest, "field_mappings")
        or not tool_manifest.field_mappings
    ):
        return filtered_fields

    # Normalize using manifest field_mappings
    field_mappings = tool_manifest.field_mappings
    normalized = []
    for field in filtered_fields:
        # Use mapping if available, otherwise pass through
        normalized_field = field_mappings.get(field, field)
        normalized.append(normalized_field)

    return normalized


# ============================================================================
# ADDRESS SEARCH HELPERS (Fallback for Google API limitation)
# ============================================================================
# Google People API searchContacts only indexes: names, nicknames, emails, phones, organizations
# Addresses are NOT searchable via the API. This module provides client-side fallback.
# Reference: https://developers.google.com/people/api/rest/v1/people/searchContacts


# Address indicator patterns (French, English, German, Spanish, Italian)
ADDRESS_KEYWORDS = {
    # French
    "rue",
    "avenue",
    "boulevard",
    "place",
    "impasse",
    "allée",
    "chemin",
    "passage",
    "voie",
    "quai",
    "cours",
    "square",
    "résidence",
    # English
    "street",
    "road",
    "lane",
    "drive",
    "court",
    "way",
    "circle",
    "terrace",
    # German
    "straße",
    "strasse",
    "weg",
    "platz",
    "gasse",
    # Spanish
    "calle",
    "avenida",
    "paseo",
    "plaza",
    # Italian
    "via",
    "piazza",
    "corso",
    "viale",
    # Common patterns
    "cedex",
    "bp",
    "cs",  # boîte postale, code service
}


def _is_address_query(query: str) -> bool:
    """
    Detect if a search query appears to be an address search.

    Uses heuristics to identify address-like queries that Google People API
    cannot search (addresses are not indexed by the searchContacts endpoint).

    Args:
        query: The search query string

    Returns:
        True if query appears to be an address search

    Examples:
        >>> _is_address_query("2 rue de la liberté")
        True
        >>> _is_address_query("75001 Paris")
        True
        >>> _is_address_query("John Doe")
        False
        >>> _is_address_query("john@example.com")
        False
    """
    if not query:
        return False

    query_lower = query.lower().strip()
    query_words = query_lower.split()

    # Pattern 1: Contains address keyword
    for word in query_words:
        # Remove common punctuation for comparison
        clean_word = word.strip(".,;:!?")
        if clean_word in ADDRESS_KEYWORDS:
            return True

    # Pattern 2: Starts with a number followed by text (e.g., "2 rue", "15 avenue")
    # This is common for street addresses
    import re

    if re.match(r"^\d+\s+\w", query_lower):
        # Check if it's not a phone number pattern
        if not re.match(r"^[\d\s\+\-\.]+$", query):
            return True

    # Pattern 3: Contains postal code patterns
    # French: 5 digits (75001, 69000)
    # German: 5 digits
    # US: 5 digits or 5+4
    # UK: complex pattern (not checked here for simplicity)
    if re.search(r"\b\d{5}\b", query):
        # Make sure it's not just a phone number
        alpha_count = sum(c.isalpha() for c in query)
        if alpha_count > 0:  # Has both digits and letters
            return True

    return False


def _filter_contacts_by_address(
    contacts: list[dict],
    query: str,
    case_insensitive: bool = True,
) -> list[dict]:
    """
    Filter contacts by address using client-side matching.

    Searches through all address fields (formattedValue, streetAddress, city,
    region, postalCode, country) for contacts that match the query.

    Args:
        contacts: List of contact dictionaries from Google People API
        query: Address search query
        case_insensitive: Whether to perform case-insensitive matching (default True)

    Returns:
        List of contacts where at least one address field contains the query

    Example:
        >>> contacts = [
        ...     {"names": [...], "addresses": [{"formattedValue": "2 rue de la liberté, Paris"}]},
        ...     {"names": [...], "addresses": [{"formattedValue": "10 avenue des Champs"}]},
        ... ]
        >>> _filter_contacts_by_address(contacts, "rue de la liberté")
        [{"names": [...], "addresses": [{"formattedValue": "2 rue de la liberté, Paris"}]}]
    """
    if not query or not contacts:
        return contacts

    search_query = query.lower() if case_insensitive else query
    matching_contacts = []

    for contact in contacts:
        addresses = contact.get("addresses", [])
        if not addresses:
            continue

        for address in addresses:
            # Check all address fields
            fields_to_check = [
                address.get("formattedValue", ""),
                address.get("streetAddress", ""),
                address.get("city", ""),
                address.get("region", ""),
                address.get("postalCode", ""),
                address.get("country", ""),
                address.get("extendedAddress", ""),
                address.get("poBox", ""),
            ]

            # Combine all fields for comprehensive search
            combined = " ".join(str(f) for f in fields_to_check if f)
            if case_insensitive:
                combined = combined.lower()

            if search_query in combined:
                matching_contacts.append(contact)
                break  # Found a match, no need to check other addresses

    return matching_contacts


# ============================================================================
# HELPER FUNCTIONS FOR DEPENDENCY INJECTION (REUSABLE PATTERN)
# ============================================================================


def _get_deps_or_fallback(runtime: ToolRuntime) -> tuple[bool, Any]:
    """
    Try to get injected dependencies, fallback to None if not available.

    This is the STANDARD PATTERN for all tools to support both:
    - Optimized execution with injected dependencies (production)
    - Backward compatibility without dependencies (tests, legacy code)

    Returns:
        Tuple of (using_injected_deps: bool, deps: ToolDependencies | None)

    Example:
        using_injected_deps, deps = _get_deps_or_fallback(runtime)
        if using_injected_deps:
            # Use cached DB session and clients
            db = deps.db
            connector_service = await deps.get_connector_service()
        else:
            # Fallback: create new session
            async with get_db_context() as db:
                connector_service = ConnectorService(db)
    """
    try:
        from src.domains.agents.dependencies import get_dependencies

        deps = get_dependencies(runtime)
        logger.debug(
            "tool_using_injected_dependencies",
            db_session_id=id(deps.db),
        )
        return True, deps
    except RuntimeError:
        # Dependencies not injected - this is OK for backward compatibility
        logger.debug("tool_using_fallback_session_creation")
        return False, None


async def _get_connector_and_credentials(
    user_uuid: UUID,
    connector_type: ConnectorType,
    deps: Any = None,
) -> tuple[Any, dict[str, Any], bool]:
    """
    Get connector and credentials using injected dependencies or fallback.

    This helper eliminates code duplication across all tools.

    Args:
        user_uuid: User UUID
        connector_type: Type of connector (e.g., ConnectorType.GOOGLE_CONTACTS)
        deps: Optional ToolDependencies (if None, creates new session)

    Returns:
        Tuple of (connector, credentials, should_close_db: bool)
        should_close_db indicates if caller must close the DB session

    Example:
        connector, credentials, should_close = await _get_connector_and_credentials(
            user_uuid, ConnectorType.GOOGLE_CONTACTS, deps
        )
        # ... use connector and credentials ...
        # No need to close anything - session is managed by deps or context manager
    """
    if deps is not None:
        # Use injected dependencies (optimized path)
        connector_service = await deps.get_connector_service()
        credentials = await connector_service.get_connector_credentials(user_uuid, connector_type)
        return connector_service, credentials, False
    else:
        # Fallback: create new session (backward compatibility)

        # Note: Caller must manage this session with async context manager
        # This is intentional - we return the service but session management
        # remains with the tool's existing try/finally block
        raise NotImplementedError(
            "Fallback path requires session management by caller. "
            "Use the tool's existing 'async with get_db_context()' pattern."
        )


# ============================================================================
# CONTEXT TYPE REGISTRATION (for contextual references)
# ============================================================================


class ContactItem(BaseModel):
    """
    Pydantic schema for contact item validation (optional, for type-safety).

    Note: addresses and birthdays are optional fields that can be included
    when requested via the fields parameter.
    """

    resource_name: str
    name: str
    emails: list[str] = []
    phones: list[str] = []
    addresses: list[dict] = []  # List of address objects with 'formatted' and 'type'
    birthdays: list[str] = []  # List of formatted birthday strings


# Register "contacts" domain at module import
# This enables contextual references like "the 2nd contact", "Marie Martin"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_CONTACTS,  # Primary identifier (NEW: domain-based architecture)
        agent_name=AGENT_CONTACT,
        item_schema=ContactItem,  # Type-safe validation
        primary_id_field=FIELD_RESOURCE_NAME,
        display_name_field="name",
        # Updated: addresses and birthdays added for enhanced fuzzy matching capabilities
        reference_fields=[
            "name",
            "emails",
            "phones",
            "addresses",
            "birthdays",
        ],  # Searchable fields for fuzzy matching
        icon="📇",  # Optional emoji for UI
    )
)


# ============================================================================
# TOOL IMPLEMENTATION CLASS (Phase 3.2 - New Architecture)
# ============================================================================


class SearchContactsTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    Search contacts tool using Phase 3.2 architecture with Data Registry support.

    Benefits vs old implementation:
    - Eliminates 240 lines of DI boilerplate
    - Standardizes error handling
    - Reuses ConnectorTool base class
    - Uses ContactsFormatter (eliminates formatting duplication)

    Data Registry Mode (LOT 5):
    - registry_enabled=True: Returns StandardToolOutput with registry items
    - Registry items contain full contact data for frontend rendering
    - Summary for LLM is compact text with IDs for DSL reference
    - LIAToolNode extracts registry and routes to SSE stream
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    # Data Registry mode enabled - returns StandardToolOutput instead of JSON string
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize search contacts tool with Data Registry support."""
        super().__init__(tool_name="get_contacts_tool", operation="search")
        self.formatter = ContactsFormatter(tool_name="get_contacts_tool", operation="search")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute search contacts API call - business logic only."""
        import re

        from src.core.constants import GOOGLE_CONTACTS_ALL_FIELDS

        settings = get_settings()

        query: str = kwargs[FIELD_QUERY]
        raw_max_results = kwargs.get("max_results")
        default_max_results = settings.contacts_tool_default_max_results
        max_results = validate_positive_int_or_default(raw_max_results, default=default_max_results)
        # Cap at domain-specific limit (CONTACTS_TOOL_DEFAULT_MAX_RESULTS)
        security_cap = settings.contacts_tool_default_max_results
        if max_results > security_cap:
            logger.warning(
                "contacts_search_limit_capped",
                user_id=str(user_id),
                requested_max_results=raw_max_results,
                capped_max_results=security_cap,
                default_max_results=default_max_results,
            )
            max_results = security_cap
        fields: list[str] | None = kwargs.get("fields")
        force_refresh: bool = kwargs.get("force_refresh", False)

        # Clean query: Extract email from RFC 5322 format "Name" <email@domain.com>
        # This handles cases where Planner passes full "from" header instead of just email
        if query and "<" in query and ">" in query:
            match = re.search(r"<([^>]+)>", query)
            if match:
                extracted_email = match.group(1).strip()
                logger.info(
                    "search_contacts_query_cleaned",
                    original_query=query[:50],
                    cleaned_query=extracted_email,
                    user_id=str(user_id),
                )
                query = extracted_email

        # Normalize phone number queries: remove dots, spaces, dashes for better matching
        # French phone: 06.06.06.06.06 -> 0606060606
        # This helps match contacts stored in different formats
        original_query = query
        phone_variants = []  # Will store alternative formats to try

        if query and re.match(r"^[\d\s\.\-\+]+$", query) and len(re.sub(r"[^\d]", "", query)) >= 8:
            normalized_phone = re.sub(r"[\s\.\-]", "", query)
            if normalized_phone != query:
                logger.info(
                    "search_contacts_phone_normalized",
                    original_query=query,
                    normalized_query=normalized_phone,
                    user_id=str(user_id),
                )
                query = normalized_phone

            # Generate French phone variants for fallback
            # Format national: 0606060606 -> Format international: +33606060606, 33606060606
            digits_only = re.sub(r"[^\d]", "", normalized_phone)
            if digits_only.startswith("0") and len(digits_only) == 10:
                # French national format -> generate international variants
                international = "33" + digits_only[1:]  # 33606060606
                international_plus = "+33" + digits_only[1:]  # +33606060606
                phone_variants = [international, international_plus]
            elif digits_only.startswith("33") and len(digits_only) == 11:
                # French international without + -> generate other variants
                national = "0" + digits_only[2:]  # 0606060606
                international_plus = "+" + digits_only  # +33606060606
                phone_variants = [national, international_plus]

        # Track whether user explicitly provided fields (for formatter decision)
        user_provided_fields = fields is not None

        # Apply default fields BEFORE normalization
        # IMPORTANT: Always include "names" field to ensure contact names are displayed
        # Otherwise users see "Inconnu" when planner requests specific fields like ["addresses"]
        fields_to_use = fields if fields else GOOGLE_CONTACTS_ALL_FIELDS
        if fields_to_use and "names" not in fields_to_use:
            fields_to_use = ["names"] + list(fields_to_use)

        # Normalize field names
        normalized_fields = normalize_field_names("get_contacts_tool", fields_to_use)

        # Execute API call with timing
        api_start = time.time()
        results = await client.search_contacts(
            query=query,
            max_results=max_results,
            fields=normalized_fields,
            use_cache=not force_refresh,
        )
        api_duration = time.time() - api_start

        # Track metrics
        contacts_api_latency.labels(operation="search").observe(api_duration)
        contacts_api_calls.labels(operation="search", status="success").inc()

        # Extract contacts
        raw_contacts = results.get("results", [])
        contacts_list = [result.get("person", {}) for result in raw_contacts]

        # ====================================================================
        # PHONE NUMBER VARIANT FALLBACK
        # ====================================================================
        # If no results and we have phone variants to try (e.g., international format)
        if len(contacts_list) == 0 and phone_variants:
            for variant in phone_variants:
                logger.info(
                    "search_contacts_phone_variant_retry",
                    original_query=original_query,
                    variant=variant,
                    user_id=str(user_id),
                )
                variant_results = await client.search_contacts(
                    query=variant,
                    max_results=max_results,
                    fields=normalized_fields,
                    use_cache=not force_refresh,
                )
                variant_contacts = variant_results.get("results", [])
                if variant_contacts:
                    contacts_list = [r.get("person", {}) for r in variant_contacts]
                    results = variant_results
                    logger.info(
                        "search_contacts_phone_variant_success",
                        original_query=original_query,
                        successful_variant=variant,
                        total_results=len(contacts_list),
                        user_id=str(user_id),
                    )
                    break  # Found results, stop trying variants

        # ====================================================================
        # ADDRESS SEARCH - API LIMITATION NOTICE
        # ====================================================================
        # Google People API searchContacts does NOT index addresses.
        # Scanning all contacts client-side is not viable for large contact lists.
        # Instead, we inform the user about this limitation.
        # Reference: https://developers.google.com/people/api/rest/v1/people/searchContacts
        from_cache = results.get("from_cache", False)
        cached_at = results.get(FIELD_CACHED_AT)
        address_search_notice = None

        if len(contacts_list) == 0 and _is_address_query(query):
            logger.info(
                "search_contacts_address_not_supported",
                user_id=str(user_id),
                query=query,
                reason="Google API does not index addresses",
            )
            # Inform user about the limitation
            address_search_notice = (
                f"⚠️ La recherche par adresse « {query} » n'est pas supportée par Google. "
                "L'API Google Contacts permet uniquement de rechercher par nom, email ou téléphone. "
                "Essayez de rechercher par le nom du contact."
            )

        contacts_results_count.labels(operation="search").observe(len(contacts_list))

        # Track query type
        query_type = "name_search"
        if address_search_notice:
            query_type = "address_search_unsupported"
        elif "@" in query:
            query_type = "email_search"
        elif any(c.isdigit() for c in query):
            query_type = "phone_search"
        contacts_queries_by_type.labels(query_type=query_type).inc()

        requested_fields = fields_to_use

        logger.info(
            "search_contacts_success",
            user_id=str(user_id),
            query_preview=query[:20],
            total_results=len(contacts_list),
            api_duration_ms=int(api_duration * 1000),
            fields_count=len(requested_fields),
            address_search_notice=address_search_notice is not None,
        )

        return {
            FIELD_QUERY: query,
            "contacts": contacts_list,
            "fields": requested_fields,
            "user_provided_fields": requested_fields if user_provided_fields else None,
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
            "notice": address_search_notice,  # None if not an address search
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Uses ToolOutputMixin.build_contacts_output() to create:
        - message: Compact text with contact names and IDs
        - registry_updates: Full contact data for frontend rendering
        - metadata: Query info, cache status, etc.

        The message is designed for LLM reasoning while registry
        provides complete data for rich frontend display.

        Example message:
            Trouvé 3 contacts pour "Jean":
            - Jean Dupont (jean.dupont@email.com) [contact_abc123]
            - Jean Martin (jean.martin@corp.com) [contact_def456]
            - Jeanne Petit (jeanne.petit@mail.fr) [contact_ghi789]
        """
        contacts = result.get("contacts", [])
        query = result.get(FIELD_QUERY, "")
        from_cache = result.get("from_cache", False)
        notice = result.get("notice")

        # If there's a notice (e.g., address search not supported), return it directly
        if notice:
            return UnifiedToolOutput.data_success(
                message=notice,
                registry_updates={},
                metadata={
                    "tool_name": "get_contacts_tool",
                    "query": query,
                    "total_results": 0,
                    "notice": notice,
                },
            )

        # Use ToolOutputMixin helper method
        return self.build_contacts_output(
            contacts=contacts,
            query=query,
            from_cache=from_cache,
        )


# Create tool instance (singleton)
_search_contacts_tool_instance = SearchContactsTool()


# ============================================================================
# TOOL FUNCTION (LangChain Registration with new decorator preset)
# ============================================================================


@connector_tool(
    name="search_contacts",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def search_contacts_tool(
    query: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    max_results: int | None = None,
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> UnifiedToolOutput:
    """
    Recherche des contacts Google par nom, email ou téléphone.

    Utilise l'API Google People pour rechercher des contacts correspondant à la requête.
    Supporte la projection de champs pour optimiser les performances.

    **Phase 3.2 Migration:** This tool now uses the new architecture (ConnectorTool base class).
    All boilerplate (DI, OAuth, error handling, formatting) is eliminated.

    **Data Registry Mode (LOT 5):** Returns UnifiedToolOutput with registry items.
    LIAToolNode handles extraction and SSE streaming.

    Args:
        query: Search term (name, email, or phone number).
        runtime: Runtime dependencies (config, store) injected automatically by LangGraph.
        max_results: Maximum number of results (default 10, max 50).
        fields: List of fields to retrieve (optional). If omitted, retrieves
                name, email and phone by default.
        force_refresh: Force cache bypass and retrieve fresh data from the API
                      (default False).

    Returns:
        UnifiedToolOutput with registry items containing contact data

    Examples:
        >>> result = await search_contacts_tool("John Doe", runtime)
        >>> result = await search_contacts_tool("John", runtime, fields=["names", "phoneNumbers"])
        >>> result = await search_contacts_tool("John", runtime, force_refresh=True)
    """
    # Delegate to tool instance (new architecture)
    return await _search_contacts_tool_instance.execute(
        runtime=runtime,
        query=query,
        max_results=max_results,
        fields=fields,
        force_refresh=force_refresh,
    )


# ============================================================================
# TOOL 2: LIST CONTACTS (PHASE 3.2 - MIGRATED)
# ============================================================================


class ListContactsTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    List contacts tool using Phase 3.2 architecture with Data Registry support.

    Migrated from 150-line monolithic function to 60-line class-based architecture.
    All boilerplate (DI, OAuth, error handling, formatting) is handled by base class.

    Data Registry Mode (LOT 5):
    - registry_enabled=True: Returns StandardToolOutput with registry items
    - Registry items contain full contact data for frontend rendering
    - Summary for LLM is compact text with contact names and IDs
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    # Data Registry mode enabled - returns StandardToolOutput instead of JSON string
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize list contacts tool with Data Registry support."""
        super().__init__(tool_name="get_contacts_tool", operation="list")
        self.formatter = ContactsFormatter(tool_name="get_contacts_tool", operation="list")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute list contacts API call - business logic only.

        Args:
            client: GooglePeopleClient instance (cached, ready to use)
            user_id: User UUID
            **kwargs: Tool parameters (query, limit, fields, force_refresh)

        Returns:
            Dict with formatted response (passed to formatter)
        """
        from src.core.config import get_settings
        from src.core.constants import GOOGLE_CONTACTS_ALL_FIELDS

        settings = get_settings()

        # Extract parameters with defaults
        query: str | None = kwargs.get(FIELD_QUERY)
        limit: int = kwargs.get("limit") or settings.contacts_tool_default_limit
        fields: list[str] | None = kwargs.get("fields")
        force_refresh: bool = kwargs.get("force_refresh", False)

        # ====================================================================
        # ADR-006: Tool Safeguard - Cap limit when query is empty
        # ====================================================================
        # If no query provided (list all contacts), enforce maximum limit cap
        # to prevent wasteful fetching of 100+ contacts without criteria
        if not query or (isinstance(query, str) and query.strip() == ""):
            max_limit_without_query = 10  # ADR-006: Reasonable cap for unfiltered lists

            if limit > max_limit_without_query:
                logger.warning(
                    "adr006_list_contacts_limit_capped",
                    user_id=str(user_id),
                    requested_limit=limit,
                    capped_limit=max_limit_without_query,
                    query=query,
                    issue="list_contacts_tool called without query but with high limit",
                    impact=f"Would fetch {limit} contacts without criteria (wasteful)",
                    action=f"Capping limit to {max_limit_without_query}",
                    recommendation="Use get_contacts_tool with query, or resolve_reference for context",
                )

                # Track metric (ADR-006)
                from src.infrastructure.observability.metrics_agents import (
                    langgraph_tool_safeguard_applied_total,
                )

                langgraph_tool_safeguard_applied_total.labels(
                    tool_name="get_contacts_tool",
                    safeguard_type="limit_cap_no_query",
                ).inc()

                # Apply cap
                limit = max_limit_without_query

        # Track whether user explicitly provided fields (for formatter decision)
        user_provided_fields = fields is not None

        # Apply default fields BEFORE normalization
        # IMPORTANT: Always include "names" field to ensure contact names are displayed
        # Otherwise users see "Inconnu" when planner requests specific fields like ["addresses"]
        fields_to_use = fields if fields else GOOGLE_CONTACTS_ALL_FIELDS
        if fields_to_use and "names" not in fields_to_use:
            fields_to_use = ["names"] + list(fields_to_use)

        # Normalize field names (user-friendly → Google API field masks)
        normalized_fields = normalize_field_names("get_contacts_tool", fields_to_use)

        # Track API call start
        api_start = time.time()

        # CRITICAL: When query is provided, use Google's server-side search API
        # instead of client-side filtering. Google's search is more powerful
        # and searches across all name fields (displayName, givenName, familyName, etc.)
        if query:
            # Use normalized fields (already has LIST_FIELDS default applied)
            search_fields = normalized_fields

            # Use Google's searchContacts API for server-side filtering
            search_results = await client.search_contacts(
                query=query,
                max_results=limit,
                fields=search_fields,
                use_cache=not force_refresh,
            )

            # Track API latency
            api_duration = time.time() - api_start
            contacts_api_latency.labels(operation="list").observe(api_duration)

            # Track successful API call
            contacts_api_calls.labels(operation="list", status="success").inc()

            # Extract contacts from search results
            # Search API returns {"results": [{"person": {...}}, ...]}
            raw_results = search_results.get("results", [])
            contacts_list = [result.get("person", {}) for result in raw_results]

            # Note: Search API doesn't support pagination, so has_more is always False
            has_more = False
            from_cache = search_results.get("from_cache", False)
            cached_at = search_results.get(FIELD_CACHED_AT)

            logger.info(
                "list_contacts_using_search_api",
                user_id=str(user_id),
                query=query,
                total_results=len(contacts_list),
                api_duration_ms=int(api_duration * 1000),
            )
        else:
            # No query - use list API for browsing all contacts
            # Architecture v2.0: Always return full details (unified tool)
            list_fields = normalized_fields if fields else GOOGLE_CONTACTS_ALL_FIELDS

            results = await client.list_connections(
                page_size=min(limit, 100),
                fields=list_fields,
                use_cache=not force_refresh,
            )

            # Track API latency
            api_duration = time.time() - api_start
            contacts_api_latency.labels(operation="list").observe(api_duration)

            # Track successful API call
            contacts_api_calls.labels(operation="list", status="success").inc()

            # Extract contacts from results
            contacts_list = results.get("connections", [])
            has_more = bool(results.get("nextPageToken"))
            from_cache = results.get("from_cache", False)
            cached_at = results.get(FIELD_CACHED_AT)

        # Track results count
        contacts_results_count.labels(operation="list").observe(len(contacts_list))

        # Track query type (business metric)
        query_type = "list_filtered" if query else "list_all"
        contacts_queries_by_type.labels(query_type=query_type).inc()

        # Determine requested fields for formatter
        # Architecture v2.0: Always return full details (unified tool)
        requested_fields = fields if fields else GOOGLE_CONTACTS_ALL_FIELDS

        # Log success
        logger.info(
            "list_contacts_success",
            user_id=str(user_id),
            query=query,
            total_contacts=len(contacts_list),
            has_more=has_more,
            api_duration_ms=int(api_duration * 1000),
            fields_count=len(requested_fields),
            used_search_api=bool(query),
        )

        # Return structured data for formatter
        return {
            "contacts": contacts_list,
            "fields": requested_fields,
            "user_provided_fields": requested_fields if user_provided_fields else None,
            "has_more": has_more,
            "from_cache": from_cache,
            FIELD_CACHED_AT: cached_at,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Uses ToolOutputMixin.build_contacts_output() to create:
        - message: Compact text listing contacts with IDs
        - registry_updates: Full contact data for frontend rendering
        - metadata: Pagination info, cache status, etc.
        """
        contacts = result.get("contacts", [])
        from_cache = result.get("from_cache", False)
        has_more = result.get("has_more", False)

        # Build base output using mixin helper
        output = self.build_contacts_output(
            contacts=contacts,
            query=None,  # List operation doesn't use query
            from_cache=from_cache,
        )

        # Add pagination info to metadata
        output.metadata["has_more"] = has_more
        if has_more:
            output.metadata["pagination_note"] = (
                f"Affichage des {len(contacts)} premiers contacts. "
                "Précisez votre recherche pour des résultats plus ciblés."
            )

        return output


# Create tool instance (singleton pattern)
_list_contacts_tool_instance = ListContactsTool()


@connector_tool(
    name="list_contacts",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def list_contacts_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str | None = None,
    limit: int | None = None,
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> UnifiedToolOutput:
    """
    List all Google contacts for the user (with automatic pagination).

    Retrieves up to 10 contacts by default. If more than 10 contacts exist,
    only the first 10 are returned to avoid overload.

    If a query is provided, filters results to return only contacts
    whose name contains the search term (case-insensitive).

    LangChain v1.0 migration with RunnableConfig pattern:
    - user_id extracted from config.configurable["user_id"]
    - store automatically injected via InjectedStore() (graph.compile(store=store))

    **Data Registry Mode (LOT 5):** Returns UnifiedToolOutput with registry items.
    LIAToolNode handles extraction and SSE streaming.

    Args:
        runtime: Runtime dependencies (config, store) injected automatically by LangGraph.
        query: Optional search term to filter by name (default None = all contacts).
        limit: Maximum number of contacts to list (default 10, max 100).
        fields: List of fields to retrieve (optional). If omitted, retrieves
                name, email and phone by default.
        force_refresh: Force cache bypass and retrieve fresh data from the API
                      (default False).

    Returns:
        UnifiedToolOutput with registry items containing contact data

    Example:
        >>> # Basic list (all contacts)
        >>> result = await list_contacts_tool(limit=50)

        >>> # Filtered list by name
        >>> result = await list_contacts_tool(query="dupond", limit=100)

        >>> # Optimized list (emails only)
        >>> result = await list_contacts_tool(fields=["names", "emailAddresses"])

        >>> # Force refresh (bypass cache)
        >>> result = await list_contacts_tool(force_refresh=True)

    Note:
        Redis cache is used by default (5 min TTL), unless force_refresh=True.

        **Phase 3.2 Migration:** This tool now uses the new architecture.
        All boilerplate (DI, OAuth, error handling, formatting) is eliminated.
    """
    # Delegate to tool instance (new architecture)
    return await _list_contacts_tool_instance.execute(
        runtime=runtime,
        query=query,
        limit=limit,
        fields=fields,
        force_refresh=force_refresh,
    )


# ============================================================================
# TOOL 3: GET CONTACT DETAILS (PHASE 3.2 - MIGRATED)
# ============================================================================


class GetContactDetailsTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    Get contact details tool using Phase 3.2 architecture with Data Registry support.

    Handles both single and batch modes.
    All boilerplate (DI, OAuth, error handling, formatting) is handled by base class.

    Data Registry Mode (LOT 5):
    - registry_enabled=True: Returns StandardToolOutput with registry items
    - Single mode: One contact in registry with full details
    - Batch mode: Multiple contacts in registry
    - Errors tracked in tool_metadata
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    # Data Registry mode enabled - returns StandardToolOutput instead of JSON string
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize get contact details tool with Data Registry support."""
        super().__init__(tool_name="get_contacts_tool", operation="details")
        self.formatter = ContactsFormatter(tool_name="get_contacts_tool", operation="details")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute get contact details API call - business logic only.

        Handles both single and batch modes.

        Args:
            client: GooglePeopleClient instance (cached, ready to use)
            user_id: User UUID
            **kwargs: Tool parameters (resource_name, resource_names, fields, force_refresh)

        Returns:
            Dict with formatted response (passed to formatter)
        """
        from src.core.config import get_settings
        from src.core.constants import GOOGLE_CONTACTS_ALL_FIELDS

        settings = get_settings()

        # Extract parameters
        resource_name: str | None = kwargs.get(FIELD_RESOURCE_NAME)
        resource_names: list[str] | list[dict[str, Any]] | None = kwargs.get("resource_names")
        fields: list[str] | None = kwargs.get("fields")
        force_refresh: bool = kwargs.get("force_refresh", False)
        limit_param = kwargs.get("limit") or kwargs.get("max_results")
        default_details_limit = settings.contacts_tool_default_limit
        max_contacts = validate_positive_int_or_default(
            limit_param,
            default=default_details_limit,
            max_value=settings.contacts_tool_default_max_results,
        )

        # =====================================================================
        # COERCION: Tolerate string input for resource_names (Postel's Law)
        # =====================================================================
        # The planner may generate Jinja2 templates that evaluate to:
        # 1. A single resource_name: "people/c123"
        # 2. A CSV of resource_names: "people/c123,people/c456,people/c789"
        #
        # This coercion handles both cases by detecting CSV format.
        # Issue #54: https://github.com/jgouviergmail/LIA-Assistant/issues/54
        # Issue #dupond-15h55: Jinja templates for GROUP operation
        if isinstance(resource_names, str):
            # Detect CSV format: contains comma AND looks like resource_names
            if "," in resource_names and "people/" in resource_names:
                # Split CSV and strip whitespace from each element
                resource_names = [
                    name.strip() for name in resource_names.split(",") if name.strip()
                ]
                logger.info(
                    "resource_names_csv_coerced",
                    original_length=len(resource_names),
                    first_name=resource_names[0] if resource_names else None,
                )
            else:
                # Single resource_name as string
                resource_names = [resource_names]

        # Validation: exactly one of resource_name or resource_names required
        if not resource_name and not resource_names:
            raise ValueError("Either resource_name or resource_names must be provided")

        if resource_name and resource_names:
            raise ValueError("resource_name and resource_names are mutually exclusive")

        # Enforce batch safety limits when multiple resource names are provided
        if resource_names and len(resource_names) > max_contacts:
            logger.warning(
                "get_contact_details_limit_capped",
                user_id=str(user_id),
                requested=len(resource_names),
                capped=max_contacts,
                default_limit=default_details_limit,
            )

            from src.infrastructure.observability.metrics_agents import (
                langgraph_tool_safeguard_applied_total,
            )

            langgraph_tool_safeguard_applied_total.labels(
                tool_name="get_contacts_tool",
                safeguard_type="limit_cap_batch_details",
            ).inc()

            resource_names = list(resource_names)[:max_contacts]

        # Track whether user explicitly provided fields (for formatter decision)
        user_provided_fields = fields is not None

        # Apply default fields BEFORE normalization (to ensure normalize gets non-None input)
        fields_to_use = fields if fields else GOOGLE_CONTACTS_ALL_FIELDS

        # Normalize field names (user-friendly → Google API field masks)
        normalized_fields = normalize_field_names("get_contacts_tool", fields_to_use)

        # Handle batch mode
        if resource_names:
            return await self._execute_batch(
                client,
                user_id,
                resource_names,
                normalized_fields,
                force_refresh,
                fields_to_use,
                user_provided_fields,
            )

        # Handle single mode
        return await self._execute_single(
            client,
            user_id,
            resource_name,
            normalized_fields,
            force_refresh,
            fields_to_use,
            user_provided_fields,
        )

    async def _execute_single(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        resource_name: str,
        normalized_fields: list[str],
        force_refresh: bool,
        requested_fields: list[str],
        user_provided_fields: bool,
    ) -> dict[str, Any]:
        """Execute single contact details fetch."""
        # Track API call start
        api_start = time.time()

        # Execute API call
        result = await client.get_person(
            resource_name=resource_name,
            fields=normalized_fields,
            use_cache=not force_refresh,
        )

        # Track API latency
        api_duration = time.time() - api_start
        contacts_api_latency.labels(operation="details").observe(api_duration)

        # Track successful API call
        contacts_api_calls.labels(operation="details", status="success").inc()

        # Track results count (1 contact)
        contacts_results_count.labels(operation="details").observe(1)

        # Track query type
        contacts_queries_by_type.labels(query_type="details_single").inc()

        # Log success (requested_fields is always non-None now, default applied before normalization)
        logger.info(
            "get_contact_details_success",
            user_id=str(user_id),
            resource_name=resource_name,
            api_duration_ms=int(api_duration * 1000),
            fields_count=len(requested_fields),
        )

        # Return structured data for formatter
        return {
            "contacts": [result],
            "fields": requested_fields,
            "user_provided_fields": requested_fields if user_provided_fields else None,
            "mode": "single",
            "from_cache": result.get("from_cache", False),
            FIELD_CACHED_AT: result.get(FIELD_CACHED_AT),
        }

    async def _execute_batch(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        resource_names: list[str] | list[dict[str, Any]],
        normalized_fields: list[str],
        force_refresh: bool,
        requested_fields: list[str],
        user_provided_fields: bool,
    ) -> dict[str, Any]:
        """Execute batch contact details fetch."""
        # Normalize resource_names (accept both list[str] and list[dict])
        normalized_resource_names = []
        for item in resource_names:
            if isinstance(item, str):
                normalized_resource_names.append(item)
            elif isinstance(item, dict) and FIELD_RESOURCE_NAME in item:
                normalized_resource_names.append(item[FIELD_RESOURCE_NAME])
            else:
                raise ValueError(
                    f"resource_names must be list of strings or list of contact objects with '{FIELD_RESOURCE_NAME}' field. Got: {type(item).__name__}"
                )

        # Track API call start
        api_start = time.time()

        # Fetch all contacts concurrently
        import asyncio

        tasks = [
            client.get_person(
                resource_name=name,
                fields=normalized_fields,
                use_cache=not force_refresh,
            )
            for name in normalized_resource_names
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Track API latency
        api_duration = time.time() - api_start
        contacts_api_latency.labels(operation="details").observe(api_duration)

        # Track successful API call
        contacts_api_calls.labels(operation="details", status="success").inc()

        # Process results (separate successes and errors)
        contacts_list = []
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(
                    {
                        FIELD_RESOURCE_NAME: normalized_resource_names[i],
                        "error": str(result),
                        FIELD_ERROR_TYPE: type(result).__name__,
                    }
                )
            else:
                contacts_list.append(result)

        # Track results count
        contacts_results_count.labels(operation="details").observe(len(contacts_list))

        # Track query type
        contacts_queries_by_type.labels(query_type="details_batch").inc()

        # Log success (requested_fields is always non-None now, default applied before normalization)
        logger.info(
            "get_contact_details_batch_success",
            user_id=str(user_id),
            total_requested=len(normalized_resource_names),
            total_success=len(contacts_list),
            total_errors=len(errors),
            api_duration_ms=int(api_duration * 1000),
            fields_count=len(requested_fields),
        )

        # Return structured data for formatter
        return {
            "contacts": contacts_list,
            "fields": requested_fields,
            "user_provided_fields": requested_fields if user_provided_fields else None,
            "mode": "batch",
            "errors": errors if errors else None,
            "from_cache": False,  # Batch mode doesn't use cache metadata (multiple API calls)
            FIELD_CACHED_AT: None,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Format as Data Registry UnifiedToolOutput with registry items.

        Handles both single and batch modes:
        - Single mode: One contact in registry with full details
        - Batch mode: Multiple contacts in registry, errors in metadata

        Uses ToolOutputMixin.build_contacts_output() for consistent formatting.
        """
        contacts = result.get("contacts", [])
        from_cache = result.get("from_cache", False)
        mode = result.get("mode", "single")
        errors = result.get("errors")

        # Build base output using mixin helper
        output = self.build_contacts_output(
            contacts=contacts,
            query=None,  # Details operation doesn't use query
            from_cache=from_cache,
        )

        # Add mode-specific metadata
        output.metadata["mode"] = mode

        # Add batch errors if any
        if mode == "batch" and errors:
            output.metadata["errors"] = errors
            output.metadata["total_errors"] = len(errors)
            output.metadata["total_success"] = len(contacts)

        return output


# Create tool instance (singleton pattern)
_get_contact_details_tool_instance = GetContactDetailsTool()


# ============================================================================
# Field Extraction Helpers (Session 23)
# ============================================================================


def _extract_field_group_identity(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract identity and names fields from Google Person object.

    Session 23 - Helper #1: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - names: Full name (via _extract_name helper)
    - nicknames: List of nickname values
    - photos: List of photo URLs

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted identity fields
    """
    identity_data = {}

    if "names" in requested_fields:
        identity_data["name"] = ContactsFormatter._extract_name(person)

    if "nicknames" in requested_fields:
        nicknames = person.get("nicknames", [])
        identity_data["nicknames"] = [
            nick.get("value", "") for nick in nicknames if nick.get("value")
        ]

    if "photos" in requested_fields:
        photos = person.get("photos", [])
        # DEBUG: Log raw photo data to understand default field behavior
        logger.debug(
            "photos_raw_data",
            photos_count=len(photos),
            photos_data=[
                {"url": p.get("url", "")[:50], "default": p.get("default")} for p in photos
            ],
        )
        # Use same logic as ContactsFormatter._extract_photos for consistency
        # Google's "default" field = True means it's a generated avatar (letter + color)
        extracted_photos = []
        for photo in photos:
            url = photo.get("url", "")
            if not url:
                continue
            photo_data: dict[str, str] = {"url": url}
            # Mark if this is a Google-generated avatar (not a real uploaded photo)
            if is_default := photo.get("default"):
                photo_data["is_default"] = str(is_default)
            extracted_photos.append(photo_data)
        identity_data["photos"] = extracted_photos

    return identity_data


def _extract_field_group_contact(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract contact information fields from Google Person object.

    Session 23 - Helper #2: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - emailAddresses: Email addresses (via _extract_emails helper)
    - phoneNumbers: Phone numbers (via _extract_phones helper)
    - addresses: Physical addresses (via _extract_addresses helper)

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted contact information fields
    """
    contact_info = {}

    if "emailAddresses" in requested_fields:
        contact_info["emails"] = ContactsFormatter._extract_emails(person)

    if "phoneNumbers" in requested_fields:
        contact_info["phones"] = ContactsFormatter._extract_phones(person)

    if "addresses" in requested_fields:
        contact_info["addresses"] = ContactsFormatter._extract_addresses(person)

    return contact_info


def _extract_field_group_personal(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract personal information fields from Google Person object.

    Session 23 - Helper #3: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - biographies: Biography/about text values
    - birthdays: Birthday information (via _extract_birthdays helper)

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted personal information fields
    """
    personal_data = {}

    if "biographies" in requested_fields:
        biographies = person.get("biographies", [])
        personal_data["biographies"] = [
            bio.get("value", "") for bio in biographies if bio.get("value")
        ]

    if "birthdays" in requested_fields:
        personal_data["birthdays"] = _extract_birthdays(person)

    return personal_data


def _extract_field_group_professional(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract professional information fields from Google Person object.

    Session 23 - Helper #4: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - organizations: Organization/job information (via _extract_organizations helper)
    - occupations: Occupation/title values
    - skills: Skill values

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted professional information fields
    """
    professional_data = {}

    if "organizations" in requested_fields:
        professional_data["organizations"] = ContactsFormatter._extract_organizations(person)

    if "occupations" in requested_fields:
        occupations = person.get("occupations", [])
        professional_data["occupations"] = [
            occ.get("value", "") for occ in occupations if occ.get("value")
        ]

    if "skills" in requested_fields:
        skills = person.get("skills", [])
        professional_data["skills"] = [
            skill.get("value", "") for skill in skills if skill.get("value")
        ]

    return professional_data


def _extract_field_group_social(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract social and relationship fields from Google Person object.

    Session 23 - Helper #5: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - relations: Relationships (person, type)
    - interests: Interest values
    - events: Event information (type, date)

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted social and relationship fields
    """
    social_data = {}

    if "relations" in requested_fields:
        relations = person.get("relations", [])
        social_data["relations"] = [
            {"person": rel.get("person", ""), "type": rel.get("type", "")}
            for rel in relations
            if rel.get("person")
        ]

    if "interests" in requested_fields:
        interests = person.get("interests", [])
        social_data["interests"] = [int.get("value", "") for int in interests if int.get("value")]

    if "events" in requested_fields:
        events = person.get("events", [])
        social_data["events"] = [
            {
                "type": event.get("type", ""),
                "date": f"{event.get('date', {}).get('day', '')}/{event.get('date', {}).get('month', '')}/{event.get('date', {}).get('year', '')}",
            }
            for event in events
            if event.get("date")
        ]

    return social_data


def _extract_field_group_communication(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract links and communication fields from Google Person object.

    Session 23 - Helper #6: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - calendarUrls: Calendar URL values
    - imClients: IM client information (username, protocol)

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted communication fields
    """
    communication_data = {}

    if "calendarUrls" in requested_fields:
        calendar_urls = person.get("calendarUrls", [])
        communication_data["calendarUrls"] = [
            cal.get("url", "") for cal in calendar_urls if cal.get("url")
        ]

    if "imClients" in requested_fields:
        im_clients = person.get("imClients", [])
        communication_data["imClients"] = [
            {"username": im.get("username", ""), "protocol": im.get("protocol", "")}
            for im in im_clients
            if im.get("username")
        ]

    return communication_data


def _extract_field_group_metadata(
    person: dict[str, Any],
    requested_fields: list[str],
) -> dict[str, Any]:
    """
    Extract metadata and custom data fields from Google Person object.

    Session 23 - Helper #7: Extracted from _fetch_single_contact_details().

    Fields extracted:
    - metadata: Contact metadata (sources, objectType)
    - locations: Location information (value, type)

    Args:
        person: Google People API person object
        requested_fields: List of fields to extract

    Returns:
        Dict with extracted metadata fields
    """
    metadata_data = {}

    if FIELD_METADATA in requested_fields:
        metadata = person.get(FIELD_METADATA, {})
        if metadata:
            metadata_data[FIELD_METADATA] = {
                "sources": metadata.get("sources", []),
                "objectType": metadata.get("objectType", ""),
            }

    if "locations" in requested_fields:
        locations = person.get("locations", [])
        metadata_data["locations"] = [
            {"value": loc.get("value", ""), "type": loc.get("type", "")}
            for loc in locations
            if loc.get("value")
        ]

    return metadata_data


async def _fetch_single_contact_details(
    resource_name: str,
    runtime: "ToolRuntime",
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Business logic to retrieve details for a single contact.

    This function contains the reusable logic to fetch a contact.
    It is used by both single mode AND batch mode.

    Args:
        resource_name: Google contact identifier
        runtime: ToolRuntime with config, store, deps
        fields: Fields to retrieve (user-friendly names or API field masks)
        force_refresh: Bypass cache

    Returns:
        Dict with contact data (no JSON string, no "success" wrapping)

    Raises:
        Exception: Si erreur lors du fetch
    """
    import time

    # Validate runtime config using helper
    config = validate_runtime_config(runtime, "_fetch_single_contact_details")
    if isinstance(config, UnifiedToolOutput):
        raise ValueError(f"Runtime config validation failed: {config.message}")

    # Extract validated config
    user_id_str = config.user_id

    user_uuid = parse_user_id(user_id_str)

    # Normalize field names from user-friendly to Google API field masks (manifest-based)
    # This allows LLM to use "name", "emails", etc. while API receives correct paths
    normalized_fields = normalize_field_names("get_contacts_tool", fields)

    # Resolve active contacts provider (Google or Apple) dynamically
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    using_injected_deps, deps = _get_deps_or_fallback(runtime)

    if using_injected_deps:
        # === OPTIMIZED PATH: Use injected dependencies ===
        client, _resolved_type = await resolve_client_for_category("contacts", user_uuid, deps)

        # === EXECUTE TOOL LOGIC ===
        api_start = time.time()
        person = await client.get_person(
            resource_name, fields=normalized_fields, use_cache=not force_refresh
        )
        api_duration = time.time() - api_start

    else:
        # === FALLBACK PATH: Backward compatibility (tests, legacy) ===
        # Uses dynamic provider resolution (Google or Apple)
        from src.domains.connectors.clients.registry import ClientRegistry
        from src.domains.connectors.provider_resolver import resolve_active_connector
        from src.domains.connectors.service import ConnectorService
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            connector_service = ConnectorService(db)
            resolved_type = await resolve_active_connector(user_uuid, "contacts", connector_service)

            if resolved_type is None:
                raise ConnectorNotEnabledError(
                    APIMessages.connector_not_enabled("Contacts"),
                    connector_name="Contacts",
                )

            if resolved_type.is_apple:
                credentials = await connector_service.get_apple_credentials(
                    user_uuid, resolved_type
                )
            else:
                credentials = await connector_service.get_connector_credentials(
                    user_uuid, resolved_type
                )

            if not credentials:
                raise ConnectorNotEnabledError(
                    APIMessages.connector_not_enabled(resolved_type.value),
                    connector_name=resolved_type.value,
                )

            # Create client via registry (backward compatibility, no caching)
            client_class = ClientRegistry.get_client_class(resolved_type)
            if client_class is None:
                raise ConnectorNotEnabledError(
                    f"No client registered for {resolved_type.value}",
                    connector_name=resolved_type.value,
                )
            client = client_class(user_uuid, credentials, connector_service)

            # === EXECUTE SAME TOOL LOGIC ===
            api_start = time.time()
            person = await client.get_person(
                resource_name, fields=normalized_fields, use_cache=not force_refresh
            )
            api_duration = time.time() - api_start

    # Track API metrics
    contacts_api_calls.labels(
        operation="details",
        status="success",
    ).inc()
    contacts_api_latency.labels(operation="details").observe(api_duration)

    # Format detailed info - conditional based on fields
    from src.core.constants import GOOGLE_CONTACTS_ALL_FIELDS

    requested_fields = fields if fields else GOOGLE_CONTACTS_ALL_FIELDS

    # Build contact data object
    contact_data = {
        FIELD_RESOURCE_NAME: person.get("resourceName", ""),
    }

    # Extract all field groups using Session 23 helper functions
    contact_data.update(_extract_field_group_identity(person, requested_fields))
    contact_data.update(_extract_field_group_contact(person, requested_fields))
    contact_data.update(_extract_field_group_personal(person, requested_fields))
    contact_data.update(_extract_field_group_professional(person, requested_fields))
    contact_data.update(_extract_field_group_social(person, requested_fields))
    contact_data.update(_extract_field_group_communication(person, requested_fields))
    contact_data.update(_extract_field_group_metadata(person, requested_fields))

    # Track results count (always 1 for details)
    contacts_results_count.labels(operation="details").observe(1)

    # Extract freshness metadata from client response (V2: real cache detection)
    from_cache = person.get("from_cache", False)
    cached_at = person.get(FIELD_CACHED_AT)
    data_source = "cache" if from_cache else "api"

    # Calculate cache age if cached (using centralized utility - DRY principle)
    cache_age_seconds = None
    if from_cache and cached_at:
        cache_age_seconds = calculate_cache_age_seconds(cached_at)

    logger.info(
        "get_contact_details_success",
        user_id=user_id_str,
        resource_name=resource_name,
        api_duration_ms=int(api_duration * 1000),
        data_source=data_source,
    )

    # Return data with metadata (caller will wrap in appropriate format)
    return {
        "contact_data": contact_data,
        "data_source": data_source,
        "cache_age_seconds": cache_age_seconds,
    }


@connector_tool(
    name="get_contact_details",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def get_contact_details_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    resource_name: str | None = None,
    resource_names: (
        str | list[str] | list[dict[str, Any]] | None
    ) = None,  # str accepted for Jinja2 coercion (Issue #54)
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> UnifiedToolOutput:
    """
    Retrieve details for one or more contacts from their Google Contacts identifiers.

    Uses the resource_name (Google identifier) to retrieve all available information:
    name, emails, phones, addresses, organization, birthday, etc.

    LangChain v1.0 migration with RunnableConfig pattern:
    - user_id extracted from config.configurable["user_id"]
    - store automatically injected via InjectedStore() (graph.compile(store=store))

    **Data Registry Mode (LOT 5):** Returns UnifiedToolOutput with registry items.
    LIAToolNode handles extraction and SSE streaming.

    Args:
        runtime: Runtime dependencies (config, store) injected automatically by LangGraph.
        resource_name: Google contact identifier (e.g., "people/c1234567890").
        resource_names: List of identifiers for batch retrieval (alternative to resource_name).
        fields: List of fields to retrieve (optional). If omitted, retrieves
                ALL fields (default behavior for detailed view).
        force_refresh: Force cache bypass and retrieve fresh data from the API
                      (default False).

    Returns:
        UnifiedToolOutput with registry items containing contact details

    Example:
        >>> # Full details (all fields)
        >>> result = await get_contact_details_tool("people/c123")

        >>> # Minimal details (name + email only)
        >>> result = await get_contact_details_tool("people/c123", fields=["names", "emailAddresses"])

        >>> # Force refresh (bypass cache)
        >>> result = await get_contact_details_tool("people/c123", force_refresh=True)

    Note:
        The resource_name is obtained via get_contacts_tool (unified tool).

        IMPORTANT - User references:
        If the user references a contact by position ("the 4th", "the 2nd", "last"),
        you MUST call resolve_reference() FIRST to get the resource_name:

        REQUIRED flow for references:
          User: "affiche le détail du 4"
          1. resolve_reference(reference="4", domain="contacts")
             → Retourne: {"success": true, "item": {"resource_name": "people/c123...", ...}}
          2. Extraire item.resource_name du résultat
          3. get_contact_details_tool(resource_name="people/c123...")

        ❌ NE JAMAIS deviner le resource_name à partir d'une référence:
           "4" → "people/c4" ← FAUX (format invalide)
           Utilise TOUJOURS resolve_reference() pour les références utilisateur.

        Le cache Redis est utilisé par défaut (5 min TTL), sauf si force_refresh=True.

        **Phase 3.2 Migration:** This tool now uses the new architecture.
        All boilerplate (DI, OAuth, error handling, formatting) is eliminated.
    """
    # Delegate to tool instance (new architecture)
    return await _get_contact_details_tool_instance.execute(
        runtime=runtime,
        resource_name=resource_name,
        resource_names=resource_names,
        fields=fields,
        force_refresh=force_refresh,
    )


# Helper functions to extract structured data from Google People API responses
# NOTE: Most extractors are now centralized in ContactsFormatter
# See: src/domains/agents/tools/formatters.py


def _extract_birthdays(person: dict) -> list[dict]:
    """
    Extract raw birthdays from person object.

    Returns raw birthday data structure to be formatted by ContactsFormatter.
    DO NOT format here - let the formatter handle localization and formatting.

    Returns:
        List of birthday dicts with 'date' key containing {year, month, day}
    """
    return person.get("birthdays", [])


# ============================================================================
# TOOL 4: CREATE CONTACT (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class CreateContactInput(BaseModel):
    """Input schema for create_contact_tool."""

    name: str
    email: str | None = None
    phone: str | None = None
    organization: str | None = None
    notes: str | None = None


class CreateContactDraftTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    Create contact tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.

    This tool creates a DRAFT that requires user confirmation before creating.
    The contact is NOT created until the user confirms via HITL.

    Flow:
    1. Tool creates draft → StandardToolOutput with requires_confirmation=True
    2. LIAToolNode detects requires_confirmation → sets pending_draft_critique
    3. Graph routes to draft_critique node
    4. User confirms/edits/cancels via HITL
    5. On confirm: execute_fn creates the contact

    Benefits:
    - User can review contact data before creating
    - User can edit name/email/phone before confirming
    - Prevents duplicate contacts
    - Audit trail of drafts and confirmations
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    # Data Registry mode enabled - creates draft for HITL confirmation
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize create contact draft tool."""
        super().__init__(tool_name="create_contact_tool", operation="create_draft")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare contact draft data (no API call yet).

        The actual creation happens after user confirms via HITL.
        This method only validates and prepares the data.

        Args:
            client: GooglePeopleClient (not used here, but required by base class)
            user_id: User UUID
            **kwargs: Contact parameters (name, email, phone, organization, notes)

        Returns:
            Dict with contact draft data for Data Registry formatting
        """
        name: str = require_field(kwargs, "name")
        email: str | None = kwargs.get("email")
        phone: str | None = kwargs.get("phone")
        organization: str | None = kwargs.get("organization")
        notes: str | None = kwargs.get("notes")

        logger.info(
            "create_contact_draft_prepared",
            user_id=str(user_id),
            name=name,
            has_email=email is not None,
            has_phone=phone is not None,
        )

        # Return draft data for Data Registry formatting
        # Note: No API call here - contact will be created after user confirms
        return {
            "name": name,
            "email": email,
            "phone": phone,
            "organization": organization,
            "notes": notes,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create contact draft via DraftService.

        Returns UnifiedToolOutput with:
        - DRAFT registry item containing contact content
        - requires_confirmation=True in metadata
        - Actions: confirm, edit, cancel

        The LIAToolNode will detect requires_confirmation and route
        to draft_critique node for HITL flow.
        """
        from src.domains.agents.drafts import create_contact_draft

        # create_contact_draft returns UnifiedToolOutput directly
        return create_contact_draft(
            name=result["name"],
            email=result.get("email"),
            phone=result.get("phone"),
            organization=result.get("organization"),
            notes=result.get("notes"),
            source_tool="create_contact_tool",
            user_language=self.get_user_language(),
        )


# ============================================================================
# LEGACY: Direct Create (for backward compatibility during transition)
# ============================================================================


class CreateContactDirectTool(ConnectorTool[GooglePeopleClient]):
    """
    Create contact tool that executes immediately (no HITL).

    WARNING: This tool creates contacts WITHOUT user confirmation.
    Use CreateContactDraftTool instead for production.

    This class is kept for:
    1. Backward compatibility during LOT 5.4 migration
    2. execute_fn in DraftCritiqueInteraction (actual create after confirm)
    3. Testing/debugging without HITL flow

    For normal use, prefer CreateContactDraftTool which creates a draft
    and requires user confirmation before creating.
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    def __init__(self) -> None:
        """Initialize direct create contact tool."""
        super().__init__(tool_name="create_contact_direct_tool", operation="create")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute create contact API call - business logic only."""
        name: str = require_field(kwargs, "name")
        email: str | None = kwargs.get("email")
        phone: str | None = kwargs.get("phone")
        organization: str | None = kwargs.get("organization")
        notes: str | None = kwargs.get("notes")

        # Create contact
        result = await client.create_contact(
            name=name,
            email=email,
            phone=phone,
            organization=organization,
            notes=notes,
        )

        logger.info(
            "contacts_contact_created_via_tool",
            user_id=str(user_id),
            resource_name=result.get("resourceName"),
            name=name,
        )

        return {
            "success": True,
            "resource_name": result.get("resourceName"),
            "name": name,
            "email": email,
            "message": APIMessages.contact_created_successfully(name),
        }


# Create tool instance (singleton)
_create_contact_draft_tool_instance = CreateContactDraftTool()


@connector_tool(
    name="create_contact",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="write",
)
async def create_contact_tool(
    name: Annotated[str, "Contact full name (required)"],
    email: Annotated[str | None, "Contact email address (optional)"] = None,
    phone: Annotated[str | None, "Contact phone number (optional)"] = None,
    organization: Annotated[str | None, "Company/organization name (optional)"] = None,
    notes: Annotated[str | None, "Additional notes (optional)"] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Create a contact in Google Contacts (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The contact is NOT created until the user confirms via HITL.

    Data Registry LOT 5.4: Write operations with Draft/Critique/Execute flow.

    Flow:
    1. Tool creates draft with contact data
    2. User sees preview and can confirm/edit/cancel
    3. On confirm, contact is actually created

    Args:
        name: Contact full name (required)
        email: Contact email address (optional)
        phone: Contact phone number (optional)
        organization: Company/organization name (optional)
        notes: Additional notes (optional)
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True in metadata

    Example response message:
        "Brouillon créé: Contact 'Jean Dupont' [draft_abc123]
         Action requise: confirmez, modifiez ou annulez."
    """
    # Delegate to draft tool instance (Data Registry mode)
    return await _create_contact_draft_tool_instance.execute(
        runtime=runtime,
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
    )


# ============================================================================
# DRAFT EXECUTION HELPER (LOT 5.4)
# ============================================================================


async def execute_contact_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact draft: actually create the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.

    This is the execute_fn passed to DraftService.process_draft_action().
    It retrieves the Google People client and creates the contact.

    Args:
        draft_content: Dict with contact content from draft
            {name, email, phone, organization, notes}
        user_id: User UUID
        deps: ToolDependencies for getting Google People client

    Returns:
        Dict with create result:
            {success, resource_name, name, email, message}

    Raises:
        Exception: If contact creation fails
    """
    # Get contacts client via dynamic provider resolution
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    # Create contact
    result = await client.create_contact(
        name=draft_content["name"],
        email=draft_content.get("email"),
        phone=draft_content.get("phone"),
        organization=draft_content.get("organization"),
        notes=draft_content.get("notes"),
    )

    logger.info(
        "contact_draft_executed",
        user_id=str(user_id),
        resource_name=result.get("resourceName"),
        name=draft_content["name"],
    )

    resource_name = result.get("resourceName")
    html_link = _build_contact_url(resource_name)

    return {
        "success": True,
        "resource_name": resource_name,
        "html_link": html_link,
        "name": draft_content["name"],
        "email": draft_content.get("email"),
        "message": APIMessages.contact_created_successfully(draft_content["name"]),
    }


# ============================================================================
# TOOL 5: UPDATE CONTACT (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class UpdateContactDraftTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    Update contact tool with Draft/HITL integration.

    Data Registry LOT 5.4: Write operations with confirmation flow.
    This tool creates a DRAFT that requires user confirmation before updating.
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize update contact draft tool."""
        super().__init__(tool_name="update_contact_tool", operation="update_draft")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare contact update draft data (no API call yet).

        The actual update happens after user confirms via HITL.
        """
        resource_name: str = require_field(kwargs, "resource_name")
        name: str | None = kwargs.get("name")
        email: str | None = kwargs.get("email")
        phone: str | None = kwargs.get("phone")
        organization: str | None = kwargs.get("organization")
        notes: str | None = kwargs.get("notes")
        address: str | None = kwargs.get("address")

        # Fetch current contact to show in draft comparison
        current_contact = await client.get_person(resource_name, use_cache=False)

        logger.info(
            "update_contact_draft_prepared",
            user_id=str(user_id),
            resource_name=resource_name,
            has_name=name is not None,
            has_email=email is not None,
            has_phone=phone is not None,
            has_address=address is not None,
        )

        return {
            "resource_name": resource_name,
            "name": name,
            "email": email,
            "phone": phone,
            "organization": organization,
            "notes": notes,
            "address": address,
            "current_contact": current_contact,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create contact update draft via DraftService.

        Returns UnifiedToolOutput with requires_confirmation=True in metadata.
        """
        from src.domains.agents.drafts import create_contact_update_draft

        # create_contact_update_draft returns UnifiedToolOutput directly
        return create_contact_update_draft(
            resource_name=result["resource_name"],
            name=result.get("name"),
            email=result.get("email"),
            phone=result.get("phone"),
            organization=result.get("organization"),
            notes=result.get("notes"),
            address=result.get("address"),
            current_contact=result.get("current_contact"),
            source_tool="update_contact_tool",
            user_language=self.get_user_language(),
        )


# Direct update tool for execute_fn callback
class UpdateContactDirectTool(ConnectorTool[GooglePeopleClient]):
    """Update contact that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    def __init__(self) -> None:
        super().__init__(tool_name="update_contact_direct_tool", operation="update")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute update contact API call - business logic only."""
        resource_name: str = kwargs["resource_name"]
        name: str | None = kwargs.get("name")
        email: str | None = kwargs.get("email")
        phone: str | None = kwargs.get("phone")
        organization: str | None = kwargs.get("organization")
        notes: str | None = kwargs.get("notes")
        address: str | None = kwargs.get("address")

        result = await client.update_contact(
            resource_name=resource_name,
            name=name,
            email=email,
            phone=phone,
            organization=organization,
            notes=notes,
            address=address,
        )

        # Get display name from updated contact
        names = result.get("names", [])
        display_name = names[0].get("displayName") if names else name or "Contact"

        logger.info(
            "contact_updated_via_tool",
            user_id=str(user_id),
            resource_name=resource_name,
        )

        return {
            "success": True,
            "resource_name": resource_name,
            "name": display_name,
            "message": APIMessages.contact_updated_successfully(display_name),
        }


_update_contact_draft_tool_instance = UpdateContactDraftTool()


@connector_tool(
    name="update_contact",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="write",
)
async def update_contact_tool(
    resource_name: Annotated[str, "Contact resource name (people/c...) - required"],
    name: Annotated[str | None, "New contact name (optional)"] = None,
    email: Annotated[str | None, "New contact email (optional)"] = None,
    phone: Annotated[str | None, "New contact phone (optional)"] = None,
    organization: Annotated[str | None, "New organization name (optional)"] = None,
    notes: Annotated[str | None, "New notes (optional)"] = None,
    address: Annotated[
        str | None, "New address (optional, e.g. '15 rue de la Paix, Paris 75001')"
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Update an existing contact in Google Contacts (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The contact is NOT updated until the user confirms via HITL.

    Args:
        resource_name: Contact resource name (people/c...) - required
        name: New contact name (optional)
        email: New contact email (optional)
        phone: New contact phone (optional)
        organization: New organization name (optional)
        notes: New notes (optional)
        address: New address (optional, e.g. '15 rue de la Paix, Paris 75001')
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True in metadata
    """
    return await _update_contact_draft_tool_instance.execute(
        runtime=runtime,
        resource_name=resource_name,
        name=name,
        email=email,
        phone=phone,
        organization=organization,
        notes=notes,
        address=address,
    )


# ============================================================================
# TOOL 6: DELETE CONTACT (LOT 5.4 - Draft/HITL Integration)
# ============================================================================


class DeleteContactDraftTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """
    Delete contact tool with Draft/HITL integration.

    Data Registry LOT 5.4: Destructive operations require explicit confirmation.
    """

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize delete contact draft tool."""
        super().__init__(tool_name="delete_contact_tool", operation="delete_draft")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Prepare contact deletion draft data.

        First fetches contact details to show user what will be deleted.
        """
        resource_name: str = kwargs["resource_name"]

        if not resource_name:
            raise ToolValidationError(
                APIMessages.field_required("resource_name"), field="resource_name"
            )

        # Fetch contact details to show user what will be deleted
        contact = await client.get_person(resource_name, use_cache=False)

        logger.info(
            "delete_contact_draft_prepared",
            user_id=str(user_id),
            resource_name=resource_name,
        )

        return {
            "resource_name": resource_name,
            "contact": contact,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """
        Create contact deletion draft via DraftService.

        Returns UnifiedToolOutput with requires_confirmation=True in metadata.
        """
        from src.domains.agents.drafts import create_contact_delete_draft

        # create_contact_delete_draft returns UnifiedToolOutput directly
        return create_contact_delete_draft(
            resource_name=result["resource_name"],
            contact=result.get("contact"),
            source_tool="delete_contact_tool",
            user_language=self.get_user_language(),
        )


# Direct delete tool for execute_fn callback
class DeleteContactDirectTool(ConnectorTool[GooglePeopleClient]):
    """Delete contact that executes immediately (for HITL callback)."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"

    def __init__(self) -> None:
        super().__init__(tool_name="delete_contact_direct_tool", operation="delete")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute delete contact API call - business logic only."""
        resource_name: str = kwargs["resource_name"]

        await client.delete_contact(resource_name)

        logger.info(
            "contact_deleted_via_tool",
            user_id=str(user_id),
            resource_name=resource_name,
        )

        return {
            "success": True,
            "resource_name": resource_name,
            "message": APIMessages.contact_deleted_successfully(),
        }


_delete_contact_draft_tool_instance = DeleteContactDraftTool()


@connector_tool(
    name="delete_contact",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="write",
)
async def delete_contact_tool(
    resource_name: Annotated[str, "Contact resource name (people/c...) - required"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Delete a contact from Google Contacts (with user confirmation).

    IMPORTANT: This tool creates a DRAFT that requires user confirmation.
    The contact is NOT deleted until the user confirms via HITL.

    This is a destructive operation that cannot be undone.

    Args:
        resource_name: Contact resource name (people/c...) - required
        runtime: Tool runtime (injected)

    Returns:
        UnifiedToolOutput with DRAFT registry item and requires_confirmation=True in metadata
    """
    return await _delete_contact_draft_tool_instance.execute(
        runtime=runtime,
        resource_name=resource_name,
    )


# ============================================================================
# DRAFT EXECUTION HELPERS (LOT 5.4)
# ============================================================================


async def execute_contact_update_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact update draft: actually update the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    result = await client.update_contact(
        resource_name=draft_content["resource_name"],
        name=draft_content.get("name"),
        email=draft_content.get("email"),
        phone=draft_content.get("phone"),
        organization=draft_content.get("organization"),
        notes=draft_content.get("notes"),
    )

    # Get display name
    names = result.get("names", [])
    display_name = names[0].get("displayName") if names else draft_content.get("name", "Contact")

    resource_name = draft_content["resource_name"]
    html_link = _build_contact_url(resource_name)

    logger.info(
        "contact_update_draft_executed",
        user_id=str(user_id),
        resource_name=resource_name,
    )

    return {
        "success": True,
        "resource_name": resource_name,
        "html_link": html_link,
        "name": display_name,
        "message": APIMessages.contact_updated_successfully(display_name),
    }


async def execute_contact_delete_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """
    Execute a contact delete draft: actually delete the contact.

    Called by DraftCritiqueInteraction.process_draft_action() when user confirms.
    """
    from src.domains.connectors.provider_resolver import resolve_client_for_category

    client, _resolved_type = await resolve_client_for_category("contacts", user_id, deps)

    await client.delete_contact(draft_content["resource_name"])

    # Get name from contact data if available
    contact = draft_content.get("contact", {})
    names = contact.get("names", [])
    display_name = names[0].get("displayName") if names else ""

    logger.info(
        "contact_delete_draft_executed",
        user_id=str(user_id),
        resource_name=draft_content["resource_name"],
    )

    return {
        "success": True,
        "resource_name": draft_content["resource_name"],
        "name": display_name,
        "message": APIMessages.contact_deleted_successfully(display_name),
    }


# ============================================================================
# UNIFIED TOOL: GET CONTACTS (v2.0 - replaces search + list + details)
# ============================================================================


@connector_tool(
    name="get_contacts",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def get_contacts_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    query: str | None = None,
    resource_name: str | None = None,
    resource_names: str | list[str] | list[dict[str, Any]] | None = None,
    max_results: int | None = None,
    fields: list[str] | None = None,
    force_refresh: bool = False,
) -> UnifiedToolOutput:
    """
    Get contacts with full details - unified search, list and retrieval.

    Architecture Simplification (2026-01):
    - Replaces search_contacts_tool + list_contacts_tool + get_contact_details_tool
    - Always returns FULL contact details (names, emails, phones, addresses, etc.)
    - Supports query mode (search) OR ID mode (direct fetch) OR list mode

    Modes:
    - Query mode: get_contacts_tool(query="John") → search + return full details
    - ID mode: get_contacts_tool(resource_name="people/c123") → fetch specific contact
    - Batch mode: get_contacts_tool(resource_names=["people/c1", "people/c2"])
    - List mode: get_contacts_tool() → return all contacts with full details

    Args:
        runtime: Runtime dependencies injected automatically.
        query: Search term (name, email, phone) - triggers search mode.
        resource_name: Single contact ID for direct fetch.
        resource_names: Multiple contact IDs for batch fetch.
        max_results: Maximum results (default 10, max 50).
        fields: Specific fields to retrieve (optional).
        force_refresh: Bypass cache (default False).

    Returns:
        UnifiedToolOutput with registry items containing contact data.
    """
    # Route to appropriate implementation based on parameters
    if resource_name or resource_names:
        # ID mode: direct fetch with full details
        return await _get_contact_details_tool_instance.execute(
            runtime=runtime,
            resource_name=resource_name,
            resource_names=resource_names,
            fields=fields,
            force_refresh=force_refresh,
        )
    elif query:
        # Query mode: search + full details
        return await _search_contacts_tool_instance.execute(
            runtime=runtime,
            query=query,
            max_results=max_results,
            fields=fields,
            force_refresh=force_refresh,
        )
    else:
        # List mode: return all contacts with full details
        return await _list_contacts_tool_instance.execute(
            runtime=runtime,
            limit=max_results,
            fields=fields,
            force_refresh=force_refresh,
        )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Unified tool (v2.0 - replaces search + list + details)
    "get_contacts_tool",
    # Action tools
    "create_contact_tool",
    "update_contact_tool",
    "delete_contact_tool",
    # Tool classes
    "SearchContactsTool",
    "ListContactsTool",
    "GetContactDetailsTool",
    "CreateContactDraftTool",
    "CreateContactDirectTool",
    "UpdateContactDraftTool",
    "UpdateContactDirectTool",
    "DeleteContactDraftTool",
    "DeleteContactDirectTool",
    # Draft execution helpers
    "execute_contact_draft",
    "execute_contact_update_draft",
    "execute_contact_delete_draft",
    # Formatters
    "ContactsFormatter",
]
