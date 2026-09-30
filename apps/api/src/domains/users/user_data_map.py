"""Single source of truth classifying user data across tables.

Every SQLAlchemy table is deliberately classified here; the columns of the
``users`` row itself are classified in ``user_column_map``. The CI guard
``tests/unit/domains/users/test_user_data_map_guard.py`` fails on any
unclassified (or stale) entry and cross-checks the USER_PURGED set against
``account_deletion_service.build_purge_statements``, closing the defect class
where a new user-scoped table silently escapes both the account-deletion purge
(ADR-067) and the GDPR export.

Consumers:
    - Account deletion (ADR-067): purge coverage is asserted against this map.
    - GDPR export: exporters are wired against ``ExportPolicy.FULL``
      entries; ``EXCLUDED`` entries never reach an archive.

It is subject to the logical-SLOC cap like any module: when it outgrows it, a
cohesive table family moves to a module of its own (as the ``users`` columns
did, 2026-09-30).
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
    "relation_debriefs": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "The daily relationship debrief: an LLM synthesis of what the "
            "account already holds about one person. Exported because it IS "
            "the reader's own record of a relationship, purged on deletion "
            "like every source it was written from."
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
    "agent_effects": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Ledger of the external effects performed for this user (ADR-263) — "
            "their own record of what the assistant did, so it leaves with the "
            "archive and dies with the account (owner decision, 2026-09-03)."
        ),
    ),
    "agent_treatments": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Register of what the assistant CONSULTED for this user (ADR-263, "
            "lot 4) — the companion of agent_effects: that one says what was "
            "done, this one what was read to answer. It carries no argument "
            "and no label, so nothing here names a third party; it still "
            "leaves with the archive and dies with the account, because it is "
            "the user's own record of their assistant's work."
        ),
    ),
    "agent_decisions": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Register of the TURNS themselves (ADR-263, lot 6) — the spine the "
            "two others hang off: agent_effects says what was done and "
            "agent_treatments what was read, and both file their rows under a "
            "run_id that this table gives a meaning to. It POINTS at the "
            "request and the answer (SET NULL, so deleting a conversation "
            "leaves a dated tombstone) and copies neither, so it holds no "
            "content of its own. The user's record of their assistant's work: "
            "it leaves with the archive and dies with the account."
        ),
    ),
    "agent_integrity_events": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Gaps in the transparency record itself (ADR-263, lot 8): an effect "
            "performed with no ledger row, a turn whose consultations nobody "
            "collected, a chain that stopped verifying, a sealing pass rolled "
            "back. It holds a bounded classification and no content. Exported "
            "because a user is entitled to know their own record is incomplete, "
            "and purged with the account like the registers it qualifies. Rows "
            "that name no account (a detection with no run context) are "
            "instance-level and stay — they identify nobody."
        ),
    ),
    "ledger_chain": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "The tamper-evident chain over the two registers (ADR-263, lot 5). "
            "One chain per ACCOUNT, and that is the decision the whole design "
            "turns on: deleting an account removes a COMPLETE chain instead of "
            "punching a permanent hole in a shared one, which is how "
            "inalterability and the right to erasure coexist. It holds digests "
            "and identifiers only — never content — so exporting it gives the "
            "user their proof without copying anything the registers already "
            "carry."
        ),
    ),
    "peer_image_shares": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Ledger of images shared with a connection (ADR-316): who, with whom, "
            "which copy — no comment is stored. Exported to both sides and purged "
            "on deletion of either."
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
    # Habits (ADR-214): derived rhythm profile + discrete learned habits.
    # Hours and domain names only — never message content.
    "user_habit_profiles": _PURGED_FULL,
    "user_habits": _PURGED_FULL,
    # Per-day hour counts only (no content) — survives conversation resets
    # by design, purged with the account and by "forget everything".
    "user_activity_days": _PURGED_FULL,
    "heartbeat_notifications": _PURGED_FULL,
    # Anticipated moments (ADR-281): scheduling bookkeeping, not a record.
    # A row says « at this instant there will be something to say about this
    # calendar event » and holds a title, two instants and a score — no
    # attendee, no address, no body. It is EXCLUDED from the export because it
    # is not a trace of what LIA did: a settled row is purged after
    # ``MOMENTS_RETENTION_DAYS``, while the notification it produced lives in
    # ``heartbeat_notifications`` and in ``agent_effects``, both exported.
    # Exporting it would hand someone rows about meetings LIA never mentioned.
    "proactive_moments": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason=(
            "Scheduling bookkeeping for the proactive sweep, self-purging after "
            "the retention. What LIA actually said is exported through "
            "heartbeat_notifications and agent_effects (ADR-281)."
        ),
    ),
    "reminders": _PURGED_FULL,
    "scheduled_actions": _PURGED_FULL,
    "open_loops": _PURGED_FULL,
    # Workboard (ADR-276). Two-sided like the peers tables: a row belongs to
    # the archive when the requester OWNS it or is ASSIGNED it. The purge
    # deletes what the account owns; what it merely HELD is released back to
    # its owner FIRST, by `build_workboard_release` in
    # `users/account_deletion_service.py` — inline there because `users`
    # imports no domain. The `ON DELETE SET NULL` on `assignee_user_id` covers
    # the four paths that hard-delete a users row; account deletion SCRUBS that
    # row instead, so no foreign-key action fires and the statement is the only
    # release there.
    "workboard_tickets": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Tickets the account owns or holds — purged when owned, released "
            "when merely held, exported on both sides."
        ),
    ),
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
    "skill_library_sources": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason=(
            "Where a skill installed from a library came from (ADR-327): the "
            "repository, folder and commit the person chose. Cascades from skills; "
            "exported with its skill."
        ),
    ),
    "user_plugins": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Installed Agent Plugins packages (ADR-225): manifest metadata "
        "the user chose to install — no secrets (the spec forbids them in "
        "packages), portable by nature.",
    ),
    "rag_spaces": _PURGED_FULL,
    "attachments": _PURGED_FULL,
    # The answers a person kept (ADR-282): their own copy, purged with them
    # and handed back in full by the export.
    "message_bookmarks": _PURGED_FULL,
    # The hosts a person allowed a sandbox script to reach (ADR-298): their
    # own decisions, purged with them and handed back by the export.
    "sandbox_egress_grants": _PURGED_FULL,
    # Meeting recording & minutes (ADR-258). The transcript column is
    # Fernet-encrypted at rest (third parties' speech) and decrypted at export
    # time by the account-export builder so the archive stays readable.
    "meetings": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Meeting records: header, minutes and encrypted transcript "
        "(decrypted at export); audio files exported when kept.",
    ),
    "meeting_templates": _PURGED_FULL,
    # The personal radio (ADR-324): the listener's settings, and the sites they
    # added to their newsroom — purged and handed back with them. The same
    # table holds the shipped catalogue (owner_id NULL), which is the
    # instance's: the purge and the export read the owner's rows only.
    "radio_preferences": _PURGED_FULL,
    "radio_feeds": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="The sites a listener added (owner_id = the account); catalogue rows "
        "have no owner and are not user data.",
    ),
    "radio_news_items": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.EXCLUDED,
        reason="Public articles read from the feeds; those of a listener's own site "
        "go with it by FK cascade, and the site itself is what the export hands back.",
    ),
    "meeting_preferences": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason="Per-user meeting preferences (engine, language, retention, auto-email) — settings, not secrets.",
    ),
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
    "admin_broadcast_recipients": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.FULL,
        reason=(
            "Which targeted admin broadcasts were addressed to the account (ADR-312) "
            "— user-scoped addressing, purged with it (its users FK never fires: the "
            "row is scrubbed, not deleted)."
        ),
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
    "oauth_grants": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Shared encrypted provider tokens and account identifiers are purged, never exported.",
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
    "webhook_channels": TableRule(
        data_class=TableDataClass.USER_PURGED,
        export=ExportPolicy.EXCLUDED,
        reason="Google push channel registry (lot H): channel tokens are secret "
        "material and the rows are transient plumbing with no portability value.",
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
    "scheduled_action_runs": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason=(
            "One row per tick of a routine (ADR-265): outcome, served slot, "
            "attempts, error — the user's own execution history, bounded by "
            "retention. Cascades from scheduled_actions AND users."
        ),
    ),
    "workboard_comments": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason=(
            "Comments on a ticket (ADR-276), by the owner, a peer or LIA. "
            "Cascades from workboard_tickets; exported through its ticket."
        ),
    ),
    "workboard_ticket_events": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason=(
            "Append-only ticket history (ADR-276): who changed what, and when "
            "a run ran. Cascades from workboard_tickets; exported with it."
        ),
    ),
    "rag_drive_sources": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason="Drive sync source config — exported as part of the space metadata.",
    ),
    "rag_mail_sources": TableRule(
        data_class=TableDataClass.USER_CASCADE,
        export=ExportPolicy.FULL,
        reason=(
            "Gmail label source config (ADR-262) — which label a space follows, "
            "exported as part of the space metadata; the indexed threads "
            "themselves are rag_documents."
        ),
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
    "health_snapshots": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Platform self-check results (spec 2026-08-27) — no user data, "
        "pruned by the diagnostics job's own retention.",
    ),
    "incidents": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Platform incident memory (spec 2026-08-27) — alert labels and "
        "check evidence only, admin-facing, never user-owned.",
    ),
    "instance_daily_budget": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="One aggregate row per UTC day for the whole instance: no user "
        "column, no per-user attribution, nothing to purge or export.",
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
