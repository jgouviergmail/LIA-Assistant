"""Single source of truth classifying user data across tables and columns.

Every SQLAlchemy table and every ``users`` column is deliberately classified
here. The CI guard ``tests/unit/domains/users/test_user_data_map_guard.py``
fails on any unclassified (or stale) entry and cross-checks the USER_PURGED
set against ``account_deletion_service.build_purge_statements``, closing the
defect class where a new user-scoped table silently escapes both the
account-deletion purge (ADR-067) and the GDPR export.

Consumers:
    - Account deletion (ADR-067): purge coverage is asserted against this map.
    - GDPR export: exporters are wired against ``ExportPolicy.FULL``
      entries; ``EXCLUDED`` entries never reach an archive.
    - ``_mark_user_deleted``: the SCRUBBED column set is the test oracle for
      the users-row PII scrub.

This is a data module (classification tables), exempt from the logical-SLOC
cap like other ``core``/constants data modules.
"""

from dataclasses import dataclass
from enum import Enum


class TableDataClass(str, Enum):
    """How a table relates to a user's personal data lifecycle."""

    USER_PURGED = "user_purged"
    """User-scoped rows explicitly deleted by the account-deletion purge."""

    USER_CASCADE = "user_cascade"
    """Deleted via an ondelete=CASCADE FK chain from a USER_PURGED table."""

    USER_ROW_SCRUBBED = "user_row_scrubbed"
    """The users row itself: kept but PII-scrubbed (see USER_COLUMNS)."""

    BILLING_RETAINED = "billing_retained"
    """Kept after deletion for dispute resolution (ADR-067)."""

    GLOBAL = "global"
    """Not user data: configuration, pricing, catalogs, admin records."""


class ExportPolicy(str, Enum):
    """Whether the GDPR export includes this table's rows."""

    FULL = "full"
    """Exported (the exporter still redacts secret columns if any)."""

    EXCLUDED = "excluded"
    """Never exported — secret material, derived data, or non-user data."""


@dataclass(frozen=True)
class TableRule:
    """Classification of one table.

    Attributes:
        data_class: Lifecycle class (purge semantics).
        export: GDPR-export policy.
        reason: Audited rationale — mandatory for EXCLUDED / retained /
            global rules, short content description otherwise.
    """

    data_class: TableDataClass
    export: ExportPolicy
    reason: str


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


# Tables that exist at runtime but are NOT SQLAlchemy metadata tables —
# purged out-of-band by the deletion service (LangGraph checkpointer /
# store) or infrastructure-owned (alembic).
EXTERNAL_TABLES: frozenset[str] = frozenset(
    {
        "checkpoints",
        "checkpoint_writes",
        "checkpoint_blobs",
        "store",
        "store_vectors",
        "alembic_version",
    }
)


_PURGED_FULL = TableRule(
    data_class=TableDataClass.USER_PURGED,
    export=ExportPolicy.FULL,
    reason="User content — purged on deletion, included in the GDPR export.",
)


TABLE_RULES: dict[str, TableRule] = {
    # ------------------------------------------------------------------
    # The users row: kept, PII-scrubbed column by column (USER_COLUMNS).
    # ------------------------------------------------------------------
    "users": TableRule(
        data_class=TableDataClass.USER_ROW_SCRUBBED,
        export=ExportPolicy.FULL,
        reason="Row kept for billing contact; PII columns scrubbed per USER_COLUMNS; "
        "settings columns exported as the user's preferences.",
    ),
    # ------------------------------------------------------------------
    # User content: purged + exported.
    # ------------------------------------------------------------------
    "conversations": _PURGED_FULL,
    "conversation_messages": _PURGED_FULL,
    # ------------------------------------------------------------------
    # Peers (peer-connections program): two-sided rows — a user sits on
    # either side, so every table is explicitly purged (users-row soft
    # delete means FK CASCADEs from users never fire). Shares/messages
    # also die with their connection, but are deleted explicitly first
    # for accurate counting (conversation_messages precedent).
    # ------------------------------------------------------------------
    "relation_favorites": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="CRM favorites (starred relationship names) — purged on deletion.",
    ),
    "relation_aliases": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "CRM identity merges declared by the user (which spellings are one "
            "person) — purged on deletion."
        ),
    ),
    "peer_connections": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="User-to-user connection lifecycle rows (either side) — purged on deletion.",
    ),
    "peer_blocks": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Anti-harassment blocks (either side) — purged on deletion.",
    ),
    "peer_domain_shares": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Sharing choices on connections involving the user — purged with them.",
    ),
    "peer_messages": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Relayed correspondence: delivery metadata forever, both texts until "
            "the retention horizon clears them (ADR-186). Exported side-scoped — "
            "each participant gets their own words — and purged on deletion."
        ),
    ),
    "peer_access_log": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Cross-user read audit (accessor or owner side) — purged on deletion.",
    ),
    "conversation_audit_log": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="User-scoped conversation audit trail (deletions/exports of threads).",
    ),
    "memories": _PURGED_FULL,
    "journal_entries": _PURGED_FULL,
    # Bounded pointers from a belief to the turn behind it — never a copy of
    # that turn (the source columns are FKs with ON DELETE SET NULL, so a
    # deleted conversation leaves a dated tombstone). Exported in full: it is
    # the only thing that lets the reader see WHY LIA concluded something, and
    # the export resolves nothing the account does not already own.
    "provenance_references": _PURGED_FULL,
    "psyche_states": _PURGED_FULL,
    "psyche_history": _PURGED_FULL,
    "user_interests": _PURGED_FULL,
    "interest_notifications": _PURGED_FULL,
    "heartbeat_notifications": _PURGED_FULL,
    "reminders": _PURGED_FULL,
    "scheduled_actions": _PURGED_FULL,
    "open_loops": _PURGED_FULL,
    # Product analytics (ADR-178): outcome truth + lifecycle events. No FK
    # CASCADE (plain user_id columns) — purged explicitly by the deletion
    # service, exported in full (bounded telemetry, no free text).
    "product_outcomes": _PURGED_FULL,
    "product_events": _PURGED_FULL,
    "phone_calls": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Call records: metadata + synthesis (transcripts never stored, D-8); "
        "callee_phone decrypted by the telephony service at export time.",
    ),
    "health_samples": _PURGED_FULL,
    "user_skill_states": _PURGED_FULL,
    "skills": _PURGED_FULL,
    "rag_spaces": _PURGED_FULL,
    "attachments": _PURGED_FULL,
    "user_usage_limits": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Per-user quota configuration — settings, not secrets.",
    ),
    "user_channel_bindings": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Channel links (e.g. Telegram chat binding) — the exporter redacts "
        "verification codes if present.",
    ),
    "user_broadcast_reads": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Read receipts of admin broadcasts — trivial but user-scoped.",
    ),
    "account_export_jobs": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Transient export bookkeeping (paths, sizes) — no portability value; "
        "archives on disk are purged with the account.",
    ),
    # ------------------------------------------------------------------
    # User-scoped secret material: purged, never exported.
    # ------------------------------------------------------------------
    "connectors": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Rows carry Fernet-encrypted OAuth credentials/app passwords; "
        "connector configuration has no portability value without them.",
    ),
    "user_mcp_servers": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Rows carry encrypted MCP auth material (tokens, headers).",
    ),
    "health_metric_tokens": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Ingestion token hashes — secret material, never exported.",
    ),
    "user_fcm_tokens": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Push delivery credentials (FCM tokens) — device secrets.",
    ),
    "webauthn_credentials": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="WebAuthn passkey key material (credential id, public key, counter) — "
        "authentication material is never exported.",
    ),
    "user_totp": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Fernet-encrypted TOTP shared secret — authentication material is never exported.",
    ),
    "mfa_backup_codes": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="SHA-256 hashes of single-use MFA backup codes — secret material.",
    ),
    # ------------------------------------------------------------------
    # Cascade children of purged tables (hard-deleted parents ⇒ FK fires).
    # ------------------------------------------------------------------
    "rag_drive_sources": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason="Drive sync source config — exported as part of the space metadata.",
    ),
    "rag_documents": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason="Document metadata; original files exported per arbitration A5.",
    ),
    "rag_chunks": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.EXCLUDED,
        reason="Derived data (chunks/embeddings) — rebuildable, no portability value (A5).",
    ),
    # ------------------------------------------------------------------
    # Billing history: retained post-deletion (ADR-067), exportable usage data.
    # ------------------------------------------------------------------
    "token_usage_logs": TableRule(
        data_class=TableDataClass.BILLING_RETAINED,
        export=ExportPolicy.FULL,
        reason="LLM usage/costs — retained for dispute resolution; already "
        "user-exportable via /usage/export.",
    ),
    "message_token_summary": TableRule(
        data_class=TableDataClass.BILLING_RETAINED,
        export=ExportPolicy.FULL,
        reason="Per-message token aggregates — billing history.",
    ),
    "user_statistics": TableRule(
        data_class=TableDataClass.BILLING_RETAINED,
        export=ExportPolicy.FULL,
        reason="Usage aggregates — billing history.",
    ),
    "google_api_usage_logs": TableRule(
        data_class=TableDataClass.BILLING_RETAINED,
        export=ExportPolicy.FULL,
        reason="Google API usage/costs — retained for dispute resolution.",
    ),
    # ------------------------------------------------------------------
    # Global (non-user) tables: config, pricing, catalogs, admin records.
    # ------------------------------------------------------------------
    "admin_audit_log": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin accountability record — not user-owned data; references "
        "users but documents admin actions.",
    ),
    "admin_broadcasts": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-authored announcements, not user data.",
    ),
    "system_settings": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Instance-wide configuration.",
    ),
    "personalities": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Shared personality catalog.",
    ),
    "personality_translations": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Translations of the shared personality catalog.",
    ),
    "llm_models": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="LLM catalog.",
    ),
    "llm_model_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "currency_exchange_rates": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Exchange-rate reference data.",
    ),
    "google_api_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "image_generation_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "provider_api_keys": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed provider API keys (encrypted) — instance secrets.",
    ),
    "llm_config_overrides": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed LLM configuration overrides.",
    ),
    "connector_global_config": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed connector configuration.",
    ),
}


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
    # Non-content operational preferences.
    "timezone": _PREFERENCE,
    "language": _PREFERENCE,
    "personality_id": _PREFERENCE,
    "weather_use_last_known_location": _PREFERENCE,
    "discovery_enabled": _PREFERENCE,
    # A consent, kept separate from discovery on purpose (ADR-189).
    "peer_email_visible": _PREFERENCE,
    # How the user wants a "360° point" built — a display preference.
    "relation_overview_scope": _PREFERENCE,
    "memory_enabled": _PREFERENCE,
    "health_metrics_agents_enabled": _PREFERENCE,
    "execution_mode": _PREFERENCE,
    "voice_enabled": _PREFERENCE,
    "voice_mode_enabled": _PREFERENCE,
    "voice_stt_mode": _PREFERENCE,
    "tokens_display_enabled": _PREFERENCE,
    "debug_panel_enabled": _PREFERENCE,
    "response_display_mode": _PREFERENCE,
    "theme": _PREFERENCE,
    "color_theme": _PREFERENCE,
    "font_family": _PREFERENCE,
    "interests_enabled": _PREFERENCE,
    "interests_notify_start_hour": _PREFERENCE,
    "interests_notify_end_hour": _PREFERENCE,
    "interests_notify_min_per_day": _PREFERENCE,
    "interests_notify_max_per_day": _PREFERENCE,
    "heartbeat_enabled": _PREFERENCE,
    "heartbeat_min_per_day": _PREFERENCE,
    "heartbeat_max_per_day": _PREFERENCE,
    "heartbeat_push_enabled": _PREFERENCE,
    "heartbeat_notify_start_hour": _PREFERENCE,
    "heartbeat_notify_end_hour": _PREFERENCE,
    # Which sources may interrupt the reader (ADR-197). A setting like its
    # siblings above: it holds source KEYS from a closed registry, never
    # content — nothing personal to scrub, and resetting it would silently
    # re-enable interruptions the user refused.
    "heartbeat_disabled_sources": _PREFERENCE,
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
    "admin_mcp_disabled_servers": _PREFERENCE,
    "briefing_preferences": _PREFERENCE,
    "onboarding_checklist": _PREFERENCE,
    "chat_shortcuts": _PREFERENCE,
}
