"""AI-prepared native records: bounded fields, no write and no invented reminder clock."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from src.core.config import settings
from src.core.constants import RECURRENCE_REMINDER_LIMITS, REMINDER_CONTENT_MAX_CHARS
from src.core.i18n import get_language_name
from src.core.recurrence import RecurrenceSpec, next_occurrence
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.prompts import load_prompt
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.users.models import User
from src.domains.workbench.errors import ASSIST_NOT_FOUND, refuse


class ProposedReminder(BaseModel):
    """What the reminder editor can review, with no guessed schedule."""

    content: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=REMINDER_CONTENT_MAX_CHARS
        ),
    ] = Field(description="What to remind the person, faithful to the selected text.")
    recurrence: RecurrenceSpec | None = Field(
        default=None,
        description="The stated schedule; null if a date, time or repetition is unclear.",
    )


class ProposedTicket(BaseModel):
    """The ticket's meaning; its holder and execution settings remain the person's choice."""

    title: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=settings.workboard_title_max_chars
        ),
    ] = Field(description="A short title grounded in the selected text.")
    description: str = Field(
        default="",
        max_length=settings.workboard_description_max_chars,
        description="The work, context, constraints and any dates stated in the source.",
    )


class ReminderProposal(BaseModel):
    kind: Literal["reminder"] = Field(
        default="reminder", description="The native reminder creation form."
    )
    reminder: ProposedReminder = Field(description="Fields for review, never an armed reminder.")


class TicketProposal(BaseModel):
    kind: Literal["ticket"] = Field(
        default="ticket", description="The native ticket creation form."
    )
    ticket: ProposedTicket = Field(description="Fields for review, never an assigned ticket.")


def admit_reminder(draft: ProposedReminder, zone: str, now: datetime) -> ProposedReminder:
    """Refuse an impossible, expired or over-limit schedule using the consumer's real engine."""
    if draft.recurrence is None:
        return draft
    try:
        draft.recurrence.validate_against(RECURRENCE_REMINDER_LIMITS)
        future = next_occurrence(draft.recurrence, zone, after=now)
    except ValueError:
        refuse(ASSIST_NOT_FOUND)
    if future is None:
        refuse(ASSIST_NOT_FOUND)
    return draft


async def propose_record(
    run: AssistRun, source: str, user: User, kind: Literal["reminder", "ticket"]
) -> ReminderProposal | TicketProposal:
    """Prepare one record under the caller's accounting, without opening any personal source.

    Args:
        run: The common assist's accounting and language.
        source: The complete selection, already marked as untrusted external content.
        user: Detached account settings; no database session is held.
        kind: The native form the person explicitly requested.

    Returns:
        Reviewable fields; the native form owns the eventual write.
    """
    zone = resolve_user_timezone(user)
    now = datetime.now(UTC)
    prompt = load_prompt("tool_assist_record_prompt").format(
        kind=kind,
        language=get_language_name(run.language),
        now=now.astimezone(zone).isoformat(),
        zone=str(zone),
        content_max=REMINDER_CONTENT_MAX_CHARS,
        title_max=settings.workboard_title_max_chars,
        description_max=settings.workboard_description_max_chars,
        times_max=RECURRENCE_REMINDER_LIMITS.max_times_per_day,
        step_min=RECURRENCE_REMINDER_LIMITS.min_step_minutes,
        series_max=RECURRENCE_REMINDER_LIMITS.max_series_count,
        source=source,
    )
    if kind == "reminder":
        draft = await ask_slot(run, prompt, ProposedReminder)
        return ReminderProposal(reminder=admit_reminder(draft, str(zone), now))
    return TicketProposal(ticket=await ask_slot(run, prompt, ProposedTicket))
