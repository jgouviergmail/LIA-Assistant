"""From words to an act the person finishes by hand (ADR-372).

A message or a sentence becomes a filled form, never an event or a task: the page opens its editor
and nothing exists until the person saves it. The model says what it read, and here that is held to
what a form can take: a value it could not read is left out, never guessed at (ADR-310), because a
day the page cannot understand would read as today. Nothing of the kind in the text is a refusal,
never an empty form. The account's day and zone travel with the words, so « Thursday » means their
Thursday.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Final, Literal

import structlog
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
from src.domains.agents.utils.content_wrapper import wrap_external_content
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot, assist_line
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import ASSIST_FAILED, ASSIST_NOT_FOUND, refuse
from src.domains.workbench.features import WorkbenchTool

logger = structlog.get_logger(__name__)

_MAIL = WorkbenchTool.MAIL
#: The rules a form offers in one press; anything else the person sets by hand.
REPEATS: Final = frozenset({"none", "daily", "weekly", "monthly", "yearly"})
#: How the prompt says no list was given.
_NO_LISTS: Final = "(none)"
#: The one importance a mail can raise a task to; anything else keeps the provider's default.
_HIGH: Final = "high"
#: A place that already carries a link: a video call there needs no second one.
_LINK: Final = re.compile(r"https?://", re.IGNORECASE)


class EventDraft(BaseModel):
    """What the model says of an event; empty means it was not said."""

    found: bool = Field(description="The text describes something to put in a calendar.")
    summary: str = Field(
        default="", max_length=WORKBENCH_EVENT_SUMMARY_MAX_CHARS, description="A short title."
    )
    start_date: str = Field(default="", description="The first day, YYYY-MM-DD.")
    start_time: str = Field(default="", description="Its hour, HH:MM, on the person's clock.")
    end_date: str = Field(default="", description="The last day, YYYY-MM-DD.")
    end_time: str = Field(default="", description="Its hour, HH:MM, on the person's clock.")
    all_day: bool = Field(default=False, description="It takes whole days.")
    location: str = Field(
        default="",
        max_length=WORKBENCH_EVENT_LOCATION_MAX_CHARS,
        description="The place, as written.",
    )
    description: str = Field(
        default="",
        max_length=WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS,
        description="What the person will need from the text.",
    )
    attendees: list[str] = Field(
        default_factory=list,
        max_length=WORKBENCH_EVENT_ATTENDEES_MAX,
        description="Addresses the text writes.",
    )
    repeat: str = Field(default="none", description="none, daily, weekly, monthly or yearly.")
    conference: bool = Field(
        default=False, description="The text asks for a video call and gives no link for it."
    )


class TaskDraft(BaseModel):
    """What the model says of a task; empty means it was not said."""

    found: bool = Field(description="The text holds something for the person to do.")
    title: str = Field(
        default="",
        max_length=WORKBENCH_TASK_TITLE_MAX_CHARS,
        description="What is to be done, in a few words.",
    )
    notes: str = Field(
        default="",
        max_length=WORKBENCH_TASK_NOTES_MAX_CHARS,
        description="What the person will need to do it.",
    )
    due: str = Field(default="", description="The day it is due, YYYY-MM-DD.")
    list_name: str = Field(default="", description="The list it names, as given.")
    importance: str = Field(default="", description="high when the text says it is urgent.")


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
    conference: bool = Field(
        default=False, description="A video call is to be made with it: none is given yet."
    )


class ProposedTask(BaseModel):
    """A task as a form can take it."""

    title: str = Field(description="What is to be done.")
    notes: str = Field(default="", description="What is needed to do it.")
    due: str | None = Field(default=None, description="The day it is due, YYYY-MM-DD.")
    list_name: str | None = Field(default=None, description="One of the person's lists.")
    importance: Literal["high"] | None = Field(
        default=None, description="high when the text says it is urgent; else the provider's own."
    )


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


def _addresses(values: list[str], own_address: str | None) -> list[str]:
    """The addresses that can be written to, each once whatever its case, in their order, the
    person's own mailbox left out: they do not invite themselves."""
    seen = {own_address.strip().casefold()} if own_address else set()
    kept: list[str] = []
    for value in (raw.strip() for raw in values):
        if validate_email(value) and value.casefold() not in seen:
            seen.add(value.casefold())
            kept.append(value)
    return kept[:WORKBENCH_EVENT_ATTENDEES_MAX]


def proposed_event(draft: EventDraft, own_address: str | None = None) -> ProposedEvent:
    """Hold what the model said to what the editor can take.

    Args:
        draft: Its answer.
        own_address: The mailbox the message was read in, when known: never one of its guests.

    Returns:
        The event: a value nobody can read is left out, and an end that does not follow its start
        goes with it. A video call is proposed only where its place holds no link already.
    """
    start_day = readable_day(draft.start_date)
    start_hour = None if draft.all_day or start_day is None else _hour(draft.start_time)
    end_day = readable_day(draft.end_date) if start_day else None
    end_hour = None if draft.all_day or end_day is None else _hour(draft.end_time)
    if end_day and (end_day, end_hour or "") < (start_day or "", start_hour or ""):
        end_day, end_hour = None, None
    location = draft.location.strip()
    return ProposedEvent(
        summary=draft.summary.strip(),
        start_date=start_day,
        start_time=start_hour,
        end_date=end_day,
        end_time=end_hour,
        all_day=draft.all_day,
        location=location,
        description=draft.description.strip(),
        attendees=_addresses(draft.attendees, own_address),
        repeat=draft.repeat if draft.repeat in REPEATS else "none",
        conference=draft.conference and not _LINK.search(location),
    )


def proposed_task(draft: TaskDraft, lists: list[str]) -> ProposedTask:
    """Hold what the model said to what a task can take.

    Args:
        draft: Its answer.
        lists: The person's lists: a task goes to one of them, or stays where it was added.

    Returns:
        The task: important only when the text says it is urgent.
    """
    named = draft.list_name.strip().casefold()
    return ProposedTask(
        title=draft.title.strip(),
        notes=draft.notes.strip(),
        due=readable_day(draft.due),
        list_name=next((name for name in lists if name.casefold() == named), None),
        importance=_HIGH if draft.importance.strip().casefold() == _HIGH else None,
    )


@dataclass(frozen=True, slots=True)
class _Received:
    """A message as a form reads it, and the mailbox it was read in when that matters."""

    source: str
    own_address: str | None


async def _own_address(client: EmailClientProtocol) -> str | None:
    """The mailbox's own address. Unread, the guests stand unfiltered in the form the person
    checks: a filter is no reason to refuse the event."""
    try:
        return await client.get_own_address()
    except Exception as error:  # noqa: BLE001 - optional, said in the log, never the event's end
        logger.info("tool_assist_own_address_unread", error_type=type(error).__name__)
        return None


async def _received(run: AssistRun, message_id: str, *, own_address: bool) -> _Received:
    """The message as a form reads it: a stranger's words, marked as such, with whom it went to
    and the files it carries; the mailbox's own address when the form has guests to sort."""
    async with open_tool_client(_MAIL, run.user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with run.reading(), provider_call(_MAIL, "read", act=False):
            message: dict[str, Any] = await client.get_message(message_id, use_cache=False)
        own = await _own_address(client) if own_address else None
    return _Received(received_as_external(message, recipients=True), own)


def _focus_note(message_id: str, focus: str | None) -> str:
    """The one act or passage the message is read for, as the message's own words; else nothing."""
    if not focus:
        return ""
    passage = wrap_external_content(focus, source_url=message_id, source_type="email")
    return f"{assist_line('form_focus')}\n{passage}"


async def _event(
    run: AssistRun,
    source: str,
    clock: AssistClock,
    focus_note: str = "",
    own_address: str | None = None,
) -> ProposedEvent:
    prompt = load_prompt("tool_assist_event_prompt").format(
        today=clock.today.isoformat(),
        weekday=clock.today.strftime("%A"),
        zone=clock.zone,
        focus_note=focus_note,
        source=source,
    )
    draft = await ask_slot(run, prompt, EventDraft)
    event = proposed_event(draft, own_address)
    if not draft.found or not event.summary:
        refuse(ASSIST_NOT_FOUND)
    return event


async def event_from_message(
    run: AssistRun, message_id: str, clock: AssistClock, focus: str | None
) -> ProposedEvent:
    """The event a received message describes.

    Args:
        run: The assist's run.
        message_id: The message.
        clock: The person's day and zone.
        focus: The passage the person chose in it, if any: the event read is that one.

    Returns:
        The event, for the editor: its guests never include the mailbox it was read in.
    """
    read = await _received(run, message_id, own_address=True)
    return await _event(run, read.source, clock, _focus_note(message_id, focus), read.own_address)


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


async def _task(
    run: AssistRun, source: str, clock: AssistClock, lists: list[str], focus_note: str = ""
) -> ProposedTask:
    prompt = load_prompt("tool_assist_task_prompt").format(
        today=clock.today.isoformat(),
        weekday=clock.today.strftime("%A"),
        zone=clock.zone,
        lists=", ".join(lists) or _NO_LISTS,
        focus_note=focus_note,
        source=source,
    )
    draft = await ask_slot(run, prompt, TaskDraft)
    task = proposed_task(draft, lists)
    if not draft.found or not task.title:
        refuse(ASSIST_NOT_FOUND)
    return task


async def task_from_message(
    run: AssistRun, message_id: str, clock: AssistClock, lists: list[str], focus: str | None
) -> ProposedTask:
    """The task a received message leaves the person.

    Args:
        run: The assist's run.
        message_id: The message.
        clock: The person's day and zone.
        lists: The names of their lists: the task goes to one the message points to.
        focus: The act or passage the person chose in it, if any: the task read is that one.

    Returns:
        The task, for its form.
    """
    read = await _received(run, message_id, own_address=False)
    return await _task(run, read.source, clock, lists, _focus_note(message_id, focus))


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
