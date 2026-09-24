"""
Connectors domain models (database entities).
Manages user connections to external services (Gmail, Drive, etc.).
"""

import enum
import uuid
from contextlib import suppress
from typing import Any

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
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
    GOOGLE_WEATHER = "google_weather"  # Weather API (lot E, global key)
    GOOGLE_ENVIRONMENT = "google_environment"  # Air Quality + Pollen (lot E, global key)

    # External API services (API Key)
    OPENWEATHERMAP = "openweathermap"
    WIKIPEDIA = "wikipedia"
    PERPLEXITY = "perplexity"
    BRAVE_SEARCH = "brave_search"
    BROWSER = "browser"  # Interactive web browsing (evolution F7)

    # Smart Home
    PHILIPS_HUE = "philips_hue"

    # Telephony (API Key - per-user ElevenLabs account for agentic outbound calls)
    ELEVENLABS_TELEPHONY = "elevenlabs_telephony"

    # Live (API Key - per-user provider account for the duplex voice mode, ADR-299).
    # The ``live`` category is ADDITIVE (wave 2 spec A10): every provider key may
    # be active, the person chooses which one a session opens on. The key is the
    # person's own, which is what keeps the live tokens off LIA's ledger.
    GEMINI_LIVE = "gemini_live"
    GPT_LIVE = "gpt_live"
    ELEVENLABS_LIVE = "elevenlabs_live"

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

    @property
    def is_hue(self) -> bool:
        """
        Check if this connector type is a Philips Hue service.

        Returns:
            True if Philips Hue smart home connector, False otherwise.
        """
        return self in _HUE_CONNECTOR_TYPES

    @property
    def uses_global_api_key(self) -> bool:
        """
        Check if this connector type uses the platform GOOGLE_API_KEY.

        Platform-key connectors have no per-user credentials: the user simply
        toggles them on. Lets a functional category mix a user-key provider
        (OpenWeatherMap) with a platform-key one (Google Weather) — the
        ConnectorTool base picks the credentials path from the RESOLVED type.

        Returns:
            True when the client authenticates with the global API key.
        """
        return self in _GLOBAL_API_KEY_CONNECTOR_TYPES

    @property
    def is_keyless(self) -> bool:
        """
        Check if this connector type asks NOTHING of the person to activate.

        A keyless connector needs no OAuth consent and no per-user key (the
        platform key or no key at all), so it belongs to the INSTANCE, not to
        the account: whether it serves someone is decided by
        ``connectors/keyless.py`` alone, no per-account row exists, and the
        settings never offer it (ADR-307) — a test keeps it off the frontend's
        activation list.

        Returns:
            True when the service asks nothing of the person.
        """
        return self in _KEYLESS_USER_CONNECTOR_TYPES

    @classmethod
    def get_keyless_types(cls) -> frozenset[ConnectorType]:
        """Get the connector types the instance provides to every account (ADR-307)."""
        return _KEYLESS_USER_CONNECTOR_TYPES

    @classmethod
    def get_oauth_types(cls) -> frozenset[ConnectorType]:
        """
        Get all OAuth-based connector types.

        Returns:
            Frozenset of connector types that use OAuth authentication.
        """
        return _OAUTH_CONNECTOR_TYPES

    @classmethod
    def get_apple_types(cls) -> frozenset[ConnectorType]:
        """
        Get all Apple iCloud connector types.

        Returns:
            Frozenset of connector types that use Apple authentication.
        """
        return _APPLE_CONNECTOR_TYPES

    @classmethod
    def get_google_types(cls) -> frozenset[ConnectorType]:
        """Get all Google OAuth connector types."""
        return _GOOGLE_CONNECTOR_TYPES

    @classmethod
    def get_microsoft_types(cls) -> frozenset[ConnectorType]:
        """Get all Microsoft 365 connector types."""
        return _MICROSOFT_CONNECTOR_TYPES

    @classmethod
    def get_hue_types(cls) -> frozenset[ConnectorType]:
        """Get all Philips Hue connector types."""
        return _HUE_CONNECTOR_TYPES


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

# Philips Hue connector types (Smart Home)
# These connectors use a hybrid auth model (local: press-link API key, remote: OAuth2)
_HUE_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset({ConnectorType.PHILIPS_HUE})

# Platform-key connectors: authenticate with the global GOOGLE_API_KEY,
# activation is a simple user toggle (no per-user credentials).
_GLOBAL_API_KEY_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    {
        ConnectorType.GOOGLE_ROUTES,
        ConnectorType.GOOGLE_PLACES,
        ConnectorType.GOOGLE_WEATHER,
        ConnectorType.GOOGLE_ENVIRONMENT,
    }
)

# Keyless user connectors: nothing asked of the person, so the INSTANCE decides
# whether they serve an account (`connectors/keyless.py`, ADR-307) and no
# per-account row exists. The platform-key types a tool gates on (Routes is not
# one — its tools read the platform key directly) plus the two free services.
# A test keeps every one of them off the frontend's activation list.
_KEYLESS_USER_CONNECTOR_TYPES: frozenset[ConnectorType] = frozenset(
    {
        ConnectorType.WIKIPEDIA,
        ConnectorType.BROWSER,
        ConnectorType.GOOGLE_PLACES,
        ConnectorType.GOOGLE_WEATHER,
        ConnectorType.GOOGLE_ENVIRONMENT,
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
    # Weather (lot E, 2026-08): OpenWeatherMap (personal key) vs Google Weather
    # (keyless, the instance's DEFAULT — ADR-307): the provider the person
    # configured wins, Google Weather answers when they configured none. AQ and
    # pollen (GOOGLE_ENVIRONMENT) stay OUT of the category on purpose — they
    # are platform services independent of the weather provider choice.
    "weather": frozenset({ConnectorType.OPENWEATHERMAP, ConnectorType.GOOGLE_WEATHER}),
    "smart_home": frozenset({ConnectorType.PHILIPS_HUE}),
    # Single-member category today: gives telephony its own UI grouping and leaves
    # room for alternative providers later. No mutual-exclusivity effect while alone.
    "telephony": frozenset({ConnectorType.ELEVENLABS_TELEPHONY}),
    # Live voice mode (ADR-299): a category for the UI grouping and the
    # capability's own reading — ADDITIVE (below): two provider keys may be
    # active at once, the person chooses which one a session opens on.
    "live": frozenset(
        {ConnectorType.GEMINI_LIVE, ConnectorType.GPT_LIVE, ConnectorType.ELEVENLABS_LIVE}
    ),
}

#: Categories whose members may ALL be active at once (wave 2 spec A10): the
#: doctrine « one active provider per category » is for data sources, where
#: two mailboxes would answer one question twice; a live voice on the person's
#: own key is a choice per session, not a source. A category listed here must
#: exist above — a guard holds the two tables together.
CONNECTOR_ADDITIVE_CATEGORIES: frozenset[str] = frozenset({"live"})

# Display names for functional categories (used in error messages).
CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "email": "Email",
    "calendar": "Calendar",
    "contacts": "Contacts",
    "tasks": "Tasks",
    "weather": "Weather",
    "smart_home": "Smart Home",
    "telephony": "Telephony",
    "live": "Live",
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
    if category is None or category in CONNECTOR_ADDITIVE_CATEGORIES:
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
    ConnectorType.PHILIPS_HUE: "Philips Hue",
    ConnectorType.ELEVENLABS_TELEPHONY: "Telephony",
    ConnectorType.GEMINI_LIVE: "Live (Gemini)",
    ConnectorType.GPT_LIVE: "Live (OpenAI)",
    ConnectorType.ELEVENLABS_LIVE: "Live (ElevenLabs)",
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


class OAuthGrant(BaseModel):
    """One encrypted provider grant owned by one LIA user and provider account."""

    __tablename__ = "oauth_grants"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "provider", "client_id", "subject", name="uq_oauth_grants_account"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    connectors: Mapped[list[Connector]] = relationship(back_populates="oauth_grant")


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
        index=True,
    )

    # OAuth scopes granted by user (stored as JSON array)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Encrypted credentials (access_token, refresh_token, etc.)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)

    # Null for legacy per-service credentials and non-OAuth connectors.
    oauth_grant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("oauth_grants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    oauth_grant: Mapped[OAuthGrant | None] = relationship(back_populates="connectors")

    # Additional connector-specific metadata (attribute name is connector_metadata, DB column is 'metadata')
    # CONVENTION: never mutate JSONB columns in place (update()/[]=) — SQLAlchemy
    # silently skips the UPDATE. Reassign a NEW dict: obj.connector_metadata =
    # {**(obj.connector_metadata or {}), **updates}. Enforced by
    # tests/unit/test_jsonb_mutation_guard.py.
    connector_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )

    # Encrypted user preferences (calendar names, task lists, etc.)
    # Same encryption pattern as credentials_encrypted
    preferences_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Relationships
    user: Mapped[User] = relationship(back_populates="connectors")

    def __repr__(self) -> str:
        return f"<Connector(id={self.id}, user_id={self.user_id}, type={self.connector_type}, status={self.status})>"


# SQLAlchemy event listeners: track new connector activations (dashboard 10).
# Fire automatically on any INSERT, regardless of which service method
# created the Connector. The duration covers the time from SQL flush to
# persistence completion — effectively the INSERT latency.
from sqlalchemy import event as _sa_event  # noqa: E402
from sqlalchemy.engine import Connection as _SAConnection  # noqa: E402
from sqlalchemy.orm import Mapper as _SAMapper  # noqa: E402


@_sa_event.listens_for(Connector, "before_insert")
def _mark_connector_activation_start(
    mapper: _SAMapper, connection: _SAConnection, target: Connector
) -> None:
    """Stamp the activation start timestamp before INSERT.

    Args:
        mapper: SQLAlchemy mapper (unused).
        connection: Active SQL connection (unused).
        target: Connector instance about to be inserted.
    """
    del mapper, connection  # unused
    # metrics must never break the INSERT
    with suppress(Exception):
        import time as _time

        # Per-instance attribute avoids interfering with the SQLAlchemy session.
        target.__dict__["_obs_activation_start"] = _time.perf_counter()


@_sa_event.listens_for(Connector, "after_insert")
def _track_connector_activation(
    mapper: _SAMapper, connection: _SAConnection, target: Connector
) -> None:
    """Emit activation counter + duration histogram after INSERT.

    Args:
        mapper: SQLAlchemy mapper (unused).
        connection: Active SQL connection (unused).
        target: Connector instance that was just inserted.
    """
    del mapper, connection  # unused
    # metrics must never break the INSERT
    with suppress(Exception):
        import time as _time

        from src.infrastructure.observability.metrics_oauth import (
            oauth_connector_activation_duration_seconds,
            oauth_connector_activation_total,
        )

        connector_type_value = target.connector_type.value
        status = "success" if target.status == ConnectorStatus.ACTIVE else "pending"
        oauth_connector_activation_total.labels(
            connector_type=connector_type_value,
            status=status,
        ).inc()

        _start = target.__dict__.get("_obs_activation_start")
        if _start is not None:
            oauth_connector_activation_duration_seconds.labels(
                connector_type=connector_type_value
            ).observe(_time.perf_counter() - _start)


class ConnectorGlobalConfig(BaseModel):
    """
    Global configuration for connector types.
    Allows admins to enable/disable connector types for the entire application.
    """

    __tablename__ = "connector_global_config"

    connector_type: Mapped[ConnectorType] = mapped_column(
        Enum(ConnectorType, native_enum=False, length=50),
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # One row per connector type (enforced by the constraint; its backing unique
    # index also serves connector_type lookups).
    __table_args__ = (
        UniqueConstraint("connector_type", name="uq_connector_global_config_connector_type"),
    )

    def __repr__(self) -> str:
        return f"<ConnectorGlobalConfig(type={self.connector_type}, enabled={self.is_enabled})>"
