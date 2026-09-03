"""Meeting recording & structured minutes (ADR-258).

Three tables for the meetings bounded context plus one column on ``rag_spaces``:

- ``meetings`` — one recording and everything derived from it; the row is the
  durable job (status + lease/heartbeat/attempts). The partial unique index
  ``uq_meetings_one_recording_per_user`` is the concurrency contract: a second
  start while one recording is live fails at the database, never SELECT-then-check.
- ``meeting_templates`` — the user's minutes structure (one default per user).
- ``meeting_preferences`` — one row per user.
- ``rag_spaces.kind`` — the role of a space another domain manages by identity
  ('meetings'); unique per (user_id, kind) where set, so the auto-created
  « Réunions » space is found by kind whatever the user renames it to.

Enum columns are ``native_enum=False`` (member NAME stored, upper case): every
raw-SQL predicate uses the names — ``status = 'RECORDING'``.

All tables are inert while MEETINGS_ENABLED is false (nothing reads or writes
them), so this migration is safe on every deployment.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-09-02 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> sa.Enum:
    """Non-native enum column type, matching the models (``native_enum=False``)."""
    return sa.Enum(*values, name=name, native_enum=False, length=20)


def upgrade() -> None:
    """Create the meetings tables, their indexes and ``rag_spaces.kind``."""
    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "meetingstatus",
                "RECORDING",
                "INTERRUPTED",
                "STOPPED",
                "PROCESSING",
                "READY",
                "FAILED",
            ),
            nullable=False,
        ),
        sa.Column(
            "stage",
            _enum("meetingstage", "NORMALIZING", "TRANSCRIBING", "SYNTHESIZING", "INDEXING"),
            nullable=True,
        ),
        sa.Column(
            "audio_format",
            _enum("meetingaudioformat", "PCM_S16LE_16", "WEBM_OPUS", "OGG_OPUS"),
            nullable=False,
        ),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("audio_duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_gaps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "audio_path",
            sa.String(length=500),
            nullable=True,
            comment="Normalized audio, relative to the meetings root",
        ),
        sa.Column("audio_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "keep_audio_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Retention deadline when the user kept the audio; NULL = purge after processing",
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_segment_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Recording heartbeat",
        ),
        sa.Column("client_timezone", sa.String(length=64), nullable=False),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_lon", sa.Float(), nullable=True),
        sa.Column("location_accuracy_m", sa.Float(), nullable=True),
        sa.Column("location_label", sa.String(length=255), nullable=True),
        sa.Column(
            "stt_provider",
            _enum("meetingsttprovider", "ELEVENLABS", "OPENAI", "LOCAL"),
            nullable=True,
        ),
        sa.Column("stt_model", sa.String(length=100), nullable=True),
        sa.Column("stt_language_hint", sa.String(length=10), nullable=True),
        sa.Column("stt_detected_language", sa.String(length=10), nullable=True),
        sa.Column("stt_diarized", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("stt_audio_seconds", sa.Float(), nullable=True),
        sa.Column("stt_cost_eur", sa.Float(), nullable=True),
        sa.Column(
            "transcript_encrypted",
            sa.Text(),
            nullable=True,
            comment="Fernet of the JSON turns [{speaker,start,end,text}]",
        ),
        sa.Column("transcript_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("calendar_provider", sa.String(length=50), nullable=True),
        sa.Column("synthesis_model", sa.String(length=100), nullable=True),
        sa.Column("synthesis_tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synthesis_tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synthesis_tokens_cache", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "synthesis_cost_eur",
            sa.Float(),
            nullable=True,
            comment="None = no administered price for the model",
        ),
        sa.Column("template_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "report_generated",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
            comment="Immutable model output",
        ),
        sa.Column(
            "report_current",
            postgresql.JSONB(none_as_null=True),
            nullable=True,
            comment="What the user sees and edits",
        ),
        sa.Column("report_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rag_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rag_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "index_state",
            _enum("meetingindexstate", "PENDING", "INDEXED", "ERROR", "DISABLED"),
            nullable=True,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_meetings_user_id", "meetings", ["user_id"])
    op.create_index("ix_meetings_status", "meetings", ["status"])
    op.create_index("ix_meetings_user_started", "meetings", ["user_id", "started_at"])
    op.create_index("ix_meetings_status_lease", "meetings", ["status", "lease_expires_at"])
    op.create_index("ix_meetings_status_last_segment", "meetings", ["status", "last_segment_at"])
    op.create_index(
        "uq_meetings_one_recording_per_user",
        "meetings",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RECORDING'"),
    )

    op.create_table(
        "meeting_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "sections",
            postgresql.JSONB(),
            nullable=False,
            comment="[{key, label, instruction, kind}] validated by schemas",
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_meeting_templates_user_id", "meeting_templates", ["user_id"])
    op.create_index(
        "uq_meeting_templates_one_default_per_user",
        "meeting_templates",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )

    op.create_table(
        "meeting_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stt_engine",
            _enum("meetingsttenginepreference", "AUTO", "REMOTE", "LOCAL"),
            nullable=False,
        ),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="'auto'"),
        sa.Column("auto_email", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "keep_audio_hours",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="0 = delete the audio after processing; bounded by the admin ceiling",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_meeting_preferences_user_id"),
    )

    op.add_column(
        "rag_spaces",
        sa.Column(
            "kind",
            sa.String(length=30),
            nullable=True,
            comment=(
                "Role of a space another domain manages by identity rather than by name "
                "('meetings', ADR-258). NULL for every space the user created. The "
                "user may still rename it; the owning domain finds it by kind. Unique "
                "per (user_id, kind) — partial index managed in Alembic."
            ),
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_rag_spaces_user_kind "
        "ON rag_spaces (user_id, kind) WHERE kind IS NOT NULL"
    )


def downgrade() -> None:
    """Drop the meetings tables and ``rag_spaces.kind``."""
    op.execute("DROP INDEX IF EXISTS uq_rag_spaces_user_kind")
    op.drop_column("rag_spaces", "kind")

    op.drop_table("meeting_preferences")

    op.drop_index("uq_meeting_templates_one_default_per_user", table_name="meeting_templates")
    op.drop_index("ix_meeting_templates_user_id", table_name="meeting_templates")
    op.drop_table("meeting_templates")

    op.drop_index("uq_meetings_one_recording_per_user", table_name="meetings")
    op.drop_index("ix_meetings_status_last_segment", table_name="meetings")
    op.drop_index("ix_meetings_status_lease", table_name="meetings")
    op.drop_index("ix_meetings_user_started", table_name="meetings")
    op.drop_index("ix_meetings_status", table_name="meetings")
    op.drop_index("ix_meetings_user_id", table_name="meetings")
    op.drop_table("meetings")
