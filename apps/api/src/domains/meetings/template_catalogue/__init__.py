"""The built-in minutes templates (ADR-259) — kinds and model instructions.

Thirty templates in seven categories, read-only for the user (customizing one
means duplicating it into the user's own library). What the user READS —
names, descriptions, section labels — lives in the six-language data module
``core/i18n_meeting_templates.py``; what the MODEL reads — the instruction of
every section, in English, the prompt's working language — lives here, one
module per category (``_meeting``, ``_transcript``, ``_analysis``,
``_business`` with technical, ``_personal`` with learning).

Boot-time completeness (ADR-085): every key has its six-language name and
description, every section key has its six-language label, every instruction
respects the bound ``MeetingTemplateUpdate`` enforces on a user template — so
a built-in can always be duplicated and saved unchanged.

Transcript templates (category ``transcript``) rewrite the whole exchange and
cost an output the size of the meeting: they are never picked automatically
(``auto_selectable=False``) — an explicit, a-posteriori choice of the user.
"""

from __future__ import annotations

from src.core.constants import MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY
from src.core.i18n_meeting_templates import (
    TEMPLATE_KEYS,
    get_section_label,
    get_template_description,
    get_template_name,
    section_label_keys,
)
from src.domains.meetings.schemas import (
    MAX_TEMPLATE_SECTIONS,
    MeetingTemplateResponse,
    MeetingTemplateSummary,
    TemplateSection,
)
from src.domains.meetings.template_catalogue import (
    _analysis,
    _business,
    _meeting,
    _personal,
    _transcript,
)
from src.domains.meetings.template_catalogue._shared import BuiltinSection, BuiltinTemplate
from src.domains.meetings.template_ref import TemplateRef

#: The bound ``TemplateSection.instruction`` enforces (schemas.py).
MAX_INSTRUCTION_CHARS = 600

#: Library order: the categories as the page lists them.
BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...] = (
    *_meeting.TEMPLATES,
    *_transcript.TEMPLATES,
    *_analysis.TEMPLATES,
    *_business.TEMPLATES,
    *_personal.TEMPLATES,
)

BUILTIN_BY_KEY: dict[str, BuiltinTemplate] = {t.key: t for t in BUILTIN_TEMPLATES}

# Boot-time completeness (ADR-085): catalogue and i18n name the same templates;
# every section has a label; every instruction fits the user-template bound.
assert set(BUILTIN_BY_KEY) == set(TEMPLATE_KEYS), "catalogue and i18n template names disagree"
assert len(BUILTIN_BY_KEY) == len(BUILTIN_TEMPLATES), "duplicate template key"
assert MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY in BUILTIN_BY_KEY, "default template key unknown"
for _template in BUILTIN_TEMPLATES:
    assert 1 <= len(_template.sections) <= MAX_TEMPLATE_SECTIONS, _template.key
    _keys = [s.key for s in _template.sections]
    assert len(set(_keys)) == len(_keys), f"{_template.key}: duplicate section keys"
    for _section in _template.sections:
        assert _section.key in section_label_keys(), f"{_template.key}.{_section.key}: no label"
        assert (
            len(_section.instruction) <= MAX_INSTRUCTION_CHARS
        ), f"{_template.key}.{_section.key}: instruction over {MAX_INSTRUCTION_CHARS}"


def builtin_sections(key: str, language: str | None) -> list[TemplateSection]:
    """The sections of built-in ``key``, labelled in ``language``.

    Raises:
        KeyError: for a key outside the catalogue.
    """
    template = BUILTIN_BY_KEY[key]
    return [
        TemplateSection(
            key=section.key,
            label=get_section_label(section.key, language),
            instruction=section.instruction,
            kind=section.kind,
        )
        for section in template.sections
    ]


def builtin_template(key: str, language: str | None) -> MeetingTemplateResponse:
    """Built-in ``key`` as the API serves it."""
    template = BUILTIN_BY_KEY[key]
    return MeetingTemplateResponse(
        ref=str(TemplateRef.builtin(key)),
        id=None,
        name=get_template_name(key, language),
        description=get_template_description(key, language),
        category=template.category,
        sections=builtin_sections(key, language),
        builtin=True,
        builtin_key=None,
        auto_selectable=template.auto_selectable,
    )


def builtin_summary(key: str, language: str | None) -> MeetingTemplateSummary:
    """Built-in ``key`` as the library list shows it."""
    template = BUILTIN_BY_KEY[key]
    return MeetingTemplateSummary(
        ref=str(TemplateRef.builtin(key)),
        name=get_template_name(key, language),
        description=get_template_description(key, language),
        category=template.category,
        builtin=True,
        sections_count=len(template.sections),
        auto_selectable=template.auto_selectable,
    )


__all__ = [
    "BUILTIN_BY_KEY",
    "BUILTIN_TEMPLATES",
    "MAX_INSTRUCTION_CHARS",
    "BuiltinSection",
    "BuiltinTemplate",
    "builtin_sections",
    "builtin_summary",
    "builtin_template",
]
