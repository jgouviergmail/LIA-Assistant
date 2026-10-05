"""How each column of the ``users`` row behaves at account deletion (ADR-067).

The ``users`` row is kept but PII-scrubbed when an account is deleted, so each
of its columns is classified here: scrubbed to None, or retained with the
reason why. The CI guard ``tests/unit/domains/users/test_user_data_map_guard.py``
fails on an unclassified or stale column, and ``_mark_user_deleted``'s SCRUBBED
set is the test oracle for the scrub.

Moved out of ``user_data_map`` (2026-09-30) when the table classification
outgrew the logical-SLOC cap: two classifications, two modules.
"""

from enum import Enum


class UserColumnClass(str, Enum):
    """How one ``users`` column behaves at account deletion."""

    SCRUBBED = "scrubbed"
    """Set to None by ``_mark_user_deleted`` (PII)."""

    RETAINED_IDENTITY = "retained_identity"
    """Kept as billing contact (email, full_name — ADR-067)."""

    RETAINED_LIFECYCLE = "retained_lifecycle"
    """Kept as account lifecycle/bookkeeping state."""

    RETAINED_PREFERENCE = "retained_preference"
    """Kept: non-content operational preference (booleans, hours, sizes)."""


_SCRUBBED = UserColumnClass.SCRUBBED
_IDENTITY = UserColumnClass.RETAINED_IDENTITY
_LIFECYCLE = UserColumnClass.RETAINED_LIFECYCLE
_PREFERENCE = UserColumnClass.RETAINED_PREFERENCE


USER_COLUMNS: dict[str, UserColumnClass] = {
    # PII — scrubbed to None by _mark_user_deleted (tested column by column).
    "hashed_password": _SCRUBBED,
    "oauth_provider": _SCRUBBED,
    "oauth_provider_id": _SCRUBBED,
    "picture_url": _SCRUBBED,
    "home_location_encrypted": _SCRUBBED,
    "last_known_location_encrypted": _SCRUBBED,
    "last_known_location_updated_at": _SCRUBBED,
    "journal_portrait_full": _SCRUBBED,
    "journal_portrait_brief": _SCRUBBED,
    "journal_portrait_compiled_at": _SCRUBBED,
    "journal_portrait_sources": _SCRUBBED,
    "phone_number_encrypted": _SCRUBBED,
    "phone_number_verified_at": _SCRUBBED,
    # Billing contact (ADR-067).
    "email": _IDENTITY,
    "full_name": _IDENTITY,
    # Account lifecycle / bookkeeping.
    "id": _LIFECYCLE,
    "created_at": _LIFECYCLE,
    "updated_at": _LIFECYCLE,
    "is_active": _LIFECYCLE,
    "is_verified": _LIFECYCLE,
    "is_superuser": _LIFECYCLE,
    "last_login": _LIFECYCLE,
    "deleted_at": _LIFECYCLE,
    "deleted_reason": _LIFECYCLE,
    # Terms acceptance: the legal record that this account agreed to the
    # terms, and to WHICH version. Kept like the rest of the lifecycle
    # bookkeeping — scrubbing it would destroy the only evidence of consent.
    "terms_accepted_at": _LIFECYCLE,
    "terms_version": _LIFECYCLE,
    # Non-content operational preferences.
    "timezone": _PREFERENCE,
    "language": _PREFERENCE,
    "personality_id": _PREFERENCE,
    "use_last_known_location": _PREFERENCE,
    "discovery_enabled": _PREFERENCE,
    # A consent, kept separate from discovery on purpose (ADR-189).
    "peer_email_visible": _PREFERENCE,
    # How the user wants a "360° point" built — a display preference.
    "relation_overview_scope": _PREFERENCE,
    "relation_debrief_enabled": _PREFERENCE,
    "memory_enabled": _PREFERENCE,
    "health_metrics_agents_enabled": _PREFERENCE,
    "execution_mode": _PREFERENCE,
    "exchange_rhythm": _PREFERENCE,
    "voice_enabled": _PREFERENCE,
    "speaking_avatar_enabled": _PREFERENCE,
    "voice_mode_enabled": _PREFERENCE,
    "voice_stt_mode": _PREFERENCE,
    "tokens_display_enabled": _PREFERENCE,
    "debug_panel_enabled": _PREFERENCE,
    "response_display_mode": _PREFERENCE,
    "theme": _PREFERENCE,
    "color_theme": _PREFERENCE,
    "font_family": _PREFERENCE,
    "font_size": _PREFERENCE,
    "habits_enabled": _PREFERENCE,
    "interests_enabled": _PREFERENCE,
    "interests_notify_start_hour": _PREFERENCE,
    "interests_notify_end_hour": _PREFERENCE,
    "interests_notify_min_per_day": _PREFERENCE,
    "interests_notify_max_per_day": _PREFERENCE,
    "heartbeat_enabled": _PREFERENCE,
    "heartbeat_notify_start_hour": _PREFERENCE,
    "heartbeat_notify_end_hour": _PREFERENCE,
    # Which sources may interrupt the reader (ADR-197). A setting like its
    # siblings above: it holds source KEYS from a closed registry, never
    # content — nothing personal to scrub, and resetting it would silently
    # re-enable interruptions the user refused.
    "heartbeat_disabled_sources": _PREFERENCE,
    "moment_kinds_disabled": _PREFERENCE,
    "journals_enabled": _PREFERENCE,
    "journal_consolidation_enabled": _PREFERENCE,
    "journal_consolidation_with_history": _PREFERENCE,
    "journal_max_total_chars": _PREFERENCE,
    "journal_context_max_chars": _PREFERENCE,
    "journal_max_entry_chars": _PREFERENCE,
    "journal_context_max_results": _PREFERENCE,
    "journal_last_consolidated_at": _PREFERENCE,
    "journal_last_cost_tokens_in": _PREFERENCE,
    "journal_last_cost_tokens_out": _PREFERENCE,
    "journal_last_cost_eur": _PREFERENCE,
    "journal_last_cost_at": _PREFERENCE,
    "journal_last_cost_source": _PREFERENCE,
    "psyche_enabled": _PREFERENCE,
    "psyche_display_avatar": _PREFERENCE,
    "psyche_sensitivity": _PREFERENCE,
    "psyche_stability": _PREFERENCE,
    "onboarding_completed": _PREFERENCE,
    "login_notifications_enabled": _PREFERENCE,
    "image_generation_enabled": _PREFERENCE,
    "image_generation_default_quality": _PREFERENCE,
    "image_generation_default_size": _PREFERENCE,
    "image_generation_output_format": _PREFERENCE,
    "image_generation_prompt_enhancement": _PREFERENCE,
    "admin_mcp_disabled_servers": _PREFERENCE,
    "briefing_preferences": _PREFERENCE,
    "onboarding_checklist": _PREFERENCE,
    "chat_shortcuts": _PREFERENCE,
    "settings_shortcuts": _PREFERENCE,
    "phone_rich_context_enabled": _PREFERENCE,
    "phone_disabled_domains": _PREFERENCE,
    "phone_call_mode": _PREFERENCE,
    "live_preferences": _PREFERENCE,
}
