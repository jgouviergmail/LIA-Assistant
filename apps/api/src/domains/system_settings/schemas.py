"""
System Settings Pydantic schemas.

Provides request/response models for the System Settings API.

Created: 2026-01-16
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.config.voice import VoiceTTSMode


class SystemSettingResponse(BaseModel):
    """Generic system setting response."""

    id: UUID
    key: str
    value: str
    updated_by: UUID | None
    change_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VoiceTTSModeResponse(BaseModel):
    """
    Response for Voice TTS Mode setting.

    Provides the current voice quality mode and metadata.
    Mode descriptions are handled via i18n on the frontend.
    """

    mode: VoiceTTSMode = Field(
        description="Current voice TTS mode: 'standard' (Edge TTS) or 'hd' (OpenAI/Gemini)"
    )
    updated_by: UUID | None = Field(
        default=None,
        description="Admin user ID who last changed the mode",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Timestamp of last mode change",
    )
    is_default: bool = Field(
        default=False,
        description="True if using default from environment (no DB setting)",
    )

    model_config = {"from_attributes": True}


class VoiceTTSModeUpdate(BaseModel):
    """
    Request to update Voice TTS Mode.

    Only administrators can change this setting.
    The change affects all users immediately.
    """

    mode: VoiceTTSMode = Field(description="New voice TTS mode: 'standard' or 'hd'")
    change_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the change (for audit trail)",
    )


# =============================================================================
# DEBUG PANEL SETTINGS
# =============================================================================


class DebugPanelEnabledResponse(BaseModel):
    """
    Response for Debug Panel Enabled setting.

    Controls whether the debug panel is visible in the chat page.
    Admin-only response with full metadata.
    """

    enabled: bool = Field(description="Whether the debug panel is enabled")
    updated_by: UUID | None = Field(
        default=None,
        description="Admin user ID who last changed the setting",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Timestamp of last setting change",
    )
    is_default: bool = Field(
        default=False,
        description="True if using default (no DB setting)",
    )

    model_config = {"from_attributes": True}


class DebugPanelStatusResponse(BaseModel):
    """
    Public read-only response for debug panel status.

    Returns the effective enabled flag and whether user-level access is available.
    Used by authenticated users to determine debug panel visibility.
    """

    enabled: bool = Field(
        description="Whether the debug panel is effectively enabled for this user"
    )
    user_access_available: bool = Field(
        default=False,
        description="Whether the admin has enabled user-level debug panel access (for preferences UI)",
    )


class DebugPanelEnabledUpdate(BaseModel):
    """
    Request to update Debug Panel Enabled setting.

    Only administrators can change this setting.
    """

    enabled: bool = Field(description="Whether to enable the debug panel")
    change_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the change (for audit trail)",
    )


# =============================================================================
# DEBUG PANEL USER ACCESS SETTINGS
# =============================================================================


class DebugPanelUserAccessResponse(BaseModel):
    """
    Response for Debug Panel User Access setting.

    Controls whether non-admin users can toggle their own debug panel
    in their Preferences settings.
    """

    available: bool = Field(description="Whether user-level debug panel access is enabled")
    updated_by: UUID | None = Field(
        default=None,
        description="Admin user ID who last changed the setting",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Timestamp of last setting change",
    )
    is_default: bool = Field(
        default=False,
        description="True if using default (no DB setting)",
    )

    model_config = {"from_attributes": True}


class DebugPanelUserAccessUpdate(BaseModel):
    """
    Request to update Debug Panel User Access setting.

    Only administrators can change this setting.
    When disabled, non-admin users lose access to the debug panel
    regardless of their personal preference.
    """

    available: bool = Field(description="Whether to enable user-level debug panel access")
    change_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the change (for audit trail)",
    )
