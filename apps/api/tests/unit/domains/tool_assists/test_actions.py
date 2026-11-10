"""From words to an act the person finishes by hand (ADR-372, lot 4).

The model says what it read; here what it said is held to what a form can take. A value it could
not read is left out, never guessed at: a date the page would not understand would read as today.
A text with nothing of the kind is a refusal, never an empty form.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from src.core.constants import (
    DYNAMIC_CONTEXT_MARKER,
    EXTERNAL_CONTENT_OPEN_TAG,
    WORKBENCH_TASK_TITLE_MAX_CHARS,
)
from src.core.exceptions import BaseAPIException
from src.domains.connectors.models import ConnectorType
from src.domains.tool_assists import actions
from src.domains.tool_assists.actions import (
    AssistClock,
    EventDraft,
    StepsDraft,
    TaskDraft,
    event_from_message,
    event_from_sentence,
    proposed_event,
    proposed_task,
    steps_of_task,
    task_from_message,
    task_from_sentence,
)
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import assist_line
from src.domains.workbench.features import WorkbenchTool

pytestmark = pytest.mark.unit

CLOCK = AssistClock(today=date(2026, 11, 4), zone="Europe/Paris")
MESSAGE = {
    "id": "m1",
    "from": "ana@example.org",
    "to": "Jean Dupont <jean@example.org>",
    "cc": "Carol <carol@example.org>",
    "date": "2026-11-03T10:00:00Z",
    "subject": "Lunch",
    "body": "Shall we meet Thursday at noon?",
    "attachments": [{"filename": "menu.pdf", "mimeType": "application/pdf"}],
}


def _run() -> AssistRun:
    return AssistRun(
        user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]), sections=("mail",)
    )


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


class TestWhatAFormCanTake:
    def test_a_whole_event_comes_through(self) -> None:
        event = proposed_event(
            EventDraft(
                found=True,
                summary=" Lunch ",
                start_date="2026-11-05",
                start_time="12:00",
                end_date="2026-11-05",
                end_time="13:30",
                location=" Café ",
                description="With Ana",
                attendees=["ana@example.org"],
                repeat="weekly",
            )
        )

        assert event.summary == "Lunch"
        assert (event.start_date, event.start_time) == ("2026-11-05", "12:00")
        assert (event.end_date, event.end_time) == ("2026-11-05", "13:30")
        assert event.location == "Café"
        assert event.attendees == ["ana@example.org"]
        assert event.repeat == "weekly"

    @pytest.mark.parametrize("day", ["tomorrow", "2026-13-40", "05/11/2026", ""])
    def test_a_day_nobody_can_read_is_left_out_with_its_hours(self, day: str) -> None:
        event = proposed_event(
            EventDraft(found=True, summary="Lunch", start_date=day, start_time="12:00")
        )

        assert event.start_date is None
        assert event.start_time is None

    @pytest.mark.parametrize("time", ["noon", "25:00", "12h30", ""])
    def test_a_time_nobody_can_read_is_left_out(self, time: str) -> None:
        event = proposed_event(
            EventDraft(found=True, summary="Lunch", start_date="2026-11-05", start_time=time)
        )

        assert event.start_date == "2026-11-05"
        assert event.start_time is None

    def test_an_end_before_the_start_is_left_out(self) -> None:
        event = proposed_event(
            EventDraft(
                found=True,
                summary="Lunch",
                start_date="2026-11-05",
                start_time="14:00",
                end_date="2026-11-05",
                end_time="13:00",
            )
        )

        assert event.end_date is None
        assert event.end_time is None

    def test_an_end_with_no_start_is_left_out(self) -> None:
        event = proposed_event(
            EventDraft(found=True, summary="Lunch", end_date="2026-11-05", end_time="13:00")
        )

        assert event.end_date is None

    def test_an_all_day_event_keeps_its_days_and_no_hours(self) -> None:
        event = proposed_event(
            EventDraft(
                found=True,
                summary="Offsite",
                all_day=True,
                start_date="2026-11-05",
                start_time="09:00",
                end_date="2026-11-06",
            )
        )

        assert event.all_day is True
        assert event.start_time is None
        assert event.end_date == "2026-11-06"

    def test_an_address_nobody_can_write_to_is_left_out(self) -> None:
        event = proposed_event(
            EventDraft(
                found=True,
                summary="Lunch",
                attendees=["ana@example.org", "Paul", "bad@", "ana@example.org"],
            )
        )

        assert event.attendees == ["ana@example.org"]

    def test_a_rule_nobody_defined_means_it_does_not_repeat(self) -> None:
        event = proposed_event(EventDraft(found=True, summary="Lunch", repeat="sometimes"))

        assert event.repeat == "none"

    def test_a_task_keeps_a_day_it_can_read(self) -> None:
        task = proposed_task(
            TaskDraft(found=True, title=" Pay ", notes=" Due soon ", due="2026-11-05"), []
        )

        assert (task.title, task.notes, task.due) == ("Pay", "Due soon", "2026-11-05")

    def test_a_task_leaves_out_a_day_it_cannot_read(self) -> None:
        assert proposed_task(TaskDraft(found=True, title="Pay", due="soon"), []).due is None

    def test_a_task_goes_to_a_list_only_if_the_list_exists(self) -> None:
        draft = TaskDraft(found=True, title="Pay", list_name="work")

        assert proposed_task(draft, ["Home", "Work"]).list_name == "Work"
        assert proposed_task(draft, ["Home"]).list_name is None

    @pytest.mark.parametrize(
        ("said", "kept"),
        [("high", "high"), (" HIGH ", "high"), ("urgent", None), ("normal", None), ("", None)],
    )
    def test_a_task_matters_more_only_when_the_text_says_it_is_urgent(
        self, said: str, kept: str | None
    ) -> None:
        task = proposed_task(TaskDraft(found=True, title="Pay", importance=said), [])

        assert task.importance == kept

    def test_a_video_call_asked_for_without_a_link_is_proposed(self) -> None:
        asked = proposed_event(EventDraft(found=True, summary="Call", conference=True))
        quiet = proposed_event(EventDraft(found=True, summary="Call"))

        assert asked.conference is True
        assert quiet.conference is False

    def test_a_video_call_that_already_has_its_link_is_not_made_twice(self) -> None:
        event = proposed_event(
            EventDraft(
                found=True,
                summary="Call",
                location="https://meet.example.org/abc-defg",
                conference=True,
            )
        )

        assert event.location == "https://meet.example.org/abc-defg"
        assert event.conference is False

    def test_a_title_is_held_to_what_the_provider_takes(self) -> None:
        long = "x" * (WORKBENCH_TASK_TITLE_MAX_CHARS + 5)

        with pytest.raises(ValidationError):
            TaskDraft(found=True, title=long)


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every prompt that reached the slot."""
    prompts: list[str] = []

    async def answer(run: AssistRun, rendered: str, schema: type[Any]) -> Any:
        prompts.append(rendered)
        if schema is EventDraft:
            return EventDraft(found=True, summary="Lunch", start_date="2026-11-05")
        if schema is TaskDraft:
            return TaskDraft(found=True, title="Pay", due="2026-11-05")
        return StepsDraft(steps=[" One ", "", "Two"])

    monkeypatch.setattr(actions, "ask_slot", answer)
    return prompts


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reads: list[str] = []

    class _Client:
        async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
            assert use_cache is False
            reads.append(message_id)
            return MESSAGE

        async def get_own_address(self) -> str | None:
            reads.append("own address")
            return "jean@example.org"

    class _Opened:
        client = _Client()
        connector_type = ConnectorType.GOOGLE_GMAIL

    @asynccontextmanager
    async def opening(tool: WorkbenchTool, user_id: object) -> AsyncIterator[_Opened]:
        assert tool is WorkbenchTool.MAIL
        yield _Opened()

    monkeypatch.setattr(actions, "open_tool_client", opening)
    return reads


def _data(prompt: str) -> str:
    return prompt.split(DYNAMIC_CONTEXT_MARKER, 1)[1]


async def test_an_event_is_read_from_the_message_as_it_stands(
    asked: list[str], mailbox: list[str]
) -> None:
    run = _run()

    event = await event_from_message(run, "m1", CLOCK, None)

    assert event.summary == "Lunch"
    assert mailbox == ["m1", "own address"]
    assert run.opened is True
    data = _data(asked[0])
    assert "Shall we meet Thursday at noon?" in data
    assert "2026-11-04" in data and "Europe/Paris" in data
    assert "external_content" in data, "a stranger's words are marked as what they are"


async def test_an_event_never_invites_the_reader_s_own_mailbox(
    monkeypatch: pytest.MonkeyPatch, mailbox: list[str]
) -> None:
    async def guests(run: AssistRun, rendered: str, schema: type[Any]) -> EventDraft:
        attendees = ["ana@example.org", "JEAN@example.org", "carol@example.org"]
        return EventDraft(found=True, summary="Lunch", attendees=attendees)

    monkeypatch.setattr(actions, "ask_slot", guests)

    event = await event_from_message(_run(), "m1", CLOCK, None)

    assert event.attendees == ["ana@example.org", "carol@example.org"]


async def test_an_event_is_still_read_when_the_mailbox_cannot_say_its_own_address(
    monkeypatch: pytest.MonkeyPatch, mailbox: list[str]
) -> None:
    async def guests(run: AssistRun, rendered: str, schema: type[Any]) -> EventDraft:
        return EventDraft(found=True, summary="Lunch", attendees=["ana@example.org"])

    class _Mute:
        async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
            return MESSAGE

        async def get_own_address(self) -> str | None:
            raise RuntimeError("profile unreadable")

    class _Opened:
        client = _Mute()
        connector_type = ConnectorType.GOOGLE_GMAIL

    @asynccontextmanager
    async def opening(tool: WorkbenchTool, user_id: object) -> AsyncIterator[_Opened]:
        yield _Opened()

    monkeypatch.setattr(actions, "ask_slot", guests)
    monkeypatch.setattr(actions, "open_tool_client", opening)

    event = await event_from_message(_run(), "m1", CLOCK, None)

    assert event.attendees == ["ana@example.org"], "the form shows the guests, unfiltered"


async def test_a_sentence_is_the_person_s_own_and_reads_no_source(
    asked: list[str], mailbox: list[str]
) -> None:
    run = _run()

    await event_from_sentence(run, "Lunch with Ana Thursday at noon", CLOCK)

    assert "Lunch with Ana Thursday at noon" in _data(asked[0])
    assert mailbox == []
    assert run.opened is False


async def test_the_day_of_the_week_is_told_so_a_relative_date_can_be_read(
    asked: list[str],
) -> None:
    await event_from_sentence(_run(), "Lunch Thursday", CLOCK)

    assert "Wednesday" in _data(asked[0])


async def test_a_task_is_read_from_the_message(asked: list[str], mailbox: list[str]) -> None:
    task = await task_from_message(_run(), "m1", CLOCK, [], None)

    assert task.title == "Pay"
    assert mailbox == ["m1"]


async def test_a_form_reads_whom_the_message_went_to_and_what_it_carries(
    asked: list[str], mailbox: list[str]
) -> None:
    await event_from_message(_run(), "m1", CLOCK, None)

    data = _data(asked[0])
    assert "From: ana@example.org" in data
    assert "To: Jean Dupont <jean@example.org>" in data
    assert "Cc: Carol <carol@example.org>" in data
    assert "menu.pdf" in data


async def test_a_task_from_a_message_is_read_against_the_person_s_lists(
    asked: list[str], mailbox: list[str]
) -> None:
    await task_from_message(_run(), "m1", CLOCK, ["Home", "Work"], None)

    data = _data(asked[0])
    assert "Home" in data
    assert "Work" in data


@pytest.mark.parametrize(
    "ask",
    [
        lambda run, focus: task_from_message(run, "m1", CLOCK, [], focus),
        lambda run, focus: event_from_message(run, "m1", CLOCK, focus),
    ],
    ids=["task", "event"],
)
async def test_a_focus_names_the_one_act_to_read_as_words_of_the_message(
    asked: list[str], mailbox: list[str], ask: Any
) -> None:
    await ask(_run(), "Send the signed lease by Friday")

    data = _data(asked[0])
    assert "Send the signed lease by Friday" in data
    assert assist_line("form_focus") in data
    assert data.count(EXTERNAL_CONTENT_OPEN_TAG) == 2, "the focus is the message's words too"


async def test_no_focus_says_nothing_of_one(asked: list[str], mailbox: list[str]) -> None:
    await task_from_message(_run(), "m1", CLOCK, [], None)

    data = _data(asked[0])
    assert assist_line("form_focus") not in data
    assert data.count(EXTERNAL_CONTENT_OPEN_TAG) == 1


async def test_a_sentence_can_name_one_of_the_person_s_lists(asked: list[str]) -> None:
    await task_from_sentence(_run(), "Pay the rent", CLOCK, ["Home", "Work"])

    assert "Home" in _data(asked[0])
    assert "Work" in _data(asked[0])


@pytest.mark.parametrize(
    "ask",
    [
        lambda run: event_from_sentence(run, "Nothing to plan here", CLOCK),
        lambda run: task_from_sentence(run, "Nothing to do here", CLOCK, []),
    ],
)
async def test_nothing_of_the_kind_is_a_refusal_never_an_empty_form(
    monkeypatch: pytest.MonkeyPatch, ask: Any
) -> None:
    async def nothing(run: AssistRun, rendered: str, schema: type[Any]) -> Any:
        return schema(found=False)

    monkeypatch.setattr(actions, "ask_slot", nothing)

    with pytest.raises(BaseAPIException) as refused:
        await ask(_run())

    assert _code(refused) == "assist_not_found"


async def test_found_with_no_title_is_nothing_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def untitled(run: AssistRun, rendered: str, schema: type[Any]) -> Any:
        return schema(found=True)

    monkeypatch.setattr(actions, "ask_slot", untitled)

    with pytest.raises(BaseAPIException) as refused:
        await event_from_sentence(_run(), "Something", CLOCK)

    assert _code(refused) == "assist_not_found"


async def test_steps_keep_their_order_and_only_what_says_something(asked: list[str]) -> None:
    steps = await steps_of_task(_run(), "Move out", "Before June")

    assert steps == ["One", "Two"]
    assert "Move out" in _data(asked[0])
    assert "Before June" in _data(asked[0])


async def test_no_step_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def none(run: AssistRun, rendered: str, schema: type[Any]) -> StepsDraft:
        return StepsDraft(steps=[])

    monkeypatch.setattr(actions, "ask_slot", none)

    with pytest.raises(BaseAPIException) as refused:
        await steps_of_task(_run(), "Move out", None)

    assert _code(refused) == "assist_failed"
