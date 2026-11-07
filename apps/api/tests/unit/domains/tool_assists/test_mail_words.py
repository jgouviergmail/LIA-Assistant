"""What a person says of their mailbox (ADR-372, lot 9).

A sentence becomes criteria on the screen or a filled form, never an act. What the model answers is
held to what those can take: an unreadable day is left out, a label nobody has is dropped, every
value stays under its field's bound, and a sentence that says nothing usable is a refusal.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.domains.tool_assists import mail_words
from src.domains.tool_assists.actions import AssistClock
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.mail_words import (
    FilterDraft,
    SearchDraft,
    filter_from_sentence,
    proposed_filter,
    proposed_search,
    search_from_sentence,
)
from src.domains.workbench.schemas.mail_settings import FILTER_CRITERION_MAX_CHARS

pytestmark = pytest.mark.unit

CLOCK = AssistClock(today=date(2026, 3, 4), zone="Europe/Paris")


def _run() -> AssistRun:
    return AssistRun(user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]))


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


def _answers(monkeypatch: pytest.MonkeyPatch, answer: BaseModel) -> list[str]:
    prompts: list[str] = []

    async def ask(run: AssistRun, prompt: str, schema: type[Any]) -> BaseModel:
        prompts.append(prompt)
        return answer

    monkeypatch.setattr(mail_words, "ask_slot", ask)
    return prompts


def test_a_search_keeps_what_the_screen_can_take() -> None:
    proposal = proposed_search(
        SearchDraft(words="  from:Ana invoice ", unread=True, first_day="2026-02-01", last_day="?")
    )

    assert proposal.words == "from:Ana invoice"
    assert proposal.unread is True
    assert proposal.first_day == "2026-02-01"
    assert proposal.last_day is None


def test_a_search_stays_under_the_length_the_listing_takes() -> None:
    proposal = proposed_search(SearchDraft(words="x" * (WORKBENCH_MAIL_QUERY_MAX_CHARS + 50)))

    assert len(proposal.words) == WORKBENCH_MAIL_QUERY_MAX_CHARS


def test_a_sentence_that_narrows_nothing_is_a_refusal_never_a_blank_search() -> None:
    with pytest.raises(BaseAPIException) as refused:
        proposed_search(SearchDraft(first_day="soon"))

    assert _code(refused) == "assist_not_found"


async def test_the_person_s_day_and_zone_reach_the_search_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _answers(monkeypatch, SearchDraft(words="budget"))

    proposal = await search_from_sentence(_run(), "le budget", CLOCK)

    assert proposal.words == "budget"
    assert "2026-03-04 (Wednesday)" in prompts[0]
    assert "Europe/Paris" in prompts[0]
    assert "le budget" in prompts[0]


def test_a_filter_keeps_the_person_s_own_spelling_of_a_label() -> None:
    draft = FilterDraft(found=True, sender="a@b.c", label="invoices", mark_read=True)

    assert proposed_filter(draft, ["Invoices", "Family"]).label == "Invoices"


def test_a_label_nobody_has_is_dropped_never_passed_on() -> None:
    draft = FilterDraft(found=True, sender="a@b.c", label="Imaginary", archive=True)

    proposal = proposed_filter(draft, ["Invoices"])

    assert proposal.label is None
    assert proposal.archive is True


def test_a_criterion_stays_under_its_published_bound() -> None:
    draft = FilterDraft(found=True, subject="x" * (FILTER_CRITERION_MAX_CHARS + 5), archive=True)

    assert len(proposed_filter(draft, []).subject) == FILTER_CRITERION_MAX_CHARS


@pytest.mark.parametrize(
    "draft",
    [
        FilterDraft(found=False, sender="a@b.c", archive=True),
        FilterDraft(found=True, archive=True),
        FilterDraft(found=True, sender="a@b.c"),
        FilterDraft(found=True, sender="a@b.c", label="Imaginary"),
    ],
)
def test_a_filter_needs_something_to_match_and_something_to_do(draft: FilterDraft) -> None:
    with pytest.raises(BaseAPIException) as refused:
        proposed_filter(draft, ["Invoices"])

    assert _code(refused) == "assist_not_found"


async def test_the_person_s_labels_reach_the_filter_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts = _answers(
        monkeypatch, FilterDraft(found=True, sender="a@b.c", label="Family", archive=True)
    )

    proposal = await filter_from_sentence(_run(), "archive a@b.c", ["Invoices", "Family"])

    assert proposal.label == "Family"
    assert "Invoices, Family" in prompts[0]
    assert "archive a@b.c" in prompts[0]


async def test_no_label_is_said_as_none_to_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = _answers(monkeypatch, FilterDraft(found=True, sender="a@b.c", archive=True))

    await filter_from_sentence(_run(), "archive a@b.c", [])

    assert "(none)" in prompts[0]
