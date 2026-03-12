"""
Domain Constants for Planning Strategies.

This module contains shared domain mappings used by planning strategies
for bypassing LLM and creating direct plans from resolved references.
"""

# Mapping from domain to unified GET tool name
# These tools handle search, list, and detail operations in one tool
DOMAIN_GET_TOOLS = {
    "contacts": "get_contacts_tool",
    "emails": "get_emails_tool",
    "events": "get_events_tool",
    "drive": "get_files_tool",
    "tasks": "get_tasks_tool",
    "places": "get_places_tool",
}

# Mapping from domain to ID field names in resolved items
# Multiple field names per domain (try in order)
DOMAIN_ID_FIELDS = {
    "contacts": ["resourceName", "resource_name", "_registry_id"],
    "emails": ["id", "message_id", "_registry_id"],
    "events": ["id", "event_id", "_registry_id"],
    "drive": ["id", "file_id", "_registry_id"],
    "tasks": ["id", "task_id", "_registry_id"],
    "places": ["place_id", "_registry_id"],
}

# Mapping from domain to parameter name for single item mode
DOMAIN_PARAM_NAMES = {
    "contacts": "resource_name",
    "emails": "message_id",
    "events": "event_id",
    "drive": "file_id",
    "tasks": "task_id",
    "places": "place_id",
}

# Mapping from domain to batch parameter name for multiple items
# Multi-ordinal fix (2026-01-01): Handle "first and second", "all three"
DOMAIN_BATCH_PARAM_NAMES = {
    "contacts": "resource_names",  # Already supports batch
    "emails": "message_ids",
    "events": "event_ids",
    "drive": "file_ids",
    "tasks": "task_ids",
    "places": "place_ids",
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
