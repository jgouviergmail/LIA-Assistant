"""The one call per seam behind which every declaration of an answer is handled.

The response node and the stream that assembles ``done`` are frozen at their
size and each call ONE function. What must hold is that this function forgets
no declaration: an instruction not injected is a tag never written, a tag not
taken is a tag the person reads, and a declaration not attached never reaches
whoever acts on it.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import settings
from src.domains.agents.expressivity.annotation import TONE_TAG_MARKER
from src.domains.agents.prompts.prompt_loader import FINAL_REMINDER_MARKER
from src.domains.agents.services import nothing_new
from src.domains.agents.services.answer_annotations import (
    attach_answer_annotations_to_done,
    inject_answer_annotations,
    take_answer_annotations,
)
from src.domains.agents.services.nothing_new import NOTHING_NEW_TAG_MARKER, quiet_run_scope

pytestmark = pytest.mark.unit

_PROMPT = f"You are LIA.\n\n{FINAL_REMINDER_MARKER}\nAnswer in the person's language."
_ANSWER = 'Nothing new.\n<lia_nothing_new/>\n<lia_tone register="factual" intensity="0.3"/>'


@pytest.fixture(autouse=True)
def _expressive_and_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "expressivity_enabled", True)
    nothing_new._declared.clear()


def test_a_quiet_run_is_asked_for_both_declarations_before_the_final_reminder() -> None:
    with quiet_run_scope(True):
        prompt = inject_answer_annotations(_PROMPT)

    reminder = prompt.index(FINAL_REMINDER_MARKER)
    assert 0 < prompt.index(TONE_TAG_MARKER) < reminder
    assert 0 < prompt.index(NOTHING_NEW_TAG_MARKER) < reminder


def test_an_ordinary_turn_is_asked_for_its_tone_alone() -> None:
    prompt = inject_answer_annotations(_PROMPT)

    assert TONE_TAG_MARKER in prompt
    assert NOTHING_NEW_TAG_MARKER not in prompt


def test_every_declaration_leaves_the_answer_and_reaches_done() -> None:
    with quiet_run_scope(True):
        cleaned = take_answer_annotations(_ANSWER, "run-both")
    done: dict[str, Any] = {}
    attach_answer_annotations_to_done(done, "run-both")

    assert cleaned == "Nothing new."
    assert done["nothing_new"] is True
    assert done["expressivity"]["register"] == "factual"


def test_an_answer_that_declares_nothing_is_left_as_written() -> None:
    with quiet_run_scope(True):
        cleaned = take_answer_annotations("Two invoices arrived.", "run-plain")
    done: dict[str, Any] = {}
    attach_answer_annotations_to_done(done, "run-plain")

    assert cleaned == "Two invoices arrived."
    assert done == {}
