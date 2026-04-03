"""
Authentication domain models (database entities).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_USER_DISPLAY_TIMEZONE,
    HEARTBEAT_MAX_PER_DAY_DEFAULT,
    HEARTBEAT_MIN_PER_DAY_DEFAULT,
    HEARTBEAT_NOTIFY_END_HOUR_DEFAULT,
    HEARTBEAT_NOTIFY_START_HOUR_DEFAULT,
    HEARTBEAT_PUSH_ENABLED_DEFAULT,
    IMAGE_GENERATION_ENABLED_DEFAULT,
    IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
    IMAGE_GENERATION_QUALITY_DEFAULT,
    IMAGE_GENERATION_SIZE_DEFAULT,
    INTEREST_NOTIFY_END_HOUR_DEFAULT,
    INTEREST_NOTIFY_MAX_PER_DAY_DEFAULT,
    INTEREST_NOTIFY_MIN_PER_DAY_DEFAULT,
    INTEREST_NOTIFY_START_HOUR_DEFAULT,
    JOURNAL_CONTEXT_MAX_CHARS_DEFAULT,
    JOURNAL_CONTEXT_MAX_RESULTS_DEFAULT,
    JOURNAL_MAX_ENTRY_CHARS_DEFAULT,
    JOURNAL_MAX_TOTAL_CHARS_DEFAULT,
)
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.interests.models import UserInterest
    from src.domains.journals.models import JournalEntry
    from src.domains.memories.models import Memory
    from src.domains.notifications.models import UserFCMToken
    from src.domains.personalities.models import Personality
    from src.domains.psyche.models import PsycheState
    from src.domains.reminders.models import Reminder
    from src.domains.scheduled_actions.models import ScheduledAction
    from src.domains.skills.models import UserSkillState
    from src.domains.sub_agents.models import SubAgent
    from src.domains.usage_limits.models import UserUsageLimit


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
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        nullable=False,
        server_default=DEFAULT_USER_DISPLAY_TIMEZONE,
        comment="User timezone (IANA timezone name) for personalized timestamp display",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        default=DEFAULT_LANGUAGE,
        nullable=False,
        server_default=DEFAULT_LANGUAGE,
        comment="User preferred language (ISO 639-1 code: fr, en, es, de, it, zh-CN) for emails and notifications",
    )

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

    # Sub-agents delegation preference (F6)
    sub_agents_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="User preference for sub-agent delegation. True = assistant can delegate tasks to specialized sub-agents.",
    )

    # Response display mode: "cards" (HTML data cards), "html" (rich HTML), "markdown" (plain)
    response_display_mode: Mapped[str] = mapped_column(
        String(20),
        default="cards",
        nullable=False,
        server_default="cards",
        comment="Response display mode: cards (HTML data cards), html (rich formatting), markdown (plain text).",
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

    # Account deletion (soft-delete with data purge)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
        comment="Timestamp of account deletion. NULL = active/inactive. Non-NULL = deleted (data purged, row kept for billing).",
    )
    deleted_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default=None,
        comment="Admin-provided reason for account deletion.",
    )

    # Interest learning system preferences
    interests_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable proactive interest notifications.",
    )
    interests_notify_start_hour: Mapped[int] = mapped_column(
        default=INTEREST_NOTIFY_START_HOUR_DEFAULT,
        nullable=False,
        server_default=str(INTEREST_NOTIFY_START_HOUR_DEFAULT),
        comment="Start hour for interest notifications (0-23, user timezone).",
    )
    interests_notify_end_hour: Mapped[int] = mapped_column(
        default=INTEREST_NOTIFY_END_HOUR_DEFAULT,
        nullable=False,
        server_default=str(INTEREST_NOTIFY_END_HOUR_DEFAULT),
        comment="End hour for interest notifications (0-23, user timezone).",
    )
    interests_notify_min_per_day: Mapped[int] = mapped_column(
        default=INTEREST_NOTIFY_MIN_PER_DAY_DEFAULT,
        nullable=False,
        server_default=str(INTEREST_NOTIFY_MIN_PER_DAY_DEFAULT),
        comment="Minimum interest notifications per day (1-10).",
    )
    interests_notify_max_per_day: Mapped[int] = mapped_column(
        default=INTEREST_NOTIFY_MAX_PER_DAY_DEFAULT,
        nullable=False,
        server_default=str(INTEREST_NOTIFY_MAX_PER_DAY_DEFAULT),
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
        default=HEARTBEAT_MIN_PER_DAY_DEFAULT,
        nullable=False,
        server_default=str(HEARTBEAT_MIN_PER_DAY_DEFAULT),
        comment="Minimum heartbeat notifications per day (1-8).",
    )
    heartbeat_max_per_day: Mapped[int] = mapped_column(
        default=HEARTBEAT_MAX_PER_DAY_DEFAULT,
        nullable=False,
        server_default=str(HEARTBEAT_MAX_PER_DAY_DEFAULT),
        comment="Maximum heartbeat notifications per day (1-8).",
    )
    heartbeat_push_enabled: Mapped[bool] = mapped_column(
        default=HEARTBEAT_PUSH_ENABLED_DEFAULT,
        nullable=False,
        server_default=str(HEARTBEAT_PUSH_ENABLED_DEFAULT).lower(),
        comment="Enable push (FCM/Telegram) for heartbeats. If false, only SSE + archive.",
    )
    heartbeat_notify_start_hour: Mapped[int] = mapped_column(
        default=HEARTBEAT_NOTIFY_START_HOUR_DEFAULT,
        nullable=False,
        server_default=str(HEARTBEAT_NOTIFY_START_HOUR_DEFAULT),
        comment="Start hour (0-23) for heartbeat notification window.",
    )
    heartbeat_notify_end_hour: Mapped[int] = mapped_column(
        default=HEARTBEAT_NOTIFY_END_HOUR_DEFAULT,
        nullable=False,
        server_default=str(HEARTBEAT_NOTIFY_END_HOUR_DEFAULT),
        comment="End hour (0-23) for heartbeat notification window.",
    )

    # Journal settings (Personal Journals — Carnets de Bord)
    journals_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable personal journals feature (user preference).",
    )
    journal_consolidation_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable periodic journal consolidation by the assistant.",
    )
    journal_consolidation_with_history: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="Allow consolidation to analyze conversation history (higher cost).",
    )
    journal_max_total_chars: Mapped[int] = mapped_column(
        default=JOURNAL_MAX_TOTAL_CHARS_DEFAULT,
        nullable=False,
        server_default=str(JOURNAL_MAX_TOTAL_CHARS_DEFAULT),
        comment="Max total characters across all active journal entries.",
    )
    journal_context_max_chars: Mapped[int] = mapped_column(
        default=JOURNAL_CONTEXT_MAX_CHARS_DEFAULT,
        nullable=False,
        server_default=str(JOURNAL_CONTEXT_MAX_CHARS_DEFAULT),
        comment="Max characters for journal context injection into prompts.",
    )
    journal_max_entry_chars: Mapped[int] = mapped_column(
        default=JOURNAL_MAX_ENTRY_CHARS_DEFAULT,
        nullable=False,
        server_default=str(JOURNAL_MAX_ENTRY_CHARS_DEFAULT),  # 800 (directive format)
        comment="Max characters per individual journal entry.",
    )
    journal_context_max_results: Mapped[int] = mapped_column(
        default=JOURNAL_CONTEXT_MAX_RESULTS_DEFAULT,
        nullable=False,
        server_default=str(JOURNAL_CONTEXT_MAX_RESULTS_DEFAULT),
        comment="Max entries returned by semantic search for context injection.",
    )
    journal_last_consolidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last journal consolidation for this user.",
    )
    journal_last_cost_tokens_in: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Input tokens of last journal background intervention.",
    )
    journal_last_cost_tokens_out: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Output tokens of last journal background intervention.",
    )
    journal_last_cost_eur: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6),
        nullable=True,
        comment="Real cost in EUR of last journal background intervention.",
    )
    journal_last_cost_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last journal background intervention.",
    )
    journal_last_cost_source: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Source of last journal intervention: 'extraction' or 'consolidation'.",
    )

    # Psyche Engine preferences
    psyche_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Enable Psyche Engine (dynamic mood, emotions, relationship tracking).",
    )
    psyche_display_avatar: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Display emotional avatar (personality + mood smiley) in chat messages.",
    )
    psyche_sensitivity: Mapped[int] = mapped_column(
        default=70,
        nullable=False,
        server_default="70",
        comment="Emotional expressiveness (0-100). Higher = more reactive to stimuli.",
    )
    psyche_stability: Mapped[int] = mapped_column(
        default=60,
        nullable=False,
        server_default="60",
        comment="Mood stability (0-100). Higher = slower mood changes, more resistant to transient stimuli.",
    )

    # Onboarding tutorial preference
    onboarding_completed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        server_default="false",
        comment="User has completed/dismissed the onboarding tutorial.",
    )

    # Image Generation preferences (evolution — AI Image Generation)
    image_generation_enabled: Mapped[bool] = mapped_column(
        default=IMAGE_GENERATION_ENABLED_DEFAULT,
        nullable=False,
        server_default="true",
        comment="User opt-in for AI image generation feature.",
    )
    image_generation_default_quality: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IMAGE_GENERATION_QUALITY_DEFAULT,
        server_default=IMAGE_GENERATION_QUALITY_DEFAULT,
        comment="Default image quality: low, medium, high.",
    )
    image_generation_default_size: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=IMAGE_GENERATION_SIZE_DEFAULT,
        server_default=IMAGE_GENERATION_SIZE_DEFAULT,
        comment="Default image size: 1024x1024, 1536x1024, 1024x1536.",
    )
    image_generation_output_format: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
        server_default=IMAGE_GENERATION_OUTPUT_FORMAT_DEFAULT,
        comment="Default output format: png, jpeg, webp.",
    )

    # Admin MCP per-user toggle (evolution F2.5)
    admin_mcp_disabled_servers: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
        nullable=False,
        comment="List of admin MCP server keys disabled by this user (e.g., ['google_flights'])",
    )

    # Per-user skill activation states (normalized in user_skill_states table)
    skill_states: Mapped[list["UserSkillState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
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
    journal_entries: Mapped[list["JournalEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["Memory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    scheduled_actions: Mapped[list["ScheduledAction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sub_agents: Mapped[list["SubAgent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    # NOTE: No relationship to UserMCPServer — user_id FK + CASCADE handles
    # deletion. ORM relationship was unused and caused import-order issues
    # (UserMCPServer mapper configuration requires User to be loaded first).

    # Usage limits (1:1, optional — no record means unlimited)
    usage_limit: Mapped["UserUsageLimit | None"] = relationship(
        back_populates="user", lazy="noload", cascade="all, delete-orphan"
    )

    # Psyche state (1:1, optional — created on first interaction when psyche_enabled)
    psyche_state: Mapped["PsycheState | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def is_deleted(self) -> bool:
        """Whether the account has been soft-deleted (data purged, row kept for billing)."""
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
