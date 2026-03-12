"""
Authentication domain models (database entities).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.interests.models import UserInterest
    from src.domains.notifications.models import UserFCMToken
    from src.domains.personalities.models import Personality
    from src.domains.reminders.models import Reminder
    from src.domains.scheduled_actions.models import ScheduledAction


class User(BaseModel):
    """
    User model for authentication and profile.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Nullable for OAuth-only users
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )  # Requires email verification
    is_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)

    # OAuth fields
    oauth_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'google', 'github', etc.
    oauth_provider_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Provider's user ID
    picture_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # Profile picture URL - 2048 chars to handle OAuth provider URLs with parameters

    # User preferences
    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="Europe/Paris",
        comment="User timezone (IANA timezone name) for personalized timestamp display",
    )  # Default: Europe/Paris (French users)
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="fr",
        comment="User preferred language (ISO 639-1 code: fr, en, es, de, it, zh-CN) for emails and notifications",
    )  # Default: fr (French)

    # Personality preference
    personality_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personalities.id", ondelete="SET NULL"),
        nullable=True,
        comment="User's preferred LLM personality (NULL = use default)",
    )

    # Home location (encrypted for privacy)
    home_location_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted home location JSON: {address, lat, lon, place_id}",
    )

    # Long-term memory preference
    memory_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="User preference for long-term memory (extraction + injection). True = enabled by default.",
    )

    # Voice comments (TTS) preference
    voice_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User preference for voice comments (TTS). False = disabled by default (opt-in).",
    )

    # Voice mode (wake word + STT input) preference
    voice_mode_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User preference for voice mode (wake word + STT input). False = disabled by default (opt-in).",
    )

    # Tokens display preference (desktop only)
    tokens_display_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User preference for displaying token usage and costs. False = disabled by default (opt-in).",
    )

    # Debug panel preference (opt-in, requires admin debug_panel_user_access_enabled)
    debug_panel_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User preference for debug panel. False = disabled by default (opt-in). Requires admin debug_panel_user_access_enabled.",
    )

    # Theme preferences (persisted per user)
    theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="system",
        server_default="system",
        comment="User display mode preference: 'light', 'dark', or 'system' (follow OS).",
    )
    color_theme: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="default",
        server_default="default",
        comment="User color theme preference: 'default', 'ocean', 'forest', 'sunset', 'slate'.",
    )
    font_family: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="system",
        server_default="system",
        comment="User font family preference: system, noto-sans, plus-jakarta-sans, ibm-plex-sans, geist, source-sans-pro, merriweather, libre-baskerville, fira-code.",
    )

    # Last login tracking
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp of last successful login (OAuth or password).",
    )

    # Interest learning system preferences
    interests_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable proactive interest notifications.",
    )
    interests_notify_start_hour: Mapped[int] = mapped_column(
        default=9,
        nullable=False,
        server_default="9",
        comment="Start hour for interest notifications (0-23, user timezone).",
    )
    interests_notify_end_hour: Mapped[int] = mapped_column(
        default=22,
        nullable=False,
        server_default="22",
        comment="End hour for interest notifications (0-23, user timezone).",
    )
    interests_notify_min_per_day: Mapped[int] = mapped_column(
        default=2,
        nullable=False,
        server_default="2",
        comment="Minimum interest notifications per day (1-10).",
    )
    interests_notify_max_per_day: Mapped[int] = mapped_column(
        default=5,
        nullable=False,
        server_default="5",
        comment="Maximum interest notifications per day (1-10).",
    )

    # Heartbeat autonome settings (Notifications proactives)
    heartbeat_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="Enable proactive heartbeat notifications (opt-in).",
    )
    heartbeat_min_per_day: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
        server_default="1",
        comment="Minimum heartbeat notifications per day (1-8).",
    )
    heartbeat_max_per_day: Mapped[int] = mapped_column(
        default=3,
        nullable=False,
        server_default="3",
        comment="Maximum heartbeat notifications per day (1-8).",
    )
    heartbeat_push_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable push (FCM/Telegram) for heartbeats. If false, only SSE + archive.",
    )
    heartbeat_notify_start_hour: Mapped[int] = mapped_column(
        default=9,
        nullable=False,
        server_default="9",
        comment="Start hour (0-23) for heartbeat notification window.",
    )
    heartbeat_notify_end_hour: Mapped[int] = mapped_column(
        default=22,
        nullable=False,
        server_default="22",
        comment="End hour (0-23) for heartbeat notification window.",
    )

    # Onboarding tutorial preference
    onboarding_completed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User has completed/dismissed the onboarding tutorial.",
    )

    # Admin MCP per-user toggle (evolution F2.5)
    admin_mcp_disabled_servers: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
        comment="List of admin MCP server keys disabled by this user (e.g., ['google_flights'])",
    )

    # Skills per-user toggle
    disabled_skills: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
        comment="List of skill names disabled by this user (e.g., ['briefing-quotidien'])",
    )

    # Relationships
    personality: Mapped["Personality | None"] = relationship(
        back_populates="users",
        foreign_keys=[personality_id],
    )
    connectors: Mapped[list["Connector"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    fcm_tokens: Mapped[list["UserFCMToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    interests: Mapped[list["UserInterest"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    scheduled_actions: Mapped[list["ScheduledAction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # NOTE: No relationship to UserMCPServer — user_id FK + CASCADE handles
    # deletion. ORM relationship was unused and caused import-order issues
    # (UserMCPServer mapper configuration requires User to be loaded first).

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
