"""Pydantic contracts of the meetings API and of the minutes themselves (ADR-258).

The minutes are structured data: ``MeetingReport`` is what the model produces
(validated at write), what the user edits (validated again), and what ONE
serializer renders into Markdown, PDF and email. Sections follow the user's
template (``TemplateSection``); the header (title, participants, when, where)
is fixed and not template-driven.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from src.core.constants import (
    MEETINGS_BULK_MAX,
    MEETINGS_IMPORT_CLOCK_SKEW_SECONDS,
    MEETINGS_TEMPLATE_REF_MAX,
)
from src.core.meeting_reformat import MeetingReformatRequest as MeetingReformatRequest
from src.core.meeting_reports import ActionItem as ActionItem
from src.core.meeting_reports import MeetingPatchRequest as MeetingPatchRequest
from src.core.meeting_reports import MeetingReport as MeetingReport
from src.core.meeting_reports import Participant as Participant
from src.core.meeting_reports import ReportSection as ReportSection
from src.core.meeting_reports import TopicItem as TopicItem
from src.core.meeting_reports import TranscriptLine as TranscriptLine
from src.core.meeting_templates import (
    MAX_TEMPLATE_SECTIONS as MAX_TEMPLATE_SECTIONS,
)
from src.core.meeting_templates import (
    SECTION_KEY_PATTERN as SECTION_KEY_PATTERN,
)
from src.core.meeting_templates import (
    TEMPLATE_REF_PATTERN as TEMPLATE_REF_PATTERN,
)
from src.core.meeting_templates import (
    MeetingTemplateCreate as MeetingTemplateCreate,
)
from src.core.meeting_templates import (
    MeetingTemplateListResponse as MeetingTemplateListResponse,
)
from src.core.meeting_templates import (
    MeetingTemplateResponse as MeetingTemplateResponse,
)
from src.core.meeting_templates import (
    MeetingTemplateSummary as MeetingTemplateSummary,
)
from src.core.meeting_templates import (
    MeetingTemplateUpdate as MeetingTemplateUpdate,
)
from src.core.meeting_templates import (
    SectionKind as SectionKind,
)
from src.core.meeting_templates import (
    TemplateCategory as TemplateCategory,
)
from src.core.meeting_templates import (
    TemplateSection as TemplateSection,
)
from src.core.meeting_templates import (
    TemplateSelection as TemplateSelection,
)
from src.domains.meetings.models import (
    MeetingAudioFormat,
    MeetingIndexState,
    MeetingStage,
    MeetingStatus,
    MeetingSttEnginePreference,
    MeetingSttProvider,
    is_import,
)
from src.domains.shared.schemas import TimezoneValidatorMixin
from src.infrastructure.llm.decision_types import DecisionCharge

#: Upper bound of sections a template may carry — enough for any minutes
#: format, small enough for one structured-output call.
#: A stable slug the model echoes back; the label is what the user reads.
#: ``auto`` or an ISO-639-1 code; the engines validate the code themselves.
LANGUAGE_PATTERN = r"^(auto|[a-z]{2})$"
#: ``builtin:<catalogue key>`` or ``user:<uuid>`` — the two template identities (ADR-259).


# ----------------------------------------------------------------------------
# Template
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Minutes
# ----------------------------------------------------------------------------


class TranscriptTurn(BaseModel):
    """One speaker turn of the transcript (seconds from the recording start)."""

    speaker: str = Field(description="Speaker label (diarized) or the single-speaker label.")
    start: float = Field(ge=0, description="Turn start, seconds.")
    end: float = Field(ge=0, description="Turn end, seconds.")
    text: str = Field(description="What was said.")


# ----------------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------------


class MeetingGeolocation(BaseModel):
    """Position at recording start, when the browser granted it."""

    lat: float = Field(ge=-90, le=90, description="Latitude.")
    lon: float = Field(ge=-180, le=180, description="Longitude.")
    accuracy_m: float | None = Field(default=None, ge=0, description="Accuracy in meters.")


class MeetingStartRequest(BaseModel):
    """Start a recording."""

    audio_format: MeetingAudioFormat = Field(description="Segment format for the whole recording.")
    language: str = Field(
        default="auto",
        pattern=LANGUAGE_PATTERN,
        description="'auto' or an ISO-639-1 hint for the transcription.",
    )
    timezone: str = Field(
        min_length=1, max_length=64, description="IANA timezone of the recording device."
    )
    geolocation: MeetingGeolocation | None = Field(
        default=None, description="Position at start, if granted."
    )
    template_ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=TEMPLATE_REF_PATTERN,
        description="Minutes template chosen for THIS meeting; null = preference, then automatic.",
    )

    @field_validator("timezone")
    @classmethod
    def _iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA zone") from exc
        return value

    @field_validator("audio_format")
    @classmethod
    def _live_format(cls, value: MeetingAudioFormat) -> MeetingAudioFormat:
        if is_import(value):
            raise ValueError("a recording streams a live format; a file is imported")
        return value


class MeetingImportRequest(TimezoneValidatorMixin, BaseModel):
    """Import a meeting from a file (owner request 2026-10-24)."""

    audio_format: MeetingAudioFormat = Field(
        description="The file's format: import_wav, import_mp3 or import_m4a."
    )
    size_bytes: int = Field(ge=1, description="The file's size; refused above the published cap.")
    recorded_at: AwareDatetime = Field(
        description="When the meeting began, with its offset — never in the future."
    )
    timezone: str = Field(min_length=1, max_length=64, description="IANA zone it was held in.")
    language: str = Field(
        default="auto",
        pattern=LANGUAGE_PATTERN,
        description="'auto' or an ISO-639-1 hint for the transcription.",
    )
    template_ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=TEMPLATE_REF_PATTERN,
        description="Minutes template chosen for THIS meeting; null = preference, then automatic.",
    )

    @field_validator("audio_format")
    @classmethod
    def _file_format(cls, value: MeetingAudioFormat) -> MeetingAudioFormat:
        if not is_import(value):
            raise ValueError("an import carries a file format")
        return value

    @field_validator("recorded_at")
    @classmethod
    def _in_the_past(cls, value: datetime) -> datetime:
        latest = datetime.now(UTC) + timedelta(seconds=MEETINGS_IMPORT_CLOCK_SKEW_SECONDS)
        if value > latest:
            raise ValueError("a meeting cannot have been recorded in the future")
        return value


class MeetingImportComplete(BaseModel):
    """Every chunk is sent: hand the file to processing."""

    chunk_count: int = Field(ge=1, description="Chunks the client sent, numbered from 0.")


class MeetingStopRequest(BaseModel):
    """Stop the recording and hand the segments to processing."""

    segment_count: int = Field(ge=0, description="Segments the client believes it uploaded.")
    allow_gaps: bool = Field(
        default=False,
        description="Finalize even when some segments never arrived (gaps are recorded).",
    )


class MeetingPreferencesUpdate(BaseModel):
    """Per-user meeting preferences (PUT semantics, every field explicit)."""

    stt_engine: MeetingSttEnginePreference = Field(description="Engine preference.")
    language: str = Field(pattern=LANGUAGE_PATTERN, description="'auto' or ISO-639-1.")
    auto_email: bool = Field(description="Email the minutes to the user when ready.")
    keep_audio_hours: int = Field(
        ge=0, description="Keep the audio this long after processing; 0 = delete."
    )
    default_template_ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=TEMPLATE_REF_PATTERN,
        description="Template applied to every meeting; null = LIA chooses from the transcript.",
    )


# ----------------------------------------------------------------------------
# Responses
# ----------------------------------------------------------------------------


class EngineInfo(BaseModel):
    """The transcription engine resolved for a recording — shown before it starts."""

    provider: MeetingSttProvider = Field(description="Engine that will transcribe.")
    model: str | None = Field(default=None, description="Model name when remote.")
    diarized: bool = Field(description="Whether speakers will be separated.")
    cost_per_hour_eur: float | None = Field(
        default=None, description="Provider price per audio hour, EUR (null when free/unknown)."
    )
    local_rtf_estimate: float | None = Field(
        default=None, description="Local engine seconds per audio second (null when remote)."
    )


class MeetingLimits(BaseModel):
    """Every bound the server enforces on a recording, published to the client."""

    segment_seconds: int = Field(description="Upload cadence the client must follow.")
    segment_max_seconds: int = Field(description="Longest single segment accepted.")
    segment_max_bytes: int = Field(description="Largest segment body accepted.")
    max_duration_minutes: int = Field(description="Hard cap on the recording length.")
    silence_prompt_minutes: int = Field(description="Silence before the client asks to continue.")


class MeetingStartResponse(BaseModel):
    """What the client needs to record."""

    id: uuid.UUID
    status: MeetingStatus
    started_at: datetime
    engine: EngineInfo
    limits: MeetingLimits


class MeetingImportLimits(BaseModel):
    """Every bound an import is held to, readable before a byte is sent (ADR-184)."""

    max_bytes: int = Field(description="Largest file accepted.")
    chunk_max_bytes: int = Field(description="Largest chunk one request may carry.")
    max_duration_minutes: int = Field(description="Longest audio accepted (judged on the file).")


class MeetingImportResponse(BaseModel):
    """What the client needs to upload the file."""

    id: uuid.UUID
    status: MeetingStatus
    started_at: datetime
    engine: EngineInfo
    limits: MeetingImportLimits


class MeetingSegmentAck(BaseModel):
    """Acknowledgement of one segment."""

    sequence: int
    segment_count: int
    audio_bytes: int
    status: MeetingStatus


class MeetingPreferencesResponse(MeetingPreferencesUpdate):
    """Current preferences plus the admin ceiling the client must respect."""

    keep_audio_hours_max: int = Field(description="Admin ceiling on keep_audio_hours.")


class MeetingSummary(BaseModel):
    """List item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: MeetingStatus
    stage: MeetingStage | None = None
    title: str | None = None
    started_at: datetime
    stopped_at: datetime | None = None
    audio_duration_seconds: float | None = None
    participants_count: int = 0
    action_items_count: int = 0
    index_state: MeetingIndexState | None = None
    stt_provider: MeetingSttProvider | None = None
    total_cost_eur: float | None = Field(
        default=None,
        description="Priced transcription, selection and minutes in EUR; None if none were priced.",
    )
    last_error_code: str | None = None
    template_ref: str | None = None
    template_name: str | None = None
    template_selection: TemplateSelection | None = None
    source_meeting_id: uuid.UUID | None = None


class MeetingListResponse(BaseModel):
    """A page of meetings with the EXACT total (ADR-185)."""

    items: list[MeetingSummary]
    total: int = Field(description="Exact number of meetings for this user.")
    limit: int
    offset: int


class MeetingDetailResponse(BaseModel):
    """Everything the meeting page shows."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: MeetingStatus
    stage: MeetingStage | None = None
    started_at: datetime
    stopped_at: datetime | None = None
    last_segment_at: datetime | None = None
    client_timezone: str
    audio_format: MeetingAudioFormat
    segment_count: int
    audio_duration_seconds: float | None = None
    audio_gaps: int = 0
    audio_kept_until: datetime | None = Field(default=None, alias="keep_audio_until")
    audio_purged_at: datetime | None = None
    location_lat: float | None = None
    location_lon: float | None = None
    location_label: str | None = None
    calendar_event_id: str | None = None
    stt_provider: MeetingSttProvider | None = None
    stt_model: str | None = None
    stt_detected_language: str | None = None
    stt_diarized: bool = False
    stt_cost_eur: float | None = None
    synthesis_model: str | None = None
    synthesis_tokens_in: int = 0
    synthesis_tokens_out: int = 0
    synthesis_tokens_cache: int = 0
    synthesis_cost_eur: float | None = Field(
        default=None, description="LLM cost of the minutes (every synthesis pass)."
    )
    template_selection_usage: list[DecisionCharge] = Field(
        default_factory=list, description="Native selection charges, separate from synthesis."
    )
    total_cost_eur: float | None = Field(
        default=None,
        description="Transcription + minutes, in EUR; None while nothing priced was spent.",
    )
    has_transcript: bool = False
    report: MeetingReport | None = None
    report_is_edited: bool = False
    report_edited_at: datetime | None = None
    template_snapshot: list[TemplateSection] | None = None
    index_state: MeetingIndexState | None = None
    indexed_at: datetime | None = None
    email_sent_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    attempts: int = Field(default=0, description="Claims spent on the current retry budget.")
    max_attempts: int = Field(
        default=0,
        description=(
            "Claims the budget allows before the meeting is dead-lettered "
            "(published because it is enforced)."
        ),
    )
    worker_stale: bool = Field(
        default=False,
        description=(
            "True while `processing` under no live lease: the worker stopped responding, "
            "the reaper requeues or dead-letters the job, and the meeting may be deleted."
        ),
    )
    template_ref: str | None = None
    template_name: str | None = None
    template_selection: TemplateSelection | None = None
    template_selection_reason: str | None = None
    source_meeting_id: uuid.UUID | None = None
    derived_count: int = Field(
        default=0, description="Minutes produced from this meeting's transcript (reformat 'new')."
    )
    transcript: list[TranscriptTurn] | None = Field(
        default=None, description="Only when requested (?include_transcript=1)."
    )


class MeetingActionResponse(BaseModel):
    """Result of a lifecycle action (stop / resume / retry / regenerate / reset)."""

    id: uuid.UUID
    status: MeetingStatus
    stage: MeetingStage | None = None
    detail: dict[str, Any] | None = Field(
        default=None, description="Action-specific payload (e.g. missing segment sequences)."
    )


class MeetingReformatResponse(BaseModel):
    """The meeting that is being written: the same one, or the new one."""

    id: uuid.UUID
    status: MeetingStatus
    stage: MeetingStage | None = None
    source_meeting_id: uuid.UUID | None = None


# ----------------------------------------------------------------------------
# Bulk operations (ADR-259)
# ----------------------------------------------------------------------------


class MeetingBulkDeleteRequest(BaseModel):
    """Delete several meetings; each id is answered individually."""

    ids: list[uuid.UUID] = Field(
        min_length=1, max_length=MEETINGS_BULK_MAX, description="Meeting ids to delete."
    )


class TemplateRefsRequest(BaseModel):
    """Several template refs to act on together (ADR-259)."""

    refs: list[str] = Field(
        ...,
        min_length=1,
        max_length=MEETINGS_BULK_MAX,
        description="Template refs (`builtin:<key>` or `user:<uuid>`); duplicates are ignored.",
    )


class TemplateBulkSkipped(BaseModel):
    """One ref a template batch left untouched, with the stable reason."""

    ref: str = Field(description="The ref as requested.")
    code: str = Field(
        description=(
            "Stable reason: template_not_found, template_ref_invalid, template_readonly, "
            "template_limit_reached, duplicate_failed, delete_failed."
        )
    )


class MeetingTemplateBulkDuplicateResponse(BaseModel):
    """What « add to my templates » did for every ref."""

    created: list[MeetingTemplateSummary] = Field(description="The new rows, in request order.")
    skipped: list[TemplateBulkSkipped] = Field(
        description="Refs left untouched, each with its reason."
    )


class MeetingTemplateBulkDeleteResponse(BaseModel):
    """What a batch delete of user templates did."""

    deleted: list[str] = Field(description="Refs deleted, in request order.")
    skipped: list[TemplateBulkSkipped] = Field(
        description="Refs left untouched, each with its reason."
    )
    preference_reset: bool = Field(
        description="True when the default-format preference pointed at a deleted row and went back to automatic."
    )


class BulkSkipped(BaseModel):
    """One id the bulk operation did not process, with the stable reason."""

    id: uuid.UUID
    code: str = Field(
        description="Stable reason: meeting_not_found, meeting_in_progress, delete_failed."
    )


class MeetingBulkDeleteResponse(BaseModel):
    """What happened to every id — never a partial success disguised as a success."""

    deleted: list[uuid.UUID] = Field(description="Ids deleted, in request order.")
    skipped: list[BulkSkipped] = Field(description="Ids left untouched, each with its reason.")
