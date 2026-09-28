"""The readable export names who spoke, in the reader's words and punctuation (ADR-323)."""

from __future__ import annotations

import pytest

from src.core.constants import SUPPORTED_LANGUAGES
from src.core.i18n_account_export import (
    EXPORT_SECTION_HEADINGS,
    EXPORT_SPEAKERS,
    render_export_speaker,
)
from src.core.i18n_drafts import label_separator
from src.domains.account_export.builder import _render_conversations

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "zh-CN"])
def test_each_message_opens_on_its_speaker_and_the_reader_s_separator(language: str) -> None:
    rows = [{"role": "user", "content": "Hello", "created_at": "2026-09-26T08:00:00+00:00"}]

    rendered = _render_conversations(rows, language)

    speaker = EXPORT_SPEAKERS[language]["user"]
    head = f"**{speaker}** (2026-09-26T08:00:00+00:00){label_separator(language).rstrip()}"
    assert f"{head}\n" in rendered
    assert not any(line.endswith(" ") for line in rendered.splitlines())
    assert "Hello" in rendered


def test_the_archive_frames_the_words_in_every_language() -> None:
    """Six languages, and no reader but the English one meets English headings."""
    assert set(EXPORT_SECTION_HEADINGS) == set(SUPPORTED_LANGUAGES)
    assert set(EXPORT_SPEAKERS) == set(SUPPORTED_LANGUAGES)
    english = EXPORT_SECTION_HEADINGS["en"]
    for language in set(SUPPORTED_LANGUAGES) - {"en", "fr"}:
        assert EXPORT_SECTION_HEADINGS[language]["journals"] != english["journals"]


def test_a_role_that_names_nobody_is_shown_as_stored() -> None:
    assert render_export_speaker("system", "fr") == "system"
    assert render_export_speaker("assistant", "de") == "LIA"
