"""Shared public template contracts for the UI, original domain and native tools."""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX

MAX_TEMPLATE_SECTIONS = 12
SECTION_KEY_PATTERN = r"^[a-z][a-z0-9_]{1,39}$"
TEMPLATE_REF_PATTERN = r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-fA-F-]{36})$"


def canonical_template_reference(value: str | None) -> str | None:
    """Normalize an already validated UUID spelling; never grant template ownership."""
    return value.lower() if value is not None and value.startswith("user:") else value


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
