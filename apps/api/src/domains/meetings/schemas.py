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
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import MEETINGS_BULK_MAX, MEETINGS_TEMPLATE_REF_MAX
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
#: ``builtin:<catalogue key>`` or ``user:<uuid>`` — the two template identities (ADR-259).
TEMPLATE_REF_PATTERN = r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-fA-F-]{36})$"


class SectionKind(str, Enum):
    """How a section is filled and rendered."""

    PARAGRAPH = "paragraph"
    BULLETS = "bullets"
    TOPICS = "topics"
    ACTION_ITEMS = "action_items"
    #: The whole exchange, turn by turn, rewritten under the section's
    #: instruction (ADR-259) — filled part by part, never by the single call.
    TRANSCRIPT = "transcript"


class TemplateCategory(str, Enum):
    """Where a template is filed in the library (ADR-259)."""

    CUSTOM = "custom"
    MEETING = "meeting"
    TRANSCRIPT = "transcript"
    ANALYSIS = "analysis"
    BUSINESS = "business"
    TECHNICAL = "technical"
    PERSONAL = "personal"
    LEARNING = "learning"


class TemplateSelection(str, Enum):
    """How the template that wrote a meeting's minutes was chosen (ADR-259)."""

    AUTO = "auto"
    USER = "user"
    PREFERENCE = "preference"


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


def _unique_keys(sections: list[TemplateSection]) -> list[TemplateSection]:
    keys = [section.key for section in sections]
    if len(set(keys)) != len(keys):
        raise ValueError("section keys must be unique")
    return sections


class MeetingTemplateSummary(BaseModel):
    """One library entry, as the list shows it."""

    ref: str = Field(description="builtin:<key> or user:<uuid>.")
    name: str = Field(description="Template name (built-ins: localized).")
    description: str | None = Field(default=None, description="What the template is for.")
    category: TemplateCategory = Field(description="Library category.")
    builtin: bool = Field(description="True for a catalogue template (read-only).")
    sections_count: int = Field(ge=1, description="Number of sections.")
    auto_selectable: bool = Field(
        description="Whether automatic selection may pick it (transcript templates: never)."
    )


class MeetingTemplateListResponse(BaseModel):
    """The library: every built-in plus the user's own, and the user cap."""

    items: list[MeetingTemplateSummary]
    max_user_templates: int = Field(description="How many templates the user may keep.")


class MeetingTemplateResponse(BaseModel):
    """A template with its sections."""

    ref: str = Field(description="builtin:<key> or user:<uuid>.")
    id: uuid.UUID | None = Field(default=None, description="Row id; null for a built-in.")
    name: str = Field(description="Template name.")
    description: str | None = Field(default=None, description="What the template is for.")
    category: TemplateCategory = Field(description="Library category.")
    sections: list[TemplateSection] = Field(description="Ordered sections.")
    builtin: bool = Field(description="True for a catalogue template (read-only).")
    builtin_key: str | None = Field(
        default=None, description="For a user template: the built-in it was duplicated from."
    )
    auto_selectable: bool = Field(description="Whether automatic selection may pick it.")


class MeetingTemplateCreate(BaseModel):
    """Create a user template, from scratch or by duplicating a reference."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: TemplateCategory = Field(default=TemplateCategory.CUSTOM)
    sections: list[TemplateSection] | None = Field(
        default=None, min_length=1, max_length=MAX_TEMPLATE_SECTIONS
    )
    duplicate_of: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=TEMPLATE_REF_PATTERN,
        description="A ref whose sections (and category) are copied when `sections` is absent.",
    )

    @field_validator("sections")
    @classmethod
    def _sections_unique(
        cls, sections: list[TemplateSection] | None
    ) -> list[TemplateSection] | None:
        return _unique_keys(sections) if sections is not None else None

    @model_validator(mode="after")
    def _sections_or_source(self) -> MeetingTemplateCreate:
        if (self.sections is None) == (self.duplicate_of is None):
            raise ValueError("exactly one of sections or duplicate_of")
        if self.sections is not None and self.name is None:
            raise ValueError("name is required without duplicate_of")
        return self


class MeetingTemplateUpdate(BaseModel):
    """Replace a user template (PUT semantics)."""

    name: str = Field(min_length=1, max_length=120, description="Template name.")
    description: str | None = Field(default=None, max_length=500)
    category: TemplateCategory = Field(default=TemplateCategory.CUSTOM)
    sections: list[TemplateSection] = Field(
        min_length=1, max_length=MAX_TEMPLATE_SECTIONS, description="Ordered sections."
    )

    @field_validator("sections")
    @classmethod
    def _sections_unique(cls, sections: list[TemplateSection]) -> list[TemplateSection]:
        return _unique_keys(sections)


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


class TranscriptLine(BaseModel):
    """One rewritten turn of a ``transcript`` section (ADR-259)."""

    speaker: str = Field(min_length=1, max_length=40, description="Speaker label or name.")
    start: float = Field(ge=0, description="Turn start, seconds from the recording start.")
    text: str = Field(min_length=1, max_length=4000, description="The rewritten turn.")


class ReportSection(BaseModel):
    """One filled section — exactly one payload shape is meaningful per kind."""

    key: str = Field(pattern=SECTION_KEY_PATTERN, description="Template section key.")
    label: str = Field(min_length=1, max_length=80, description="Heading (from the template).")
    kind: SectionKind = Field(description="Shape of the content.")
    paragraph: str | None = Field(default=None, max_length=8000, description="For 'paragraph'.")
    bullets: list[str] = Field(default_factory=list, description="For 'bullets'.")
    topics: list[TopicItem] = Field(default_factory=list, description="For 'topics'.")
    action_items: list[ActionItem] = Field(default_factory=list, description="For 'action_items'.")
    transcript: list[TranscriptLine] = Field(default_factory=list, description="For 'transcript'.")

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
            case SectionKind.TRANSCRIPT:
                return not any(line.text.strip() for line in self.transcript)


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
    template_ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=TEMPLATE_REF_PATTERN,
        description="Minutes template for this meeting, while it is still live or queued.",
    )

    @property
    def touches_report(self) -> bool:
        """Whether anything but the template choice is being edited."""
        return any(
            value is not None
            for value in (self.title, self.participants, self.sections, self.location_label)
        )

    @model_validator(mode="after")
    def _something_to_change(self) -> MeetingPatchRequest:
        if not self.touches_report and self.template_ref is None:
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


class MeetingReformatRequest(BaseModel):
    """Write the minutes again with another template (ADR-259)."""

    template_ref: str = Field(
        max_length=MEETINGS_TEMPLATE_REF_MAX, pattern=TEMPLATE_REF_PATTERN, description="Template."
    )
    mode: Literal["replace", "new"] = Field(
        description="replace = these minutes; new = new minutes from the same transcript."
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
