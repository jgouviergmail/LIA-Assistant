"""From words to an act the person finishes by hand (ADR-372).

A message or a sentence becomes a filled form, never an event or a task: the page opens its editor
and nothing exists until the person saves it. The model says what it read, and here that is held to
what a form can take: a value it could not read is left out, never guessed at (ADR-310), because a
day the page cannot understand would read as today. Nothing of the kind in the text is a refusal,
never an empty form. The account's day and zone travel with the words, so « Thursday » means their
Thursday.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final

from pydantic import BaseModel, Field

from src.core.constants import (
    TOOL_ASSIST_STEPS_MAX,
    WORKBENCH_EVENT_ATTENDEES_MAX,
    WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS,
    WORKBENCH_EVENT_LOCATION_MAX_CHARS,
    WORKBENCH_EVENT_SUMMARY_MAX_CHARS,
    WORKBENCH_TASK_NOTES_MAX_CHARS,
    WORKBENCH_TASK_TITLE_MAX_CHARS,
)
from src.core.validators import validate_email
from src.domains.agents.emails.reply_drafting import received_as_external
from src.domains.agents.prompts import load_prompt
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import ASSIST_FAILED, ASSIST_NOT_FOUND, refuse
from src.domains.workbench.features import WorkbenchTool

_MAIL = WorkbenchTool.MAIL
#: The rules a form offers in one press; anything else the person sets by hand.
REPEATS: Final = frozenset({"none", "daily", "weekly", "monthly", "yearly"})
#: How the prompt says no list was given.
_NO_LISTS: Final = "(none)"


class EventDraft(BaseModel):
    """What the model says of an event; empty means it was not said."""

    found: bool = Field(description="The text describes something to put in a calendar.")
    summary: str = Field(default="", description="A short title.")
    start_date: str = Field(default="", description="The first day, YYYY-MM-DD.")
    start_time: str = Field(default="", description="Its hour, HH:MM, on the person's clock.")
    end_date: str = Field(default="", description="The last day, YYYY-MM-DD.")
    end_time: str = Field(default="", description="Its hour, HH:MM, on the person's clock.")
    all_day: bool = Field(default=False, description="It takes whole days.")
    location: str = Field(default="", description="The place, as written.")
    description: str = Field(default="", description="What the person will need from the text.")
    attendees: list[str] = Field(default_factory=list, description="Addresses the text writes.")
    repeat: str = Field(default="none", description="none, daily, weekly, monthly or yearly.")


class TaskDraft(BaseModel):
    """What the model says of a task; empty means it was not said."""

    found: bool = Field(description="The text holds something for the person to do.")
    title: str = Field(default="", description="What is to be done, in a few words.")
    notes: str = Field(default="", description="What the person will need to do it.")
    due: str = Field(default="", description="The day it is due, YYYY-MM-DD.")
    list_name: str = Field(default="", description="The list it names, as given.")


class StepsDraft(BaseModel):
    """The steps the model proposes, in order."""

    steps: list[str] = Field(default_factory=list, description="Short concrete actions.")


class ProposedEvent(BaseModel):
    """An event as a form can take it: what is left out was not said, or not readable."""

    summary: str = Field(description="Its title.")
    start_date: str | None = Field(default=None, description="The first day, YYYY-MM-DD.")
    start_time: str | None = Field(default=None, description="Its hour, HH:MM.")
    end_date: str | None = Field(default=None, description="The last day, YYYY-MM-DD.")
    end_time: str | None = Field(default=None, description="Its hour, HH:MM.")
    all_day: bool = Field(default=False, description="It takes whole days.")
    location: str = Field(default="", description="Where it is.")
    description: str = Field(default="", description="What it is about.")
    attendees: list[str] = Field(default_factory=list, description="Who it invites.")
    repeat: str = Field(default="none", description="none, daily, weekly, monthly or yearly.")


class ProposedTask(BaseModel):
    """A task as a form can take it."""

    title: str = Field(description="What is to be done.")
    notes: str = Field(default="", description="What is needed to do it.")
    due: str | None = Field(default=None, description="The day it is due, YYYY-MM-DD.")
    list_name: str | None = Field(default=None, description="One of the person's lists.")


@dataclass(frozen=True, slots=True)
class AssistClock:
    """The person's day and zone: what makes « Thursday » a date."""

    today: date
    zone: str


def readable_day(value: str) -> str | None:
    """A day a form can read, or None."""
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _hour(value: str) -> str | None:
    """An hour a form can read, or None."""
    try:
        return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


def _addresses(values: list[str]) -> list[str]:
    """The addresses that can be written to, each once, in their order."""
    usable = [value.strip() for value in values if validate_email(value.strip())]
    return list(dict.fromkeys(usable))[:WORKBENCH_EVENT_ATTENDEES_MAX]


def proposed_event(draft: EventDraft) -> ProposedEvent:
    """Hold what the model said to what the editor can take.

    Args:
        draft: Its answer.

    Returns:
        The event: a value nobody can read is left out, and an end that does not follow its start
        goes with it.
    """
    start_day = readable_day(draft.start_date)
    start_hour = None if draft.all_day or start_day is None else _hour(draft.start_time)
    end_day = readable_day(draft.end_date) if start_day else None
    end_hour = None if draft.all_day or end_day is None else _hour(draft.end_time)
    if end_day and (end_day, end_hour or "") < (start_day or "", start_hour or ""):
        end_day, end_hour = None, None
    return ProposedEvent(
        summary=draft.summary.strip()[:WORKBENCH_EVENT_SUMMARY_MAX_CHARS],
        start_date=start_day,
        start_time=start_hour,
        end_date=end_day,
        end_time=end_hour,
        all_day=draft.all_day,
        location=draft.location.strip()[:WORKBENCH_EVENT_LOCATION_MAX_CHARS],
        description=draft.description.strip()[:WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS],
        attendees=_addresses(draft.attendees),
        repeat=draft.repeat if draft.repeat in REPEATS else "none",
    )


def proposed_task(draft: TaskDraft, lists: list[str]) -> ProposedTask:
    """Hold what the model said to what a task can take.

    Args:
        draft: Its answer.
        lists: The person's lists: a task goes to one of them, or stays where it was added.

    Returns:
        The task.
    """
    named = draft.list_name.strip().casefold()
    return ProposedTask(
        title=draft.title.strip()[:WORKBENCH_TASK_TITLE_MAX_CHARS],
        notes=draft.notes.strip()[:WORKBENCH_TASK_NOTES_MAX_CHARS],
        due=readable_day(draft.due),
        list_name=next((name for name in lists if name.casefold() == named), None),
    )


async def _received(run: AssistRun, message_id: str) -> str:
    """The message as the model reads it: a stranger's words, marked as such."""
    async with open_tool_client(_MAIL, run.user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with run.reading(), provider_call(_MAIL, "read", act=False):
            message: dict[str, Any] = await client.get_message(message_id, use_cache=False)
    return received_as_external(message)


async def _event(run: AssistRun, source: str, clock: AssistClock) -> ProposedEvent:
    prompt = load_prompt("tool_assist_event_prompt").format(
        today=clock.today.isoformat(),
        weekday=clock.today.strftime("%A"),
        zone=clock.zone,
        source=source,
    )
    draft = await ask_slot(run, prompt, EventDraft)
    event = proposed_event(draft)
    if not draft.found or not event.summary:
        refuse(ASSIST_NOT_FOUND)
    return event


async def event_from_message(run: AssistRun, message_id: str, clock: AssistClock) -> ProposedEvent:
    """The event a received message describes.

    Args:
        run: The assist's run.
        message_id: The message.
        clock: The person's day and zone.

    Returns:
        The event, for the editor.
    """
    return await _event(run, await _received(run, message_id), clock)


async def event_from_sentence(run: AssistRun, sentence: str, clock: AssistClock) -> ProposedEvent:
    """The event a person describes in their own words.

    Args:
        run: The assist's run.
        sentence: Their words.
        clock: Their day and zone.

    Returns:
        The event, for the editor.
    """
    return await _event(run, sentence, clock)


async def _task(run: AssistRun, source: str, clock: AssistClock, lists: list[str]) -> ProposedTask:
    prompt = load_prompt("tool_assist_task_prompt").format(
        today=clock.today.isoformat(),
        weekday=clock.today.strftime("%A"),
        zone=clock.zone,
        lists=", ".join(lists) or _NO_LISTS,
        source=source,
    )
    draft = await ask_slot(run, prompt, TaskDraft)
    task = proposed_task(draft, lists)
    if not draft.found or not task.title:
        refuse(ASSIST_NOT_FOUND)
    return task


async def task_from_message(run: AssistRun, message_id: str, clock: AssistClock) -> ProposedTask:
    """The task a received message leaves the person.

    Args:
        run: The assist's run.
        message_id: The message.
        clock: The person's day and zone.

    Returns:
        The task, for its form.
    """
    return await _task(run, await _received(run, message_id), clock, [])


async def task_from_sentence(
    run: AssistRun, sentence: str, clock: AssistClock, lists: list[str]
) -> ProposedTask:
    """The task a person describes in their own words.

    Args:
        run: The assist's run.
        sentence: Their words.
        clock: Their day and zone.
        lists: The names of their lists.

    Returns:
        The task, for them to add.
    """
    return await _task(run, sentence, clock, lists)


async def steps_of_task(run: AssistRun, title: str, notes: str | None) -> list[str]:
    """The steps a task breaks down into, proposed.

    Args:
        run: The assist's run.
        title: The task.
        notes: Its notes, if any.

    Returns:
        The steps, in order.
    """
    prompt = load_prompt("tool_assist_steps_prompt").format(
        steps_max=TOOL_ASSIST_STEPS_MAX, title=title, notes=notes or ""
    )
    draft = await ask_slot(run, prompt, StepsDraft)
    steps = [step.strip() for step in draft.steps if step.strip()]
    if not steps:
        refuse(ASSIST_FAILED)
    return [step[:WORKBENCH_TASK_TITLE_MAX_CHARS] for step in steps[:TOOL_ASSIST_STEPS_MAX]]
