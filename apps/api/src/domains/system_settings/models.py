"""
System Settings database models.

Stores application-wide settings controlled by administrators.
Follows the same pattern as ConnectorGlobalConfig for consistency.

Created: 2026-01-16
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class SystemSettingKey(str, enum.Enum):
    """
    System setting keys.

    Each key represents a global application setting that can be
    modified by administrators.

    The legacy ``voice_tts_mode`` key was retired in v1.20.x — TTS
    provider/model selection now lives on ``llm_config_overrides``
    (LLM type ``voice_tts``).
    """

    # Fresh-install reference seed bundle marker (ADR-215): value is the
    # exact six-record bundle SHA-256 written by verify_reference_seeds.sql
    # in the same transaction as the seeds. Raw SQL uses the persisted
    # member-name token SELF_HOST_SEED_BUNDLE (Enum(native_enum=False)
    # stores names); the ORM round-trip is pinned by
    # test_reference_seed_bundle_contract.py.
    SELF_HOST_SEED_BUNDLE = "self_host_seed_bundle"

    # Debug panel: "true" or "false" (controls visibility in chat page)
    DEBUG_PANEL_ENABLED = "debug_panel_enabled"

    # Debug panel user access: "true" or "false" (controls whether non-admin users can toggle their own debug panel)
    DEBUG_PANEL_USER_ACCESS_ENABLED = "debug_panel_user_access_enabled"

    # Instance-wide daily spend ceiling in euros, e.g. "1" or "0.50".
    # Empty/absent = no operator ceiling; the deployment ceiling (environment)
    # still applies. An operator may only LOWER it, never raise it.
    INSTANCE_DAILY_BUDGET_EUR = "instance_daily_budget_eur"

    # Demonstrator instance marker: "true" only on the database of a public
    # demonstrator. The nightly account wipe requires it IN ADDITION to the
    # environment flag, so an environment variable alone can never authorize
    # mass deletion on a database that is not a demonstrator's. The condition
    # travels with the data it destroys.
    DEMO_INSTANCE_MARKER = "demo_instance_marker"

    # Administrable platform capabilities (live-demonstrator programme, lot 3).
    # One key per capability; their SettingSpecs are GENERATED from
    # domains/capabilities/registry.py, so a capability cannot ship with an
    # undeclared key. Value is "true"/"false"; absent = enabled, so a fresh
    # instance behaves exactly as before any switch existed.
    CAPABILITY_STT_ENABLED = "capability_stt_enabled"
    CAPABILITY_TTS_ENABLED = "capability_tts_enabled"
    CAPABILITY_IMAGE_GENERATION_ENABLED = "capability_image_generation_enabled"
    CAPABILITY_ATTACHMENTS_ENABLED = "capability_attachments_enabled"
    CAPABILITY_RAG_SPACES_ENABLED = "capability_rag_spaces_enabled"
    CAPABILITY_WEB_SEARCH_ENABLED = "capability_web_search_enabled"
    CAPABILITY_BROWSER_ENABLED = "capability_browser_enabled"
    CAPABILITY_SKILLS_ENABLED = "capability_skills_enabled"
    CAPABILITY_MCP_ENABLED = "capability_mcp_enabled"
    CAPABILITY_TELEPHONY_ENABLED = "capability_telephony_enabled"

    # Whether the landing advertises the public demonstrator. Off by default:
    # a fresh instance never advertises a demonstrator it does not run. Read
    # ANONYMOUSLY (the landing has no session) and switchable at runtime —
    # "take the demo offline" cannot wait for a rebuild.
    PUBLIC_DEMO_LINK_ENABLED = "public_demo_link_enabled"

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
            key=SystemSettingKey.DEBUG_PANEL_ENABLED,
            value="true",
            updated_by=admin_user.id,
        )
    """

    __tablename__ = "system_settings"

    key: Mapped[SystemSettingKey] = mapped_column(
        Enum(SystemSettingKey, native_enum=False, length=50),
        nullable=False,
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

    # Unique key (enforced by the constraint; its backing index serves lookups).
    __table_args__ = (UniqueConstraint("key", name="uq_system_settings_key"),)

    def __repr__(self) -> str:
        return f"<SystemSetting(key={self.key.value}, value={self.value})>"
