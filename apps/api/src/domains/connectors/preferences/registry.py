"""
Registry mapping connector types to their preference schemas.

This registry enables:
    - Type-safe preference validation per connector
    - Easy extension for new connector types
    - Runtime schema lookup for API endpoints
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.schemas import (
    AppleCalendarPreferences,
    BaseConnectorPreferences,
    GoogleCalendarPreferences,
    GoogleTasksPreferences,
    MicrosoftCalendarPreferences,
    MicrosoftTasksPreferences,
)

if TYPE_CHECKING:
    pass

# Registry of connector types that support preferences
# Maps connector_type string -> Pydantic schema class
CONNECTOR_PREFERENCES_REGISTRY: dict[str, type[BaseConnectorPreferences]] = {
    ConnectorType.GOOGLE_CALENDAR.value: GoogleCalendarPreferences,
    ConnectorType.GOOGLE_TASKS.value: GoogleTasksPreferences,
    ConnectorType.APPLE_CALENDAR.value: AppleCalendarPreferences,
    ConnectorType.MICROSOFT_CALENDAR.value: MicrosoftCalendarPreferences,
    ConnectorType.MICROSOFT_TASKS.value: MicrosoftTasksPreferences,
}


def get_preference_schema(connector_type: str) -> type[BaseConnectorPreferences] | None:
    """
    Get the preference schema class for a connector type.

    Args:
        connector_type: Connector type string (e.g., "google_calendar")

    Returns:
        Schema class if connector supports preferences, None otherwise
    """
    return CONNECTOR_PREFERENCES_REGISTRY.get(connector_type)


def has_preferences(connector_type: str) -> bool:
    """
    Check if a connector type supports user preferences.

    Args:
        connector_type: Connector type string

    Returns:
        True if connector supports preferences, False otherwise
    """
    return connector_type in CONNECTOR_PREFERENCES_REGISTRY
