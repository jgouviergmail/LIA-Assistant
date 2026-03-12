"""
Connector Preferences Module.

Provides type-safe, encrypted storage for user connector preferences.
Examples: default calendar name, default task list name.

Architecture:
    - schemas.py: Pydantic schemas for each connector type
    - registry.py: Mapping connector_type -> schema class
    - service.py: Validation, encryption, decryption, sanitization
    - resolver.py: Case-insensitive name-to-ID resolution
"""

from src.domains.connectors.preferences.registry import (
    CONNECTOR_PREFERENCES_REGISTRY,
    get_preference_schema,
    has_preferences,
)
from src.domains.connectors.preferences.resolver import (
    GoogleCalendarNameResolver,
    GoogleTasksListNameResolver,
    PreferenceNameResolver,
    ResolvedItem,
    resolve_calendar_name,
    resolve_task_list_name,
)
from src.domains.connectors.preferences.schemas import (
    BaseConnectorPreferences,
    GoogleCalendarPreferences,
    GoogleTasksPreferences,
)
from src.domains.connectors.preferences.service import ConnectorPreferencesService

__all__ = [
    # Schemas
    "BaseConnectorPreferences",
    "GoogleCalendarPreferences",
    "GoogleTasksPreferences",
    # Registry
    "CONNECTOR_PREFERENCES_REGISTRY",
    "get_preference_schema",
    "has_preferences",
    # Service
    "ConnectorPreferencesService",
    # Resolver
    "GoogleCalendarNameResolver",
    "GoogleTasksListNameResolver",
    "PreferenceNameResolver",
    "ResolvedItem",
    "resolve_calendar_name",
    "resolve_task_list_name",
]
