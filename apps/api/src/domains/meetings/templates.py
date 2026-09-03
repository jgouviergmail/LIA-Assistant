"""The minutes template: built-in default, validation and JSON round trip (ADR-258, ADR-259).

The default is ONE entry of the catalogue (``template_catalogue.py``, key
``MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY``); ``DEFAULT_SECTION_*`` derive from it
so every historical reader keeps its name. A user edit is a
``meeting_templates`` row.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.core.constants import MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY
from src.domains.meetings.schemas import (
    MAX_TEMPLATE_SECTIONS,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
    SectionKind,
    TemplateSection,
)
from src.domains.meetings.template_catalogue import (
    BUILTIN_BY_KEY,
    builtin_sections,
    builtin_template,
)

_DEFAULT = BUILTIN_BY_KEY[MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY]

#: Default section keys, in rendering order (derived from the catalogue).
DEFAULT_SECTION_KEYS: tuple[str, ...] = tuple(section.key for section in _DEFAULT.sections)
#: Shape of each default section.
DEFAULT_SECTION_KINDS: dict[str, SectionKind] = {s.key: s.kind for s in _DEFAULT.sections}
#: What the model is asked to put in each default section (English, the prompt's language).
DEFAULT_SECTION_INSTRUCTIONS: dict[str, str] = {s.key: s.instruction for s in _DEFAULT.sections}


def default_sections(language: str | None) -> list[TemplateSection]:
    """The built-in default template's sections, labelled in ``language``."""
    return builtin_sections(MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY, language)


def default_template(language: str | None) -> MeetingTemplateResponse:
    """The built-in default template, labelled in ``language``."""
    return builtin_template(MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY, language)


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
    "DEFAULT_SECTION_INSTRUCTIONS",
    "DEFAULT_SECTION_KEYS",
    "DEFAULT_SECTION_KINDS",
    "MAX_TEMPLATE_SECTIONS",
    "default_sections",
    "default_template",
    "parse_sections",
    "sections_to_json",
]
