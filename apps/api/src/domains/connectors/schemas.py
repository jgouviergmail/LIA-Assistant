"""
Connectors domain schemas (Pydantic models for API).
"""

import re
from datetime import datetime
from enum import Enum
from ipaddress import IPv4Address, ip_address
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from src.domains.connectors.models import ConnectorStatus, ConnectorType


class ConnectorCreate(BaseModel):
    """Schema for creating a connector (base)."""

    connector_type: ConnectorType = Field(..., description="Type of connector")
    scopes: list[str] = Field(..., description="OAuth scopes to request")


class ConnectorResponse(BaseModel):
    """
    Schema for connector response.

    Attributes:
        metadata: Optional connector-specific metadata. Valid keys by connector type:
            - google_calendar: {"email": str, "calendar_id": str}
            - google_tasks: {"email": str}
            - google_contacts: {"email": str, "total_contacts": int}
            - google_gmail: {"email": str}
            - openai: {"model": str}
            - weather: {"provider": str}
    """

    id: UUID = Field(..., description="Connector ID")
    user_id: UUID = Field(..., description="User ID")
    connector_type: ConnectorType = Field(..., description="Connector type")
    status: ConnectorStatus = Field(..., description="Connector status")
    scopes: list[str] = Field(..., description="Granted OAuth scopes")
    metadata: dict[str, Any] | None = Field(
        None,
        description="Connector-specific metadata (email, calendar_id, etc.)",
        validation_alias="connector_metadata",
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class ConnectorListResponse(BaseModel):
    """Schema for list of connectors."""

    connectors: list[ConnectorResponse] = Field(..., description="List of connectors")
    total: int = Field(..., description="Total number of connectors")


class ConnectorOAuthInitiate(BaseModel):
    """Schema for OAuth initiation response."""

    authorization_url: str = Field(..., description="OAuth authorization URL")
    state: str = Field(..., description="CSRF state token")


class ConnectorUpdate(BaseModel):
    """Schema for updating a connector."""

    status: ConnectorStatus | None = Field(None, description="New connector status")
    metadata: dict[str, Any] | None = Field(None, description="Updated metadata")


class ConnectorCredentials(BaseModel):
    """Internal schema for decrypted connector credentials (not exposed via API)."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None


# ========== API KEY CREDENTIALS ==========


class APIKeyCredentials(BaseModel):
    """
    Internal schema for API Key-based credentials (not exposed via API).

    Used for connectors that authenticate via API key instead of OAuth.
    The api_key is stored encrypted in the database.
    """

    api_key: str = Field(..., description="API key for authentication")
    api_secret: str | None = Field(
        None, description="Optional API secret (for APIs requiring key+secret)"
    )
    key_name: str | None = Field(None, description="User-defined name for this key")
    expires_at: datetime | None = Field(None, description="Optional expiration date for the key")


class APIKeyActivationRequest(BaseModel):
    """
    Request schema for activating an API Key connector.

    Frontend sends this to activate a connector with an API key.
    The key will be encrypted before storage.
    """

    api_key: str = Field(
        ...,
        min_length=8,
        max_length=512,
        description="API key for the service",
    )
    api_secret: str | None = Field(
        None,
        max_length=512,
        description="Optional API secret (if required by the service)",
    )
    key_name: str | None = Field(
        None,
        max_length=100,
        description="User-defined name for this key (e.g., 'Production Key')",
    )
    connector_type: ConnectorType = Field(
        ...,
        description="Type of connector to activate",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str) -> str:
        """Validate API key format and strip whitespace."""
        v = v.strip()
        if not v:
            raise ValueError("API key cannot be empty")
        # Check for obviously invalid patterns
        if v.startswith("your_") or v == "api_key_here":
            raise ValueError("Please enter a valid API key")
        return v


class APIKeyValidationRequest(BaseModel):
    """Request schema for validating an API key before activation."""

    api_key: str = Field(..., min_length=8, description="API key to validate")
    api_secret: str | None = Field(None, description="Optional API secret")
    connector_type: ConnectorType = Field(..., description="Connector type for validation")


class APIKeyValidationResponse(BaseModel):
    """Response schema for API key validation."""

    is_valid: bool = Field(..., description="Whether the API key is valid")
    message: str = Field(..., description="Validation result message")
    masked_key: str = Field(..., description="Masked version of the key for display")
    expires_at: datetime | None = Field(None, description="Key expiration if detected")


class ConnectorAPIKeyInfo(BaseModel):
    """
    Public information about an API key connector (safe to expose).

    Does NOT include the actual key, only metadata.
    """

    key_name: str | None = Field(None, description="User-defined key name")
    masked_key: str = Field(..., description="Masked key (e.g., 'sk-a...xyz')")
    has_secret: bool = Field(..., description="Whether a secret is also configured")
    expires_at: datetime | None = Field(None, description="Key expiration date")
    created_at: datetime = Field(..., description="When the key was added")
    last_used_at: datetime | None = Field(None, description="Last time the key was used")


# ========== GOOGLE CONTACTS ==========

# Google Contacts scopes - Full read/write access
GOOGLE_CONTACTS_SCOPES = [
    "https://www.googleapis.com/auth/contacts",  # Read/write access to contacts
    "https://www.googleapis.com/auth/contacts.other.readonly",  # Read-only access to other contacts
    "https://www.googleapis.com/auth/userinfo.email",  # Email address
    "https://www.googleapis.com/auth/userinfo.profile",  # Basic profile info
]


class GoogleContactsOAuthRequest(BaseModel):
    """Request schema for Google Contacts OAuth callback."""

    code: str = Field(..., description="Authorization code from Google")
    state: str = Field(..., description="CSRF state token")


# ========== ADMIN - GLOBAL CONFIG ==========


class ConnectorGlobalConfigResponse(BaseModel):
    """Response schema for connector global configuration."""

    id: UUID = Field(..., description="Config ID")
    connector_type: ConnectorType = Field(..., description="Connector type")
    is_enabled: bool = Field(..., description="Whether connector is globally enabled")
    disabled_reason: str | None = Field(None, description="Reason for disabling (if disabled)")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}


class ConnectorGlobalConfigUpdate(BaseModel):
    """Schema for updating connector global configuration."""

    is_enabled: bool = Field(..., description="Enable or disable connector type")
    disabled_reason: str | None = Field(
        None, description="Reason for disabling (required when disabling)"
    )

    @field_validator("disabled_reason")
    @classmethod
    def validate_disabled_reason(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Require disabled_reason when disabling connector."""
        is_enabled = info.data.get("is_enabled")
        if is_enabled is False and not v:
            raise ValueError("disabled_reason is required when disabling a connector")
        return v


# ========== CONNECTOR PREFERENCES ==========


class ConnectorPreferencesResponse(BaseModel):
    """Response schema for connector preferences."""

    connector_id: UUID = Field(..., description="Connector ID")
    connector_type: str = Field(..., description="Connector type")
    preferences: dict[str, Any] = Field(
        default_factory=dict,
        description="User preferences for this connector",
    )


class ConnectorPreferencesUpdate(BaseModel):
    """
    Request schema for updating connector preferences.

    The schema is validated against connector-specific Pydantic models.
    Values are sanitized and encrypted before storage.
    """

    # Dynamic fields based on connector type
    # Validated by ConnectorPreferencesService
    model_config = {"extra": "allow"}


class ConnectorPreferencesUpdateResponse(BaseModel):
    """Response schema for preferences update."""

    message: str = Field(..., description="Success message")
    connector_id: UUID = Field(..., description="Connector ID")


# ========== APPLE iCLOUD CREDENTIALS ==========


# App-specific password format: xxxx-xxxx-xxxx-xxxx (lowercase letters only)
_APPLE_APP_PASSWORD_PATTERN = re.compile(r"^[a-z]{4}-[a-z]{4}-[a-z]{4}-[a-z]{4}$")


class AppleCredentials(BaseModel):
    """
    Internal schema for Apple iCloud credentials (not exposed via API).

    Stored encrypted in the database, decrypted at runtime.
    Apple uses Apple ID + app-specific password (no OAuth, no token refresh).
    """

    apple_id: str = Field(..., description="Apple ID (email address)")
    app_password: str = Field(..., description="App-specific password")


# ============================================================================
# Philips Hue Schemas (Smart Home)
# ============================================================================


class HueConnectionMode(str, Enum):
    """Hue Bridge connection mode."""

    LOCAL = "local"
    REMOTE = "remote"


class HueBridgeCredentials(BaseModel):
    """
    Hue Bridge credentials stored encrypted in connector.credentials_encrypted.

    Supports two modes:
    - LOCAL: API key from press-link pairing + bridge IP
    - REMOTE: OAuth2 tokens from Hue Remote API
    """

    connection_mode: HueConnectionMode = Field(..., description="Local or remote connection mode")
    # Local mode fields
    api_key: str | None = Field(None, description="Hue application key from press-link pairing")
    bridge_ip: str | None = Field(None, description="Bridge internal IP address")
    bridge_id: str | None = Field(None, description="Bridge unique identifier")
    client_key: str | None = Field(None, description="Entertainment API client key")
    # Remote mode fields (OAuth2)
    access_token: str | None = Field(None, description="OAuth2 access token")
    refresh_token: str | None = Field(None, description="OAuth2 refresh token")
    token_type: str | None = Field(None, description="Token type (Bearer)")
    expires_at: datetime | None = Field(None, description="Token expiry datetime")
    remote_username: str | None = Field(None, description="Whitelist username for remote API")


class HueBridgeInfo(BaseModel):
    """Discovered Hue Bridge on local network."""

    id: str = Field(..., description="Bridge unique identifier")
    internalipaddress: str = Field(..., description="Bridge IP on local network")
    port: int | None = Field(None, description="Bridge port (443 by default)")


class HueBridgeDiscoveryResponse(BaseModel):
    """Response from bridge discovery endpoint."""

    bridges: list[HueBridgeInfo] = Field(default_factory=list, description="Discovered bridges")


class _HueBridgeIpValidatorMixin(BaseModel):
    """Mixin validating bridge_ip is a private, non-loopback IPv4 address."""

    @field_validator("bridge_ip", check_fields=False)
    @classmethod
    def validate_bridge_ip(cls, v: str) -> str:
        """Validate bridge_ip is a private IPv4 address (RFC 1918)."""
        try:
            ip = ip_address(v)
        except ValueError as e:
            raise ValueError(f"Invalid IP address format: {v}") from e
        if not isinstance(ip, IPv4Address):
            raise ValueError("Bridge IP must be an IPv4 address")
        if ip.is_loopback:
            raise ValueError("Loopback addresses are not allowed")
        if not ip.is_private:
            raise ValueError("Bridge IP must be a private network address (RFC 1918)")
        return v


class HuePairingRequest(_HueBridgeIpValidatorMixin):
    """Request to pair with a Hue Bridge via press-link."""

    bridge_ip: str = Field(..., description="Bridge IP from discovery step")


class HuePairingResponse(BaseModel):
    """Response from press-link pairing attempt."""

    success: bool = Field(..., description="Whether pairing succeeded")
    application_key: str | None = Field(None, description="Hue application key")
    client_key: str | None = Field(None, description="Entertainment API client key")
    bridge_id: str | None = Field(None, description="Bridge unique identifier")
    error: str | None = Field(None, description="Error message if pairing failed")


class HueLocalActivationRequest(_HueBridgeIpValidatorMixin):
    """Request to activate Hue connector in local mode."""

    bridge_ip: str = Field(..., description="Bridge internal IP address")
    application_key: str = Field(..., description="Application key from pairing")
    client_key: str | None = Field(None, description="Entertainment API client key")
    bridge_id: str | None = Field(None, description="Bridge unique identifier")


class _AppleCredentialsBase(BaseModel):
    """Base class for Apple iCloud credential fields with shared validators."""

    apple_id: str = Field(
        ...,
        min_length=5,
        max_length=254,
        description="Apple ID (email address)",
    )
    app_password: str = Field(
        ...,
        min_length=19,
        max_length=19,
        description="App-specific password (xxxx-xxxx-xxxx-xxxx)",
    )

    @field_validator("apple_id")
    @classmethod
    def validate_apple_id(cls, v: str) -> str:
        """Validate Apple ID is a valid email format."""
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Apple ID must be a valid email address")
        return v

    @field_validator("app_password")
    @classmethod
    def validate_app_password(cls, v: str) -> str:
        """Validate app-specific password format (xxxx-xxxx-xxxx-xxxx, lowercase)."""
        v = v.strip().lower()
        if not _APPLE_APP_PASSWORD_PATTERN.match(v):
            raise ValueError(
                "App-specific password must be in format xxxx-xxxx-xxxx-xxxx "
                "(lowercase letters only)"
            )
        return v


class AppleValidationRequest(_AppleCredentialsBase):
    """Request schema for validating Apple iCloud credentials before activation."""


class AppleValidationResponse(BaseModel):
    """Response schema for Apple iCloud credential validation."""

    is_valid: bool = Field(..., description="Whether credentials are valid")
    message: str = Field(..., description="Validation result message")


class AppleActivationRequest(_AppleCredentialsBase):
    """
    Request schema for activating Apple iCloud connectors.

    Activates one or more Apple services in a single call.
    Mutual exclusivity is enforced server-side: activating Apple Email
    will deactivate Gmail if it was active, and vice versa.
    """

    services: list[ConnectorType] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="Apple services to activate",
    )

    @field_validator("services")
    @classmethod
    def validate_services_are_apple(cls, v: list[ConnectorType]) -> list[ConnectorType]:
        """Ensure all requested services are Apple connector types."""
        apple_types = ConnectorType.get_apple_types()

        for service in v:
            if service not in apple_types:
                raise ValueError(
                    f"{service.value} is not an Apple service. "
                    f"Valid: {', '.join(ct.value for ct in apple_types)}"
                )
        return v


class AppleActivationResponse(BaseModel):
    """Response schema for Apple iCloud connector activation."""

    activated: list[ConnectorResponse] = Field(..., description="Connectors that were activated")
    deactivated: list[ConnectorResponse] = Field(
        default_factory=list,
        description="Connectors that were deactivated due to mutual exclusivity",
    )


# ========== OAUTH HEALTH CHECK ==========


class ConnectorHealthStatus(str, Enum):
    """Health status of a connector's OAuth token."""

    HEALTHY = "healthy"  # Token valid and not expiring soon
    EXPIRING_SOON = "expiring_soon"  # Token expires within threshold (warning)
    EXPIRED = "expired"  # Token has expired
    ERROR = "error"  # Connector in ERROR status (refresh failed)


class ConnectorHealthSeverity(str, Enum):
    """Severity level for health notifications."""

    INFO = "info"  # Informational only
    WARNING = "warning"  # Token expiring soon (toast notification)
    CRITICAL = "critical"  # Token expired or error (modal notification)


class ConnectorHealthItem(BaseModel):
    """Health status for a single connector."""

    id: UUID = Field(..., description="Connector ID")
    connector_type: ConnectorType = Field(..., description="Connector type")
    display_name: str = Field(..., description="Human-readable connector name")
    health_status: ConnectorHealthStatus = Field(..., description="Current health status")
    severity: ConnectorHealthSeverity = Field(..., description="Notification severity level")
    expires_in_minutes: int | None = Field(
        None,
        description="Minutes until token expires (null if expired/error)",
    )
    authorize_url: str = Field(..., description="URL to reconnect the connector")
    reconnect_type: str = Field(
        "oauth",
        description="Reconnection method: 'oauth' for Google redirect, "
        "'apple_credentials' for Apple credential form",
    )

    model_config = {"from_attributes": True}


class ConnectorHealthResponse(BaseModel):
    """Response schema for connector health check endpoint."""

    connectors: list[ConnectorHealthItem] = Field(
        default_factory=list,
        description="List of connectors with their health status",
    )
    has_issues: bool = Field(..., description="True if any connector has warning/critical status")
    critical_count: int = Field(..., description="Number of connectors with critical status")
    warning_count: int = Field(..., description="Number of connectors with warning status")
    checked_at: datetime = Field(..., description="Timestamp when health check was performed")


class ConnectorHealthSettingsResponse(BaseModel):
    """Response schema for connector health settings endpoint.

    SIMPLIFIED: Only exposes critical cooldown (for modal deduplication).
    No warning settings since we only alert on status=ERROR.
    """

    polling_interval_ms: int = Field(
        ...,
        description="How often to poll for health updates (milliseconds)",
    )
    critical_cooldown_ms: int = Field(
        ...,
        description="Cooldown before showing critical modal again (milliseconds)",
    )


# ========== CALENDAR & TASK LIST ITEMS ==========


class CalendarListItem(BaseModel):
    """A calendar item from a connected calendar provider."""

    name: str = Field(..., description="Calendar display name")
    is_default: bool = Field(False, description="Whether this is the default/primary calendar")
    access_role: str = Field("owner", description="Access role: owner or reader")


class CalendarListResponse(BaseModel):
    """Response schema for listing calendars from a connected provider."""

    items: list[CalendarListItem] = Field(..., description="List of available calendars")


class TaskListItem(BaseModel):
    """A task list item from a connected tasks provider."""

    name: str = Field(..., description="Task list display name")
    is_default: bool = Field(False, description="Whether this is the default task list")


class TaskListResponse(BaseModel):
    """Response schema for listing task lists from a connected provider."""

    items: list[TaskListItem] = Field(..., description="List of available task lists")
