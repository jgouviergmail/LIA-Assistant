"""
Schema Registration - Register all existing tool schemas.

This module is called at application startup to populate the Tool Schema Registry
with schemas for all existing tools. It extracts schemas from formatters and
registers them with appropriate examples.

Phase 2.1 - Schema Mismatch Resolution (Issue #32)

Purpose:
    Auto-populate the schema registry at startup by:
    1. Extracting schemas from formatter classes
    2. Creating helpful reference examples
    3. Registering schemas for all tools

Architecture:
    - Called once at application startup (bootstrap.py)
    - Registers all Google Contacts tools
    - Registers all Gmail tools (future)
    - Provides reference examples for planner

Usage:
    >>> # At application startup
    >>> from src.domains.agents.tools.schema_registration import register_all_tool_schemas
    >>> register_all_tool_schemas()
    >>> # Now all tools have registered schemas

Best Practices (2025):
    - One registration point for all tools
    - Comprehensive reference examples
    - Clear documentation of expected structures
    - Defensive error handling

Author: Phase 2.1 Implementation
Created: 2025-11-23
"""

import structlog

from src.domains.agents.tools.formatters import ContactsFormatter
from src.domains.agents.tools.schema_extractor import SchemaExtractor
from src.domains.agents.tools.schema_registry import ToolSchemaRegistry

logger = structlog.get_logger(__name__)


def register_all_tool_schemas() -> None:
    """
    Register schemas for all existing tools.

    This function is called at application startup to populate the
    Tool Schema Registry with schemas for all tools in the system.

    Registered Tools:
        - Google Contacts: search_contacts_tool, get_contact_details_tool, list_contacts_tool
        - Gmail: (future - Phase 2 expansion)
        - Context Tools: (utility tools - no schemas needed)

    Side Effects:
        - Populates ToolSchemaRegistry singleton
        - Logs registration progress
        - Logs statistics on completion

    Examples:
        >>> # Called once at startup
        >>> register_all_tool_schemas()
        >>> # Check registration
        >>> registry = ToolSchemaRegistry.get_instance()
        >>> assert len(registry.list_tools()) >= 3
        >>> assert registry.has_schema("search_contacts_tool")
    """
    logger.info(
        "schema_registration_start",
        message="Starting registration of all tool schemas",
    )

    registry = ToolSchemaRegistry.get_instance()
    extractor = SchemaExtractor()

    # Register Google Contacts tools
    _register_contacts_schemas(registry, extractor)

    # Gmail tools - TODO: Implement in Phase 2 expansion
    # For now, we focus on Contacts to validate the architecture
    # _register_gmail_schemas(registry, extractor)

    # Context tools don't need schemas (utility tools, not data-producing)
    # Examples: resolve_reference, get_context_list, set_current_item

    # Log completion statistics
    stats = registry.get_stats()
    tools = registry.list_tools()

    logger.info(
        "schema_registration_complete",
        total_tools=stats["total_tools"],
        tools_with_examples=stats["tools_with_examples"],
        total_examples=stats["total_examples"],
        tools=tools,
        message=f"Registered {stats['total_tools']} tool schemas with {stats['total_examples']} examples",
    )


def _register_contacts_schemas(registry: ToolSchemaRegistry, extractor: SchemaExtractor) -> None:
    """
    Register Google Contacts tool schemas.

    Registers schemas for all Google Contacts tools:
    - search_contacts_tool: Search with query (operation="search")
    - get_contact_details_tool: Get full details (operation="details")
    - list_contacts_tool: List with pagination (operation="list")

    Args:
        registry: ToolSchemaRegistry instance
        extractor: SchemaExtractor instance

    Reference Examples:
        Each tool includes examples showing:
        - How to reference first item
        - How to reference nested fields (emailAddresses[0].value)
        - How to use wildcards for arrays (contacts[*].emailAddresses[*].value)

    Common Mistakes Prevented:
        ❌ $steps.search.emails[0].value (WRONG - field is emailAddresses)
        ✅ $steps.search.contacts[0].emailAddresses[0].value (CORRECT)

        ❌ $steps.details.results[0].email (WRONG - no results field)
        ✅ $steps.details.contacts[0].emailAddresses[0].value (CORRECT)
    """
    logger.info(
        "registering_contacts_schemas",
        message="Registering Google Contacts tool schemas",
    )

    # 1. search_contacts_tool
    # Operation: "search" - includes basic fields for search results
    # Response wraps results in "contacts" array
    search_schema = extractor.extract_from_formatter(ContactsFormatter, operation="search")

    registry.register_schema(
        "search_contacts_tool",
        search_schema,
        examples=[
            {
                "description": "Get first contact's resource name",
                "reference": "$steps.search.contacts[0].resource_name",
                "expected_type": "string",
                "note": "resource_name is always available and unique identifier",
            },
            {
                "description": "Get first contact's first email address",
                "reference": "$steps.search.contacts[0].emailAddresses[0].value",
                "expected_type": "string",
                "note": "Field is 'emailAddresses' not 'emails'",
            },
            {
                "description": "Get first contact's first phone number",
                "reference": "$steps.search.contacts[0].phoneNumbers[0].value",
                "expected_type": "string",
                "note": "Field is 'phoneNumbers' not 'phones'",
            },
            {
                "description": "Get all email addresses from all contacts",
                "reference": "$steps.search.contacts[*].emailAddresses[*].value",
                "expected_type": "array<string>",
                "note": "Use [*] wildcard to extract from all items",
            },
            {
                "description": "Get all phone numbers from all contacts",
                "reference": "$steps.search.contacts[*].phoneNumbers[*].value",
                "expected_type": "array<string>",
                "note": "Useful for batch operations",
            },
        ],
    )

    # 2. get_contact_details_tool
    # Operation: "details" - includes ALL fields for detailed view
    # Response wraps results in "contacts" array (even for single contact)
    details_schema = extractor.extract_from_formatter(ContactsFormatter, operation="details")

    registry.register_schema(
        "get_contact_details_tool",
        details_schema,
        examples=[
            {
                "description": "Get first contact's first email address",
                "reference": "$steps.get_contact_details.contacts[0].emailAddresses[0].value",
                "expected_type": "string",
                "note": "Same structure as search, but with more fields",
            },
            {
                "description": "Get first contact's organization name",
                "reference": "$steps.get_contact_details.contacts[0].organizations[0].name",
                "expected_type": "string",
                "note": "Organizations field only available in details operation",
            },
            {
                "description": "Get first contact's organization title",
                "reference": "$steps.get_contact_details.contacts[0].organizations[0].title",
                "expected_type": "string",
                "note": "Job title within organization",
            },
            {
                "description": "Get all phone numbers from first contact",
                "reference": "$steps.get_contact_details.contacts[0].phoneNumbers[*].value",
                "expected_type": "array<string>",
                "note": "Extract all phone numbers from one contact",
            },
            {
                "description": "Get first contact's birthday",
                "reference": "$steps.get_contact_details.contacts[0].birthdays[0].date",
                "expected_type": "object",
                "note": "Birthday is object with year, month, day fields",
            },
            {
                "description": "Get first contact's first address",
                "reference": "$steps.get_contact_details.contacts[0].addresses[0].formatted",
                "expected_type": "string",
                "note": "Full formatted address string",
            },
        ],
    )

    # 3. list_contacts_tool
    # Operation: "list" - minimal fields for efficient listing
    # Response wraps results in "contacts" array with pagination
    list_schema = extractor.extract_from_formatter(ContactsFormatter, operation="list")

    registry.register_schema(
        "list_contacts_tool",
        list_schema,
        examples=[
            {
                "description": "Get all contact resource names",
                "reference": "$steps.list.contacts[*].resource_name",
                "expected_type": "array<string>",
                "note": "Useful for batch operations or counting",
            },
            {
                "description": "Get first contact's name",
                "reference": "$steps.list.contacts[0].names",
                "expected_type": "string",
                "note": "Names is extracted as displayName string",
            },
            {
                "description": "Get first contact's first email",
                "reference": "$steps.list.contacts[0].emailAddresses[0].value",
                "expected_type": "string",
                "note": "Same structure as search/details",
            },
            {
                "description": "Get all names from all contacts",
                "reference": "$steps.list.contacts[*].names[*].displayName",
                "expected_type": "array<string>",
                "note": "Nested wildcard extraction",
            },
        ],
    )

    logger.info(
        "contacts_schemas_registered",
        tools_count=3,
        tools=["search_contacts_tool", "get_contact_details_tool", "list_contacts_tool"],
        message="Registered 3 Google Contacts tool schemas",
    )


def _register_gmail_schemas(registry: ToolSchemaRegistry, extractor: SchemaExtractor) -> None:
    """
    Register Gmail tool schemas.

    TODO: Implement in Phase 2 expansion.

    This will register:
    - search_emails_tool
    - get_email_details_tool
    - send_email_tool

    Args:
        registry: ToolSchemaRegistry instance
        extractor: SchemaExtractor instance

    Note:
        Currently deferred to focus on validating the architecture with Contacts tools.
        Gmail tools will follow the same pattern once ContactsFormatter validation is complete.
    """
    logger.info(
        "gmail_schemas_registration_deferred",
        message="Gmail tool schema registration deferred to Phase 2 expansion",
    )
    # TODO: Implement when EmailFormatter is ready
    pass
