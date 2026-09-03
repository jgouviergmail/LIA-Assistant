"""Pydantic contracts of the meetings API and of the minutes themselves (ADR-258).

The minutes are structured data: ``MeetingReport`` is what the model produces
(validated at write), what the user edits (validated again), and what ONE
serializer renders into Markdown, PDF and email. Sections follow the user's
template (``TemplateSection``); the header (title, participants, when, where)
is fixed and not template-driven.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domains.meetings.models import (
    MeetingAudioFormat,
    MeetingIndexState,
    MeetingStage,
    MeetingStatus,
    MeetingSttEnginePreference,
    MeetingSttProvider,
)

#: Upper bound of sections a template may carry — enough for any minutes
#: format, small enough for one structured-output call.
MAX_TEMPLATE_SECTIONS = 12
#: A stable slug the model echoes back; the label is what the user reads.
SECTION_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,39}$"
#: ``auto`` or an ISO-639-1 code; the engines validate the code themselves.
LANGUAGE_PATTERN = r"^(auto|[a-z]{2})$"


class SectionKind(str, Enum):
    """How a section is filled and rendered."""

    PARAGRAPH = "paragraph"
    BULLETS = "bullets"
    TOPICS = "topics"
    ACTION_ITEMS = "action_items"


# ----------------------------------------------------------------------------
# Template
# ----------------------------------------------------------------------------


class TemplateSection(BaseModel):
    """One section of a minutes template."""

    key: str = Field(
        pattern=SECTION_KEY_PATTERN,
        description="Stable slug the model echoes back (2-40 chars, [a-z0-9_]).",
    )
    label: str = Field(min_length=1, max_length=80, description="Heading shown in the minutes.")
    instruction: str = Field(
        min_length=1,
        max_length=600,
        description="What the model must put in this section.",
    )
    kind: SectionKind = Field(description="Shape of the content (paragraph, bullets, ...).")


class MeetingTemplateResponse(BaseModel):
    """The template in force for the user — the default until they edit it."""

    id: uuid.UUID | None = Field(
        default=None, description="Row id, or null while the built-in default applies."
    )
    name: str = Field(description="Template name.")
    sections: list[TemplateSection] = Field(description="Ordered sections.")
    is_builtin_default: bool = Field(description="True when no user edit exists yet.")


class MeetingTemplateUpdate(BaseModel):
    """Replace the user's template (PUT semantics)."""

    name: str = Field(min_length=1, max_length=120, description="Template name.")
    sections: list[TemplateSection] = Field(
        min_length=1, max_length=MAX_TEMPLATE_SECTIONS, description="Ordered sections."
    )

    @field_validator("sections")
    @classmethod
    def _unique_keys(cls, sections: list[TemplateSection]) -> list[TemplateSection]:
        keys = [section.key for section in sections]
        if len(set(keys)) != len(keys):
            raise ValueError("section keys must be unique")
        return sections


# ----------------------------------------------------------------------------
# Minutes
# ----------------------------------------------------------------------------


class Participant(BaseModel):
    """One person in the meeting, as far as the recording tells."""

    label: str = Field(
        min_length=1,
        max_length=40,
        description="Stable speaker label from diarization (e.g. 'S1'), or a free label.",
    )
    name: str | None = Field(default=None, max_length=120, description="Name when established.")
    role: str | None = Field(default=None, max_length=120, description="Role when stated.")


class TopicItem(BaseModel):
    """One discussed topic with its own summary."""

    title: str = Field(min_length=1, max_length=200, description="Topic title.")
    summary: str = Field(min_length=1, max_length=4000, description="What was said about it.")


class ActionItem(BaseModel):
    """One action, task or commitment."""

    description: str = Field(min_length=1, max_length=1000, description="What must be done.")
    owner: str | None = Field(default=None, max_length=120, description="Who, when named.")
    due_date: str | None = Field(
        default=None,
        max_length=40,
        description="Absolute deadline (YYYY-MM-DD when precise) or null.",
    )


class ReportSection(BaseModel):
    """One filled section — exactly one payload shape is meaningful per kind."""

    key: str = Field(pattern=SECTION_KEY_PATTERN, description="Template section key.")
    label: str = Field(min_length=1, max_length=80, description="Heading (from the template).")
    kind: SectionKind = Field(description="Shape of the content.")
    paragraph: str | None = Field(default=None, max_length=8000, description="For 'paragraph'.")
    bullets: list[str] = Field(default_factory=list, description="For 'bullets'.")
    topics: list[TopicItem] = Field(default_factory=list, description="For 'topics'.")
    action_items: list[ActionItem] = Field(default_factory=list, description="For 'action_items'.")

    def is_empty(self) -> bool:
        """Whether the section carries no content for its kind."""
        match self.kind:
            case SectionKind.PARAGRAPH:
                return not (self.paragraph or "").strip()
            case SectionKind.BULLETS:
                return not any(item.strip() for item in self.bullets)
            case SectionKind.TOPICS:
                return not self.topics
            case SectionKind.ACTION_ITEMS:
                return not self.action_items


class MeetingReport(BaseModel):
    """The minutes: fixed header fields + the template's sections, in order."""

    title: str = Field(min_length=1, max_length=200, description="Relevant meeting title.")
    participants: list[Participant] = Field(default_factory=list, description="Participants.")
    sections: list[ReportSection] = Field(default_factory=list, description="Filled sections.")

    @field_validator("sections")
    @classmethod
    def _unique_section_keys(cls, sections: list[ReportSection]) -> list[ReportSection]:
        keys = [section.key for section in sections]
        if len(set(keys)) != len(keys):
            raise ValueError("report section keys must be unique")
        return sections


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

    @field_validator("timezone")
    @classmethod
    def _iana_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA zone") from exc
        return value


class MeetingStopRequest(BaseModel):
    """Stop the recording and hand the segments to processing."""

    segment_count: int = Field(ge=0, description="Segments the client believes it uploaded.")
    allow_gaps: bool = Field(
        default=False,
        description="Finalize even when some segments never arrived (gaps are recorded).",
    )


class MeetingPatchRequest(BaseModel):
    """Edit the minutes (partial). Every provided field replaces the current one."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    participants: list[Participant] | None = Field(default=None)
    sections: list[ReportSection] | None = Field(default=None)
    location_label: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _something_to_change(self) -> MeetingPatchRequest:
        if (
            self.title is None
            and self.participants is None
            and self.sections is None
            and self.location_label is None
        ):
            raise ValueError("nothing to update")
        return self


class MeetingPreferencesUpdate(BaseModel):
    """Per-user meeting preferences (PUT semantics, every field explicit)."""

    stt_engine: MeetingSttEnginePreference = Field(description="Engine preference.")
    language: str = Field(pattern=LANGUAGE_PATTERN, description="'auto' or ISO-639-1.")
    auto_email: bool = Field(description="Email the minutes to the user when ready.")
    keep_audio_hours: int = Field(
        ge=0, description="Keep the audio this long after processing; 0 = delete."
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
        description="Transcription + minutes, in EUR; None while nothing priced was spent.",
    )
    last_error_code: str | None = None


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
