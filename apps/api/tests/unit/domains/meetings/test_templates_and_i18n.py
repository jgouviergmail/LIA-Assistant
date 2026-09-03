"""Default template, template validation and backend i18n parity (ADR-258)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core import i18n_meetings
from src.core.i18n_meetings import (
    DEFAULT_SECTION_INSTRUCTIONS,
    DEFAULT_SECTION_KEYS,
    get_header_label,
    get_notification_title,
    get_section_label,
    get_space_name,
    get_speaker_label,
    supported_languages,
)
from src.domains.meetings.schemas import (
    MAX_TEMPLATE_SECTIONS,
    MeetingTemplateUpdate,
    SectionKind,
    TemplateSection,
)
from src.domains.meetings.templates import (
    DEFAULT_SECTION_KINDS,
    default_sections,
    default_template,
    parse_sections,
    sections_to_json,
)

pytestmark = pytest.mark.unit

SIX = ("en", "fr", "de", "es", "it", "zh-CN")


def test_the_six_languages_are_covered_by_every_table() -> None:
    assert set(supported_languages()) == set(SIX)
    for table in (i18n_meetings._SECTION_LABELS,):
        for key, labels in table.items():
            assert set(labels) == set(SIX), f"{key}: {set(SIX) ^ set(labels)}"
    for lng in SIX:
        header = i18n_meetings._HEADER_LABELS[lng]
        assert set(header) == set(i18n_meetings._HEADER_LABELS["en"]), lng
        assert get_speaker_label(2, lng).count("2") == 1
        assert get_space_name(lng)
        assert get_notification_title(lng)
        assert get_header_label("participants", lng)


def test_default_template_is_ordered_localized_and_complete() -> None:
    sections = default_sections("fr")
    assert [s.key for s in sections] == list(DEFAULT_SECTION_KEYS)
    assert sections[0].label == "Résumé"
    assert sections[0].kind is SectionKind.PARAGRAPH
    assert sections[1].kind is SectionKind.TOPICS
    assert sections[3].kind is SectionKind.ACTION_ITEMS
    assert (
        set(DEFAULT_SECTION_KINDS) == set(DEFAULT_SECTION_INSTRUCTIONS) == set(DEFAULT_SECTION_KEYS)
    )
    template = default_template("zh")
    assert template.is_builtin_default is True and template.id is None
    assert template.sections[0].label == get_section_label("summary", "zh-CN")


def test_unknown_or_missing_language_follows_the_configured_default() -> None:
    # normalize_language is the ONLY fallback authority: an unknown locale and a
    # missing one both resolve to the deployment's default language.
    from src.core.i18n import DEFAULT_LANGUAGE

    assert get_section_label("summary", "xx") == get_section_label("summary", DEFAULT_LANGUAGE)
    assert get_space_name(None) == get_space_name(DEFAULT_LANGUAGE)
    assert get_space_name("en") == "Meetings"


def test_template_update_rejects_duplicate_keys_and_bad_slugs() -> None:
    good = TemplateSection(
        key="summary", label="Résumé", instruction="x", kind=SectionKind.PARAGRAPH
    )
    with pytest.raises(ValidationError, match="unique"):
        MeetingTemplateUpdate(name="t", sections=[good, good])
    with pytest.raises(ValidationError):
        TemplateSection(key="Bad Key", label="x", instruction="x", kind=SectionKind.BULLETS)
    with pytest.raises(ValidationError):
        MeetingTemplateUpdate(name="t", sections=[])
    too_many = [
        TemplateSection(key=f"s{i}", label="x", instruction="x", kind=SectionKind.BULLETS)
        for i in range(MAX_TEMPLATE_SECTIONS + 1)
    ]
    with pytest.raises(ValidationError):
        MeetingTemplateUpdate(name="t", sections=too_many)


def test_stored_sections_round_trip_and_bad_payloads_are_refused() -> None:
    sections = default_sections("en")
    stored = sections_to_json(sections)
    assert stored[0]["kind"] == "paragraph"  # enum VALUE in JSON, never the member
    assert parse_sections(stored) == sections
    with pytest.raises(ValueError, match="invalid template sections"):
        parse_sections([{"key": "x"}])
    with pytest.raises(ValueError):
        parse_sections("not a list")
