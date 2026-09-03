"""The built-in template catalogue (ADR-259): complete in six languages, within the API bounds.

The catalogue is code (kinds, instructions) plus a data module (names,
descriptions, section labels ×6). Both are asserted complete at import time;
these tests state the same contracts as behaviour, plus the bounds every
section must respect — the SAME bounds ``MeetingTemplateUpdate`` enforces on
a user template, so a built-in can always be duplicated and saved unchanged.
"""

from __future__ import annotations

import re

import pytest

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
    SECTION_KEY_PATTERN,
    MeetingTemplateUpdate,
    SectionKind,
    TemplateCategory,
)
from src.domains.meetings.template_catalogue import (
    BUILTIN_BY_KEY,
    BUILTIN_TEMPLATES,
    builtin_sections,
    builtin_summary,
    builtin_template,
)

pytestmark = pytest.mark.unit

SIX = ("en", "fr", "de", "es", "it", "zh-CN")
MAX_INSTRUCTION_CHARS = 600
MAX_LABEL_CHARS = 80


def test_the_catalogue_holds_the_thirty_agreed_templates() -> None:
    assert len(BUILTIN_TEMPLATES) == 30
    keys = [template.key for template in BUILTIN_TEMPLATES]
    assert len(set(keys)) == len(keys)
    assert set(keys) == set(TEMPLATE_KEYS)
    assert MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY in BUILTIN_BY_KEY


@pytest.mark.parametrize("template", BUILTIN_TEMPLATES, ids=lambda t: t.key)
def test_every_template_respects_the_user_template_bounds(template) -> None:
    assert 1 <= len(template.sections) <= MAX_TEMPLATE_SECTIONS
    keys = [section.key for section in template.sections]
    assert len(set(keys)) == len(keys), "section keys must be unique"
    for section in template.sections:
        assert re.match(SECTION_KEY_PATTERN, section.key), section.key
        assert 1 <= len(section.instruction) <= MAX_INSTRUCTION_CHARS, (template.key, section.key)
        assert section.key in section_label_keys(), (template.key, section.key)
    # The exact contract of a saved user template: a duplicate is always valid.
    MeetingTemplateUpdate(name="copy", sections=builtin_sections(template.key, "en"))


@pytest.mark.parametrize("template", BUILTIN_TEMPLATES, ids=lambda t: t.key)
def test_transcript_templates_are_never_auto_selected_and_only_they_carry_the_kind(
    template,
) -> None:
    has_transcript = any(s.kind is SectionKind.TRANSCRIPT for s in template.sections)
    if template.category is TemplateCategory.TRANSCRIPT:
        assert template.auto_selectable is False
        assert has_transcript
    else:
        assert not has_transcript
        assert template.auto_selectable is True


def test_the_default_template_is_exactly_the_historical_one() -> None:
    default = BUILTIN_BY_KEY[MEETINGS_DEFAULT_BUILTIN_TEMPLATE_KEY]
    assert default.category is TemplateCategory.MEETING
    assert [(s.key, s.kind) for s in default.sections] == [
        ("summary", SectionKind.PARAGRAPH),
        ("topics", SectionKind.TOPICS),
        ("decisions", SectionKind.BULLETS),
        ("action_items", SectionKind.ACTION_ITEMS),
        ("risks", SectionKind.BULLETS),
        ("open_questions", SectionKind.BULLETS),
    ]


def test_every_category_but_custom_has_at_least_one_template() -> None:
    covered = {template.category for template in BUILTIN_TEMPLATES}
    assert covered == set(TemplateCategory) - {TemplateCategory.CUSTOM}


@pytest.mark.parametrize("language", SIX)
@pytest.mark.parametrize("key", TEMPLATE_KEYS)
def test_names_descriptions_and_labels_exist_in_the_six_languages(key: str, language: str) -> None:
    assert get_template_name(key, language).strip()
    assert get_template_description(key, language).strip()
    for section in BUILTIN_BY_KEY[key].sections:
        label = get_section_label(section.key, language)
        assert label.strip() and len(label) <= MAX_LABEL_CHARS, (key, section.key, language)


def test_localized_sections_carry_the_language_the_user_reads() -> None:
    sections = builtin_sections("medical_appointment", "fr")
    assert sections[0].label == get_section_label(sections[0].key, "fr")
    assert sections[0].label != get_section_label(sections[0].key, "de")
    # Instructions are the model's working language whatever the user's.
    assert sections[0].instruction == BUILTIN_BY_KEY["medical_appointment"].sections[0].instruction


def test_the_response_and_summary_shapes_name_the_reference() -> None:
    response = builtin_template("bant_analysis", "en")
    assert response.ref == "builtin:bant_analysis" and response.id is None
    assert response.builtin is True and response.category is TemplateCategory.BUSINESS
    summary = builtin_summary("transcript_clean", "it")
    assert summary.ref == "builtin:transcript_clean"
    assert summary.sections_count == len(BUILTIN_BY_KEY["transcript_clean"].sections)
    assert summary.auto_selectable is False and summary.builtin is True


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(KeyError):
        builtin_sections("nope", "en")
