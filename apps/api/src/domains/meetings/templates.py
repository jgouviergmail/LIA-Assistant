"""The minutes template: built-in default and validation (ADR-258).

The default lives in CODE (kinds here, labels and instructions in
``core/i18n_meetings.py``) so a reset is deterministic and speaks the user's
language; a user edit is a ``meeting_templates`` row. The kinds map is asserted
complete against the label keys at import time (ADR-085): a default section
without a kind — or a label without a section — refuses to boot.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.core.i18n_meetings import (
    DEFAULT_SECTION_INSTRUCTIONS,
    DEFAULT_SECTION_KEYS,
    get_section_label,
    get_template_name,
)
from src.domains.meetings.schemas import (
    MAX_TEMPLATE_SECTIONS,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
    SectionKind,
    TemplateSection,
)

#: Shape of each default section. Rendering order is ``DEFAULT_SECTION_KEYS``.
DEFAULT_SECTION_KINDS: dict[str, SectionKind] = {
    "summary": SectionKind.PARAGRAPH,
    "topics": SectionKind.TOPICS,
    "decisions": SectionKind.BULLETS,
    "action_items": SectionKind.ACTION_ITEMS,
    "risks": SectionKind.BULLETS,
    "open_questions": SectionKind.BULLETS,
}

# Boot-time completeness (ADR-085): the three declarations name the same sections.
assert set(DEFAULT_SECTION_KINDS) == set(
    DEFAULT_SECTION_KEYS
), "DEFAULT_SECTION_KINDS must cover exactly DEFAULT_SECTION_KEYS"
assert set(DEFAULT_SECTION_INSTRUCTIONS) == set(
    DEFAULT_SECTION_KEYS
), "DEFAULT_SECTION_INSTRUCTIONS must cover exactly DEFAULT_SECTION_KEYS"


def default_sections(language: str | None) -> list[TemplateSection]:
    """The built-in template, labelled in ``language``.

    Args:
        language: Backend-canonical or raw locale; normalized by the i18n table.

    Returns:
        Ordered sections with localized labels and English model instructions.
    """
    return [
        TemplateSection(
            key=key,
            label=get_section_label(key, language),
            instruction=DEFAULT_SECTION_INSTRUCTIONS[key],
            kind=DEFAULT_SECTION_KINDS[key],
        )
        for key in DEFAULT_SECTION_KEYS
    ]


def default_template(language: str | None) -> MeetingTemplateResponse:
    """The template served when the user has not edited one."""
    return MeetingTemplateResponse(
        id=None,
        name=get_template_name(language),
        sections=default_sections(language),
        is_builtin_default=True,
    )


def parse_sections(raw: Any) -> list[TemplateSection]:
    """Validate a stored ``sections`` JSON payload (template row or snapshot).

    Args:
        raw: The JSONB value.

    Returns:
        Validated sections.

    Raises:
        ValueError: When the payload is not a valid, non-empty, unique-key list.
    """
    try:
        update = MeetingTemplateUpdate(name="stored", sections=raw)
    except ValidationError as exc:
        raise ValueError(f"invalid template sections: {exc.error_count()} error(s)") from exc
    return update.sections


def sections_to_json(sections: list[TemplateSection]) -> list[dict[str, Any]]:
    """Serialize sections for the JSONB column (enum values, not members)."""
    return [section.model_dump(mode="json") for section in sections]


__all__ = [
    "DEFAULT_SECTION_KINDS",
    "MAX_TEMPLATE_SECTIONS",
    "default_sections",
    "default_template",
    "parse_sections",
    "sections_to_json",
]
