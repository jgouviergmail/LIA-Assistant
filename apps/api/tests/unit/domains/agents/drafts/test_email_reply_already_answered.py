"""The card of a reply says when the person already answered that message (ADR-379).

Answering a message twice is the person's right; doing it without knowing is how a
duplicate leaves. The confirmation card states it FIRST, in the reader's language and
zone, before the recipients and the words being approved.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.card_spec import Note, Row
from src.domains.agents.drafts.models import Draft, DraftType, EmailReplyDraftInput
from src.domains.agents.drafts.preview_renderer import build_card_spec, render_detailed_preview

pytestmark = [pytest.mark.unit]

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


def _reply(**over: Any) -> Draft:
    content = EmailReplyDraftInput(
        message_id="m1",
        to="Marc Dupont <marc@example.org>",
        subject="Re: Budget",
        body="One more thing.",
        **over,
    ).model_dump()
    return Draft(type=DraftType.EMAIL_REPLY, content=content)


@pytest.mark.parametrize("language", LANGUAGES)
def test_an_answered_message_is_said_first_in_the_readers_language(language: str) -> None:
    draft = _reply(already_answered=True, answered_at="2026-11-10T09:30:00+01:00")

    first = build_card_spec(draft, language, "Europe/Paris").lines[0]

    assert isinstance(first, Row)
    assert first.label == get_draft_preview_labels(language)["already_answered"]
    assert "2026" in str(first.value) and "09:30" in str(first.value).replace("h", ":")


def test_the_instant_is_told_in_the_readers_own_zone() -> None:
    draft = _reply(already_answered=True, answered_at="2026-11-10T09:30:00+01:00")

    first = build_card_spec(draft, "en", "America/New_York").lines[0]

    assert isinstance(first, Row) and "03:30" in str(first.value)


def test_a_mark_the_mailbox_does_not_date_is_said_without_a_date() -> None:
    first = build_card_spec(_reply(already_answered=True), "en", "Europe/Paris").lines[0]

    assert first == Note(text=get_draft_preview_labels("en")["already_answered"])


def test_a_first_reply_reads_as_before() -> None:
    preview = render_detailed_preview(_reply(), "en", "Europe/Paris")

    assert get_draft_preview_labels("en")["already_answered"] not in preview
    assert preview.splitlines()[0].startswith("- **To**")
