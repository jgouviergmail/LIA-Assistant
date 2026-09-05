"""The model-facing shapes accept ``null`` where the schema has a default (2026-09-05).

Replayed in production: ``deepseek-v4-flash`` answered the forced tool with a
complete, correct minutes payload and ``"bullets": null`` on a paragraph
section. ``list[str] = Field(default_factory=list)`` refused it three times,
the meeting failed, and the message said the model had not answered. A
model-facing shape is permissive by contract — the strict ``MeetingReport``
lives in ``schemas.py`` — so ``null`` on a defaulted list means « none ».
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.meetings.synthesis import SynthesizedMinutes, SynthesizedSection

pytestmark = pytest.mark.unit

#: What the model returned on 2026-09-05 (wording shortened, shape exact).
DEEPSEEK_PAYLOAD: dict[str, Any] = {
    "title": "Point sur le lancement de la newsletter de septembre",
    "participants": [
        {"label": "speaker_0", "name": None, "role": None},
        {"label": "speaker_1", "name": None, "role": None},
    ],
    "sections": [
        {
            "key": "summary",
            "paragraph": "Point rapide sur le lancement de la newsletter.",
            "topics": [],
            "bullets": None,
            "action_items": [],
        },
        {
            "key": "topics",
            "topics": [{"title": "Visuel de couverture", "summary": "Version finale demain."}],
            "paragraph": None,
            "bullets": None,
            "action_items": [],
        },
        {"key": "decisions", "bullets": ["La couverture d'août sera conservée."]},
        {
            "key": "action_items",
            "action_items": [
                {"description": "Envoyer le visuel", "owner": "Marc", "due_date": "2026-09-06"},
                {"description": "Recaler jeudi", "owner": None, "due_date": "2026-09-10"},
            ],
        },
        {"key": "risks", "bullets": ["Le visuel peut manquer."]},
        {"key": "open_questions", "bullets": []},
    ],
}


def test_the_payload_deepseek_returned_on_2026_09_05_validates() -> None:
    minutes = SynthesizedMinutes.model_validate(DEEPSEEK_PAYLOAD)
    assert minutes.sections[0].bullets == []
    assert minutes.sections[1].paragraph is None
    assert [topic.title for topic in minutes.sections[1].topics] == ["Visuel de couverture"]
    assert minutes.sections[3].action_items[1].owner is None


def test_null_on_every_defaulted_list_reads_as_empty() -> None:
    minutes = SynthesizedMinutes.model_validate(
        {"title": "t", "participants": None, "sections": None}
    )
    assert minutes.participants == [] and minutes.sections == []
    section = SynthesizedSection.model_validate(
        {"key": "k", "bullets": None, "topics": None, "action_items": None}
    )
    assert section.bullets == [] and section.topics == [] and section.action_items == []


def test_a_wrong_type_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        SynthesizedSection.model_validate({"key": "k", "bullets": "not a list"})
    with pytest.raises(ValidationError):
        SynthesizedMinutes.model_validate({"title": None, "sections": []})
