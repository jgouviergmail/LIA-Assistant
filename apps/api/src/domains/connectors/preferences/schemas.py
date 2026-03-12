"""
Pydantic schemas for connector preferences.

Each connector type that supports user preferences has its own schema class.
All schemas inherit from BaseConnectorPreferences for type safety.

Security:
    - max_length=100 prevents excessive data storage
    - extra="forbid" rejects unknown fields
    - Values are sanitized before encryption (see service.py)
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class BaseConnectorPreferences(BaseModel):
    """
    Base class for connector preferences.

    All connector-specific preference schemas must inherit from this class.
    Provides common configuration and type hints.
    """

    connector_type: ClassVar[str]

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class GoogleCalendarPreferences(BaseConnectorPreferences):
    """
    Preferences for Google Calendar connector.

    Attributes:
        default_calendar_name: Name of the default calendar for creating events.
            Initialized with the user's Gmail address during connector creation.
            If not set, the system falls back to the user's primary Google calendar.
    """

    connector_type: ClassVar[str] = "google_calendar"

    default_calendar_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom du calendrier par defaut pour creer les evenements",
    )


class GoogleTasksPreferences(BaseConnectorPreferences):
    """
    Preferences for Google Tasks connector.

    Attributes:
        default_task_list_name: Name of the default task list.
            If not set, the agent uses the user's primary task list.
    """

    connector_type: ClassVar[str] = "google_tasks"

    default_task_list_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom de la liste de taches par defaut",
    )


class AppleCalendarPreferences(BaseConnectorPreferences):
    """
    Preferences for Apple Calendar connector.

    Attributes:
        default_calendar_name: Name of the default calendar for creating events.
            If not set, the system falls back to "primary".
    """

    connector_type: ClassVar[str] = "apple_calendar"

    default_calendar_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom du calendrier par defaut pour creer les evenements",
    )


class MicrosoftCalendarPreferences(BaseConnectorPreferences):
    """
    Preferences for Microsoft Calendar connector.

    Attributes:
        default_calendar_name: Name of the default calendar for creating events.
            If not set, the system falls back to "primary".
    """

    connector_type: ClassVar[str] = "microsoft_calendar"

    default_calendar_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom du calendrier par defaut pour creer les evenements",
    )


class MicrosoftTasksPreferences(BaseConnectorPreferences):
    """
    Preferences for Microsoft To Do connector.

    Attributes:
        default_task_list_name: Name of the default task list.
            If not set, the agent uses the first available task list.
    """

    connector_type: ClassVar[str] = "microsoft_tasks"

    default_task_list_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom de la liste de taches par defaut",
    )


class PreferencesRequest(BaseModel):
    """
    Router-level validation schema for connector preferences.

    Accepts all valid preference fields from all connector types.
    Fields are optional since different connector types use different fields.
    The service layer validates that required fields for the specific connector type are present.

    Security:
        - extra="forbid" rejects unknown/arbitrary fields at router level
        - Prevents injection of unexpected data before service validation
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    # Google Calendar preferences
    default_calendar_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom du calendrier par defaut (Google Calendar)",
    )

    # Google Tasks preferences
    default_task_list_name: str | None = Field(
        default=None,
        max_length=100,
        description="Nom de la liste de taches par defaut (Google Tasks)",
    )
