"""What a person says of their mailbox, as criteria they can see and change (ADR-372).

A sentence becomes a search on screen or a filter in its form, never an act: the page shows the
criteria, the person changes them or not, and only then does anything run. The model is held to
what the screen can take: an unreadable day is left out, a label nobody has is dropped, and every
value stays under the bound its field publishes.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, Field

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.domains.agents.prompts import load_prompt
from src.domains.tool_assists.actions import AssistClock, readable_day
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.workbench.errors import ASSIST_NOT_FOUND, refuse
from src.domains.workbench.schemas.mail_settings import FILTER_CRITERION_MAX_CHARS

#: How the prompt says the person has no label.
_NO_LABELS: Final = "(none)"


class SearchDraft(BaseModel):
    """What the model says the person is looking for; empty means it was not said."""

    words: str = Field(default="", description="The search, in the search language.")
    unread: bool = Field(default=False, description="Only what was not read.")
    attachments: bool = Field(default=False, description="Only what carries files.")
    first_day: str = Field(default="", description="The first day, YYYY-MM-DD.")
    last_day: str = Field(default="", description="The last day, YYYY-MM-DD.")


class ProposedSearch(BaseModel):
    """A search as the screen can take it."""

    words: str = Field(description="The search, as the box shows it.")
    unread: bool = Field(description="Only what was not read.")
    attachments: bool = Field(description="Only what carries files.")
    first_day: str | None = Field(default=None, description="The first day, YYYY-MM-DD.")
    last_day: str | None = Field(default=None, description="The last day, YYYY-MM-DD.")


class FilterDraft(BaseModel):
    """What the model says of a filter; empty means it was not said."""

    found: bool = Field(description="The sentence says which mail, and what to do with it.")
    sender: str = Field(default="", description="Who it comes from.")
    recipient: str = Field(default="", description="Who it is addressed to.")
    subject: str = Field(default="", description="Words of its subject.")
    words: str = Field(default="", description="Other words it holds.")
    has_attachment: bool = Field(default=False, description="It carries files.")
    label: str = Field(default="", description="The label or folder it names, as given.")
    archive: bool = Field(default=False, description="It skips the inbox.")
    mark_read: bool = Field(default=False, description="It is marked read.")


class ProposedFilter(BaseModel):
    """A filter as its form can take it."""

    sender: str = Field(default="", description="Who it comes from.")
    recipient: str = Field(default="", description="Who it is addressed to.")
    subject: str = Field(default="", description="Words of its subject.")
    words: str = Field(default="", description="Other words it holds.")
    has_attachment: bool = Field(default=False, description="It carries files.")
    label: str | None = Field(default=None, description="One of the person's labels.")
    archive: bool = Field(default=False, description="It skips the inbox.")
    mark_read: bool = Field(default=False, description="It is marked read.")


def proposed_search(draft: SearchDraft) -> ProposedSearch:
    """What the screen can take of a search; asking for nothing is a refusal, never a blank.

    Args:
        draft: What the model read.

    Returns:
        The criteria.

    Raises:
        BaseAPIException: The sentence narrows nothing.
    """
    first, last = readable_day(draft.first_day), readable_day(draft.last_day)
    words = draft.words.strip()[:WORKBENCH_MAIL_QUERY_MAX_CHARS]
    if not (words or draft.unread or draft.attachments or first or last):
        refuse(ASSIST_NOT_FOUND)
    return ProposedSearch(
        words=words,
        unread=draft.unread,
        attachments=draft.attachments,
        first_day=first,
        last_day=last,
    )


def proposed_filter(draft: FilterDraft, labels: list[str]) -> ProposedFilter:
    """What a form can take of a filter: matching something and doing something, or a refusal.

    Args:
        draft: What the model read.
        labels: The person's labels, as they named them.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: The sentence does not say which mail, or what to do with it.
    """
    criterion = FILTER_CRITERION_MAX_CHARS
    label = draft.label.strip()
    named = next((known for known in labels if known.casefold() == label.casefold()), None)
    proposal = ProposedFilter(
        sender=draft.sender.strip()[:criterion],
        recipient=draft.recipient.strip()[:criterion],
        subject=draft.subject.strip()[:criterion],
        words=draft.words.strip()[:criterion],
        has_attachment=draft.has_attachment,
        label=named,
        archive=draft.archive,
        mark_read=draft.mark_read,
    )
    matches = (
        proposal.sender,
        proposal.recipient,
        proposal.subject,
        proposal.words,
        proposal.has_attachment,
    )
    acts = (proposal.label, proposal.archive, proposal.mark_read)
    if not (draft.found and any(matches) and any(acts)):
        refuse(ASSIST_NOT_FOUND)
    return proposal


async def search_from_sentence(run: AssistRun, sentence: str, clock: AssistClock) -> ProposedSearch:
    """The criteria a sentence amounts to: the listing runs once the screen holds them.

    Args:
        run: The assist's run.
        sentence: The person's words.
        clock: The person's day and zone.

    Returns:
        The criteria.

    Raises:
        BaseAPIException: The sentence narrows nothing, or no usable answer came.
    """
    prompt = load_prompt("tool_assist_search_prompt").format(
        today=clock.today.isoformat(),
        weekday=clock.today.strftime("%A"),
        zone=clock.zone,
        sentence=sentence,
    )
    return proposed_search(await ask_slot(run, prompt, SearchDraft))


async def filter_from_sentence(run: AssistRun, sentence: str, labels: list[str]) -> ProposedFilter:
    """The filter a sentence describes, for its form: nothing is created.

    Args:
        run: The assist's run.
        sentence: The person's words.
        labels: The person's labels or folders.

    Returns:
        The filled form.

    Raises:
        BaseAPIException: No filter in the sentence, or no usable answer came.
    """
    prompt = load_prompt("tool_assist_filter_prompt").format(
        labels=", ".join(labels) or _NO_LABELS,
        sentence=sentence,
    )
    return proposed_filter(await ask_slot(run, prompt, FilterDraft), labels)
