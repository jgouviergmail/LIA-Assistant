"""SQLAlchemy models of the meetings bounded context (ADR-258).

Three tables:

- ``meetings`` — one recording and everything derived from it. The row IS the
  durable job (ADR-129 pattern): ``status`` carries the lifecycle, the
  lease/heartbeat/attempts columns carry the claim, and every transition is an
  atomic conditional UPDATE in the repository. The transcript rests
  Fernet-encrypted (third parties' speech); the minutes are JSON validated by
  ``schemas.MeetingReport`` on both write and read.
- ``meeting_templates`` — the user's OWN minutes templates (ADR-259): several
  per user, each with a category and a free name; the built-in templates live
  in code (``template_catalogue.py``) and are referenced as ``builtin:<key>``.
- ``meeting_preferences`` — one row per user: engine preference, language,
  audio retention choice, auto-email, default template reference (NULL =
  LIA chooses from the transcript).

Enum columns use ``native_enum=False``, which stores the member NAME in upper
case (``'RECORDING'``) — every raw-SQL predicate must use the names, the same
trap the telephony domain documents.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class MeetingStatus(str, Enum):
    """Lifecycle of a meeting — the durable job state.

    ``recording`` → ``stopped`` → ``processing`` → ``ready`` | ``failed``;
    ``recording`` → ``interrupted`` (no segment for a while) → ``recording``
    (a segment arrives) or ``stopped`` (the user finalizes what exists).
    """

    RECORDING = "recording"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MeetingStage(str, Enum):
    """Where a ``processing`` meeting stands — shown to the user as progress."""

    NORMALIZING = "normalizing"
    TRANSCRIBING = "transcribing"
    SYNTHESIZING = "synthesizing"
    INDEXING = "indexing"


class MeetingAudioFormat(str, Enum):
    """What the client sends. Fixed at start for the whole recording."""

    PCM_S16LE_16 = "pcm_s16le_16"
    WEBM_OPUS = "webm_opus"
    OGG_OPUS = "ogg_opus"


class MeetingSttProvider(str, Enum):
    """Which transcription engine produced (or will produce) the transcript."""

    ELEVENLABS = "elevenlabs"
    OPENAI = "openai"
    LOCAL = "local"


class MeetingSttEnginePreference(str, Enum):
    """The user's engine preference; ``auto`` = first engine with a key, then local."""

    AUTO = "auto"
    REMOTE = "remote"
    LOCAL = "local"


class MeetingIndexState(str, Enum):
    """Whether the minutes reached the « Réunions » knowledge space."""

    PENDING = "pending"
    INDEXED = "indexed"
    ERROR = "error"
    DISABLED = "disabled"


# Predicate of the "one recording per user" partial unique index. NAME, not
# value: native_enum=False stores 'RECORDING'.
ACTIVE_RECORDING_STATUS_SQL = "status = 'RECORDING'"


class Meeting(BaseModel):
    """A recorded meeting and everything derived from it (ADR-258).

    PII policy: ``transcript_encrypted`` is Fernet-encrypted by the service;
    ``report_*`` hold the user's own minutes; ``location_*`` are the user's
    position at start. Logs carry ids, counts and codes — never these columns.
    """

    __tablename__ = "meetings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[MeetingStatus] = mapped_column(
        SAEnum(MeetingStatus, native_enum=False, length=20),
        nullable=False,
        default=MeetingStatus.RECORDING,
        index=True,
    )
    stage: Mapped[MeetingStage | None] = mapped_column(
        SAEnum(MeetingStage, native_enum=False, length=20), nullable=True
    )

    # --- audio ---------------------------------------------------------------
    audio_format: Mapped[MeetingAudioFormat] = mapped_column(
        SAEnum(MeetingAudioFormat, native_enum=False, length=20), nullable=False
    )
    segment_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    audio_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    audio_gaps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Segments the client never delivered (the minutes carry a notice when > 0)",
    )
    audio_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Normalized audio, relative to the meetings root"
    )
    audio_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    keep_audio_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Retention deadline when the user kept the audio; NULL = purge after processing",
    )

    # --- when and where ------------------------------------------------------
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_segment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Recording heartbeat"
    )
    client_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- transcription -------------------------------------------------------
    stt_provider: Mapped[MeetingSttProvider | None] = mapped_column(
        SAEnum(MeetingSttProvider, native_enum=False, length=20), nullable=True
    )
    stt_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stt_language_hint: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stt_detected_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stt_diarized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    stt_audio_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    stt_cost_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    transcript_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Fernet of the JSON turns [{speaker,start,end,text}]"
    )
    transcript_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- enrichment ----------------------------------------------------------
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- which template wrote the minutes (ADR-259) --------------------------
    template_ref: Mapped[str | None] = mapped_column(
        String(80), nullable=True, comment="builtin:<key> | user:<uuid> — what produced report_*"
    )
    template_name: Mapped[str | None] = mapped_column(
        String(120), nullable=True, comment="Snapshot of the template name at synthesis time"
    )
    template_selection: Mapped[str | None] = mapped_column(
        String(12), nullable=True, comment="auto | user | preference (TemplateSelection)"
    )
    template_selection_reason: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="The model's one-line justification when auto"
    )
    source_meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"),
        nullable=True,
        comment="New minutes produced from another meeting's transcript (reformat mode 'new')",
    )

    # --- minutes -------------------------------------------------------------
    # What the minutes cost in LLM tokens (initial synthesis + every rebuild, the
    # condense passes included). The billing truth is token_usage_logs (linked by
    # run_id); these columns are the per-meeting display and its exact total.
    synthesis_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    synthesis_tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    synthesis_tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    synthesis_tokens_cache: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    synthesis_cost_eur: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="None = no administered price for the model"
    )
    template_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    report_generated: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True, comment="Immutable model output"
    )
    report_current: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True, comment="What the user sees and edits"
    )
    report_edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- knowledge space -----------------------------------------------------
    rag_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rag_documents.id", ondelete="SET NULL"), nullable=True
    )
    index_state: Mapped[MeetingIndexState | None] = mapped_column(
        SAEnum(MeetingIndexState, native_enum=False, length=20), nullable=True
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- delivery and errors -------------------------------------------------
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- durable job (ADR-129 pattern) ---------------------------------------
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_meetings_user_started", "user_id", "started_at"),
        # Reaper scan: stuck jobs by lease, stale recordings by heartbeat.
        Index("ix_meetings_status_lease", "status", "lease_expires_at"),
        Index("ix_meetings_status_last_segment", "status", "last_segment_at"),
        Index("ix_meetings_source", "source_meeting_id"),
        # Exactly one live recording per user, enforced by the database.
        Index(
            "uq_meetings_one_recording_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(ACTIVE_RECORDING_STATUS_SQL),
        ),
    )

    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, user_id={self.user_id}, status={self.status})>"


class MeetingTemplate(BaseModel):
    """One of the user's own minutes templates — ordered sections the model must fill.

    ADR-259: a user keeps several (bounded by ``MEETINGS_MAX_USER_TEMPLATES``),
    each in a category; the one applied by default is a preference
    (``MeetingPreference.default_template_ref``), never a flag on the row.
    Built-in templates are not rows: they live in ``template_catalogue.py``.
    """

    __tablename__ = "meeting_templates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="custom",
        server_default=text("'custom'"),
        comment="TemplateCategory value; 'custom' unless the user files it elsewhere",
    )
    builtin_key: Mapped[str | None] = mapped_column(
        String(60), nullable=True, comment="The built-in this row was duplicated from, if any"
    )
    sections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, comment="[{key, label, instruction, kind}] validated by schemas"
    )


class MeetingPreference(BaseModel):
    """Per-user meeting preferences (one row per user, created on first write)."""

    __tablename__ = "meeting_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stt_engine: Mapped[MeetingSttEnginePreference] = mapped_column(
        SAEnum(MeetingSttEnginePreference, native_enum=False, length=20),
        nullable=False,
        default=MeetingSttEnginePreference.AUTO,
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="auto", server_default=text("'auto'")
    )
    auto_email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    keep_audio_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="0 = delete the audio after processing; bounded by the admin ceiling",
    )
    default_template_ref: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        comment="builtin:<key> | user:<uuid> applied to every meeting; NULL = LIA chooses (ADR-259)",
    )
