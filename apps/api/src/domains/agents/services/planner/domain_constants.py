"""
Domain Constants for Planning Strategies.

This module contains shared domain mappings used by planning strategies
for bypassing LLM and creating direct plans from resolved references.

Keys use SINGULAR domain names from DOMAIN_REGISTRY (e.g., "contact", "email")
to match source_domain convention in QueryIntelligence and ResolvedContext.

FIX 2026-04: Changed from plural keys ("contacts", "emails") to singular ("contact",
"email") to match source_domain from routing_history which uses DOMAIN_REGISTRY names.
Also renamed "drive" → "file" to match DOMAIN_REGISTRY key.
"""

# Mapping from domain to unified GET tool name
# These tools handle search, list, and detail operations in one tool
DOMAIN_GET_TOOLS = {
    "contact": "get_contacts_tool",
    "email": "get_emails_tool",
    "event": "get_events_tool",
    "file": "get_files_tool",
    "task": "get_tasks_tool",
    "place": "get_places_tool",
}

# Mapping from domain to ID field names in resolved items
# Multiple field names per domain (try in order)
DOMAIN_ID_FIELDS = {
    "contact": ["resourceName", "resource_name", "_registry_id"],
    "email": ["id", "message_id", "_registry_id"],
    "event": ["id", "event_id", "_registry_id"],
    "file": ["id", "file_id", "_registry_id"],
    "task": ["id", "task_id", "_registry_id"],
    "place": ["place_id", "_registry_id"],
}

# Mapping from domain to parameter name for single item mode
DOMAIN_PARAM_NAMES = {
    "contact": "resource_name",
    "email": "message_id",
    "event": "event_id",
    "file": "file_id",
    "task": "task_id",
    "place": "place_id",
}

# Mapping from domain to batch parameter name for multiple items
# Multi-ordinal fix (2026-01-01): Handle "first and second", "all three"
DOMAIN_BATCH_PARAM_NAMES = {
    "contact": "resource_names",
    "email": "message_ids",
    "event": "event_ids",
    "file": "file_ids",
    "task": "task_ids",
    "place": "place_ids",
}

# Cross-domain bypass mappings
# Maps source field → (target_domain, target_tool, target_param)
# Example: event.location → search places
CROSS_DOMAIN_MAPPINGS: dict[str, tuple[str, str, str]] = {
    "location": ("places", "get_places_tool", "query"),
    "address": ("places", "get_places_tool", "query"),
    # Future: email → contacts, attendees → contacts, etc.
}


__all__ = [
    "DOMAIN_GET_TOOLS",
    "DOMAIN_ID_FIELDS",
    "DOMAIN_PARAM_NAMES",
    "DOMAIN_BATCH_PARAM_NAMES",
    "CROSS_DOMAIN_MAPPINGS",
]
