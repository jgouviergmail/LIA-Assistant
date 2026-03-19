"""
Connectors domain models (database entities).
Manages user connections to external services (Gmail, Drive, etc.).
"""

import enum
import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel


class ConnectorStatus(str, enum.Enum):
    """Connector status enum."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"
    ERROR = "error"


class ConnectorType(str, enum.Enum):
    """Connector type enum."""

    # Google services (OAuth)
    GOOGLE_GMAIL = "google_gmail"
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_CONTACTS = "google_contacts"
    GOOGLE_TASKS = "google_tasks"

    # Apple iCloud services (App-Specific Password)
    APPLE_EMAIL = "apple_email"
    APPLE_CALENDAR = "apple_calendar"
    APPLE_CONTACTS = "apple_contacts"

    # Microsoft 365 services (OAuth via Microsoft Entra ID)
    MICROSOFT_OUTLOOK = "microsoft_outlook"
    MICROSOFT_CALENDAR = "microsoft_calendar"
    MICROSOFT_CONTACTS = "microsoft_contacts"
    MICROSOFT_TASKS = "microsoft_tasks"

    # Google services (API Key - global key, not per-user)
    GOOGLE_ROUTES = "google_routes"
    GOOGLE_PLACES = "google_places"  # Uses global GOOGLE_API_KEY

    # External API services (API Key)
    OPENWEATHERMAP = "openweathermap"
    WIKIPEDIA = "wikipedia"
    PERPLEXITY = "perplexity"
    BRAVE_SEARCH = "brave_search"
    BROWSER = "browser"  # Interactive web browsing (evolution F7)

    # Legacy (deprecated - use GOOGLE_GMAIL instead)
    GMAIL = "gmail"

    # Future connectors
    SLACK = "slack"
    NOTION = "notion"
    GITHUB = "github"

    @property
    def is_oauth(self) -> bool:
        """
        Check if this connector type uses OAuth authentication.

        Returns:
            True if OAuth-based (requires user consent flow and token refresh),
            False if API key-based or no authentication needed.
        """
        return self in _OAUTH_CONNECTOR_TYPES

    @property
    def is_apple(self) -> bool:
        """
        Check if this connector type uses Apple iCloud authentication.

        Returns:
            True if Apple iCloud (uses Apple ID + app-specific password),
            False otherwise.
        """
        return self in _APPLE_CONNECTOR_TYPES

    @property
    def is_google(self) -> bool:
        """
        Check if this connector type is a Google service.

        Returns:
            True if Google OAuth service, False otherwise.
        """
        return self in _GOOGLE_CONNECTOR_TYPES

    @property
    def is_microsoft(self) -> bool:
        """
        Check if this connector type is a Microsoft 365 service.

        Returns:
            True if Microsoft OAuth service, False otherwise.
        """
        return self in _MICROSOFT_CONNECTOR_TYPES

    @classmethod
    def get_oauth_types(cls) -> frozenset["ConnectorType"]:
        """
        Get all OAuth-based connector types.

        Returns:
            Frozenset of connector types that use OAuth authentication.
        """
        return _OAUTH_CONNECTOR_TYPES

    @classmethod
    def get_apple_types(cls) -> frozenset["ConnectorType"]:
        """
        Get all Apple iCloud connector types.

        Returns:
            Frozenset of connector types that use Apple authentication.
        """
        return _APPLE_CONNECTOR_TYPES

    @classmethod
    def get_google_types(cls) -> frozenset["ConnectorType"]:
        """Get all Google OAuth connector types."""
        return _GOOGLE_CONNECTOR_TYPES

    @classmethod
    def get_microsoft_types(cls) -> frozenset["ConnectorType"]:
        """Get all Microsoft 365 connector types."""
        return _MICROSOFT_CONNECTOR_TYPES


# Google OAuth connector types (defined after enum to avoid forward reference)
_GOOGLE_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    {
        ConnectorType.GOOGLE_GMAIL,
        ConnectorType.GOOGLE_CALENDAR,
        ConnectorType.GOOGLE_DRIVE,
        ConnectorType.GOOGLE_CONTACTS,
        ConnectorType.GOOGLE_TASKS,
    }
)

# Microsoft 365 OAuth connector types
_MICROSOFT_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    {
        ConnectorType.MICROSOFT_OUTLOOK,
        ConnectorType.MICROSOFT_CALENDAR,
        ConnectorType.MICROSOFT_CONTACTS,
        ConnectorType.MICROSOFT_TASKS,
    }
)

# All OAuth connector types (Google + Microsoft + legacy)
# These connectors require user OAuth consent and periodic token refresh
_OAUTH_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    _GOOGLE_CONNECTOR_TYPES
    | _MICROSOFT_CONNECTOR_TYPES
    | {ConnectorType.GMAIL}  # Legacy type (deprecated, use GOOGLE_GMAIL)
)

# Apple iCloud connector types (defined after enum to avoid forward reference)
# These connectors use Apple ID + app-specific password (no OAuth)
_APPLE_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    {
        ConnectorType.APPLE_EMAIL,
        ConnectorType.APPLE_CALENDAR,
        ConnectorType.APPLE_CONTACTS,
    }
)

# Functional categories for mutual exclusivity
# Only ONE connector per category can be ACTIVE at a time for a given user.
CONNECTOR_FUNCTIONAL_CATEGORIES: dict[str, frozenset[ConnectorType]] = {
    "email": frozenset(
        {ConnectorType.GOOGLE_GMAIL, ConnectorType.APPLE_EMAIL, ConnectorType.MICROSOFT_OUTLOOK}
    ),
    "calendar": frozenset(
        {
            ConnectorType.GOOGLE_CALENDAR,
            ConnectorType.APPLE_CALENDAR,
            ConnectorType.MICROSOFT_CALENDAR,
        }
    ),
    "contacts": frozenset(
        {
            ConnectorType.GOOGLE_CONTACTS,
            ConnectorType.APPLE_CONTACTS,
            ConnectorType.MICROSOFT_CONTACTS,
        }
    ),
    "tasks": frozenset({ConnectorType.GOOGLE_TASKS, ConnectorType.MICROSOFT_TASKS}),
}

# Display names for functional categories (used in error messages).
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "email": "Email",
    "calendar": "Calendar",
    "contacts": "Contacts",
    "tasks": "Tasks",
}


def get_functional_category(connector_type: ConnectorType) -> str | None:
    """
    Get the functional category of a connector type.

    Args:
        connector_type: The connector type to look up.

    Returns:
        Category name ("email", "calendar", "contacts", "tasks")
        or None if not categorized.
    """
    for category, types in CONNECTOR_FUNCTIONAL_CATEGORIES.items():
        if connector_type in types:
            return category
    return None


def get_conflicting_connector_types(connector_type: ConnectorType) -> frozenset[ConnectorType]:
    """
    Get ALL mutually exclusive connector types for the given type.

    Args:
        connector_type: The connector type to find conflicts for.

    Returns:
        Frozenset of conflicting ConnectorTypes (e.g., {APPLE_EMAIL, MICROSOFT_OUTLOOK}
        for GOOGLE_GMAIL), or empty frozenset if no mutual exclusivity applies.
    """
    category = get_functional_category(connector_type)
    if category is None:
        return frozenset()
    return frozenset(ct for ct in CONNECTOR_FUNCTIONAL_CATEGORIES[category] if ct != connector_type)


def get_conflicting_connector_type(connector_type: ConnectorType) -> ConnectorType | None:
    """
    Get a mutually exclusive connector type that conflicts with the given type.

    .. deprecated::
        Use :func:`get_conflicting_connector_types` (plural) instead for N-way exclusivity.

    Returns:
        A conflicting ConnectorType, or None if no mutual exclusivity applies.
    """
    conflicting = get_conflicting_connector_types(connector_type)
    return next(iter(conflicting), None)


# Display names for connectors (used in notifications and UI)
# Maps ConnectorType to human-readable name
CONNECTOR_DISPLAY_NAMES: dict[ConnectorType, str] = {
    ConnectorType.GOOGLE_GMAIL: "Gmail",
    ConnectorType.GOOGLE_CALENDAR: "Google Calendar",
    ConnectorType.GOOGLE_DRIVE: "Google Drive",
    ConnectorType.GOOGLE_CONTACTS: "Google Contacts",
    ConnectorType.GOOGLE_TASKS: "Google Tasks",
    ConnectorType.GOOGLE_PLACES: "Google Places",
    ConnectorType.GOOGLE_ROUTES: "Google Routes",
    ConnectorType.APPLE_EMAIL: "Apple Mail",
    ConnectorType.APPLE_CALENDAR: "Apple Calendar",
    ConnectorType.APPLE_CONTACTS: "Apple Contacts",
    ConnectorType.MICROSOFT_OUTLOOK: "Microsoft Outlook",
    ConnectorType.MICROSOFT_CALENDAR: "Microsoft Calendar",
    ConnectorType.MICROSOFT_CONTACTS: "Microsoft Contacts",
    ConnectorType.MICROSOFT_TASKS: "Microsoft To Do",
    ConnectorType.OPENWEATHERMAP: "OpenWeatherMap",
    ConnectorType.WIKIPEDIA: "Wikipedia",
    ConnectorType.PERPLEXITY: "Perplexity",
    ConnectorType.BRAVE_SEARCH: "Brave Search",
    ConnectorType.BROWSER: "Browser",
    ConnectorType.GMAIL: "Gmail",  # Legacy
    ConnectorType.SLACK: "Slack",
    ConnectorType.NOTION: "Notion",
    ConnectorType.GITHUB: "GitHub",
}


def get_connector_display_name(connector_type: ConnectorType) -> str:
    """
    Get the display name for a connector type.

    Args:
        connector_type: The connector type enum value.

    Returns:
        Human-readable display name, or the enum value if not mapped.
    """
    return CONNECTOR_DISPLAY_NAMES.get(connector_type, connector_type.value)


# OAuth authorize route paths (maps ConnectorType to API route path)
# These paths are relative to /api/v1/connectors prefix
# Used by health check to generate correct authorize_url for reconnection
CONNECTOR_AUTHORIZE_PATHS: dict[ConnectorType, str] = {
    ConnectorType.GOOGLE_GMAIL: "/gmail/authorize",
    ConnectorType.GOOGLE_CALENDAR: "/google-calendar/authorize",
    ConnectorType.GOOGLE_DRIVE: "/google-drive/authorize",
    ConnectorType.GOOGLE_CONTACTS: "/google-contacts/authorize",
    ConnectorType.GOOGLE_TASKS: "/google-tasks/authorize",
    ConnectorType.GMAIL: "/gmail/authorize",  # Legacy type (uses same route)
    ConnectorType.MICROSOFT_OUTLOOK: "/microsoft-outlook/authorize",
    ConnectorType.MICROSOFT_CALENDAR: "/microsoft-calendar/authorize",
    ConnectorType.MICROSOFT_CONTACTS: "/microsoft-contacts/authorize",
    ConnectorType.MICROSOFT_TASKS: "/microsoft-tasks/authorize",
}


def get_connector_authorize_path(connector_type: ConnectorType) -> str | None:
    """
    Get the OAuth authorize API route path for a connector type.

    Args:
        connector_type: The connector type enum value.

    Returns:
        API route path for OAuth authorization (e.g., "/gmail/authorize"),
        or None if connector doesn't support OAuth.
    """
    return CONNECTOR_AUTHORIZE_PATHS.get(connector_type)


class Connector(BaseModel):
    """
    Connector model for user external service connections.
    Stores encrypted OAuth tokens and connector metadata.
    """

    __tablename__ = "connectors"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(ConnectorType, native_enum=False, length=50),
        nullable=False,
        index=True,
    )
    status: Mapped[ConnectorStatus] = mapped_column(
        Enum(ConnectorStatus, native_enum=False),
        nullable=False,
        default=ConnectorStatus.ACTIVE,
    )

    # OAuth scopes granted by user (stored as JSON array)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Encrypted credentials (access_token, refresh_token, etc.)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Additional connector-specific metadata (attribute name is connector_metadata, DB column is 'metadata')
    connector_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )

    # Encrypted user preferences (calendar names, task lists, etc.)
    # Same encryption pattern as credentials_encrypted
    preferences_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="connectors")

    def __repr__(self) -> str:
        return f"<Connector(id={self.id}, user_id={self.user_id}, type={self.connector_type}, status={self.status})>"


class ConnectorGlobalConfig(BaseModel):
    """
    Global configuration for connector types.
    Allows admins to enable/disable connector types for the entire application.
    """

    __tablename__ = "connector_global_config"

    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(ConnectorType, native_enum=False),
        unique=True,
        nullable=False,
        index=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ConnectorGlobalConfig(type={self.connector_type}, enabled={self.is_enabled})>"
