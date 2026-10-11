"""Shared original minutes and sparse patch contracts; domain re-exports stay compatible."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.meeting_templates import SECTION_KEY_PATTERN, TEMPLATE_REF_PATTERN, SectionKind


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


def apply_report_changes(
    report: MeetingReport | None, request: MeetingPatchRequest
) -> MeetingReport | None:
    """Merge only original non-null header/content fields and validate the whole result."""
    if report is None:
        return None
    updates = {
        key: value
        for key, value in (
            ("title", request.title),
            ("participants", request.participants),
            ("sections", request.sections),
        )
        if value is not None
    }
    return MeetingReport.model_validate(report.model_copy(update=updates).model_dump())
