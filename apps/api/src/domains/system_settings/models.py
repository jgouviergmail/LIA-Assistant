"""
System Settings database models.

Stores application-wide settings controlled by administrators.
Follows the same pattern as ConnectorGlobalConfig for consistency.

Created: 2026-01-16
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class SystemSettingKey(str, enum.Enum):
    """
    System setting keys.

    Each key represents a global application setting that can be
    modified by administrators.
    """

    # Voice TTS mode: "standard" (Edge TTS) or "hd" (OpenAI/Gemini)
    VOICE_TTS_MODE = "voice_tts_mode"

    # Debug panel: "true" or "false" (controls visibility in chat page)
    DEBUG_PANEL_ENABLED = "debug_panel_enabled"

    # Debug panel user access: "true" or "false" (controls whether non-admin users can toggle their own debug panel)
    DEBUG_PANEL_USER_ACCESS_ENABLED = "debug_panel_user_access_enabled"

    # Future settings can be added here:
    # MAINTENANCE_MODE = "maintenance_mode"
    # DEFAULT_LANGUAGE = "default_language"
    # etc.


class SystemSetting(BaseModel):
    """
    System Setting model for application-wide configuration.

    Stores key-value pairs for global settings that can be modified
    by administrators at runtime (without server restart).

    Attributes:
        key: Unique setting identifier (from SystemSettingKey enum)
        value: Setting value (string, JSON-serializable for complex values)
        updated_by: Admin user ID who last updated the setting
        updated_at: Timestamp of last update (inherited from BaseModel)

    Example:
        setting = SystemSetting(
            key=SystemSettingKey.VOICE_TTS_MODE,
            value="hd",
            updated_by=admin_user.id,
        )
    """

    __tablename__ = "system_settings"

    key: Mapped[SystemSettingKey] = mapped_column(
        Enum(SystemSettingKey, native_enum=False),
        unique=True,
        nullable=False,
        index=True,
    )

    value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Track who last updated this setting
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional description of why the change was made
    change_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<SystemSetting(key={self.key.value}, value={self.value})>"
