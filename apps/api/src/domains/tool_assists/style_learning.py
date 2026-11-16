"""Learning how the person writes, at their click in the settings (ADR-383 amendment 2026-11-16).

The click asks a model on the instance's key, so it goes through the assists' door
(``run_assist``): both spending ceilings asked first, the spend billed to the account,
the read of the sent mail filed on the same run, the outcome counted. It is the account's
one learning at a time, whichever surface asked (``learn_one_at_a_time``): a second
click — another tab, another worker — or the assistant's confirmed card waits for the
first and answers what it learned, never pays twice. The click replaces the record the
person sees when it arrives, and nothing since: a forget confirmed meanwhile stands. No
session is held while the mailbox and the model answer (ADR-304): the account comes
through the stream-safe dependency.

Served under ``/writing-style`` beside the section's own routes, whatever the operator's
switch on the Tools says: learning a voice is not a Tool. The route lives here because
the door does — ``writing_style`` importing ``agents`` would close an import cycle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from src.core.config import settings
from src.core.i18n import normalize_language
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.agents.emails.writing_style import (
    Learning,
    LearningOutcome,
    SentMailUnreadable,
    learn_one_at_a_time,
    learn_writing_style,
    learned_record_at,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import AssistRun, run_assist
from src.domains.tool_assists.schemas import AssistAnswer
from src.domains.users.models import User
from src.domains.workbench.errors import refuse_provider_failure

rate_limit_style_learning = create_user_rate_limiter(
    "writing_style_learn",
    max_calls=settings.tool_assist_rate_limit_calls,
    window_seconds=settings.tool_assist_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)

Person = Annotated[User, Depends(get_current_active_session_for_stream)]

router = APIRouter(
    prefix="/writing-style",
    tags=["Writing style"],
    dependencies=[Depends(rate_limit_style_learning)],
)


class WritingStyleLearning(AssistAnswer):
    """How the learning the person asked for ended, and what it cost."""

    outcome: LearningOutcome = Field(
        description=(
            "learned; too_few (too few sent e-mails, nothing learned); no_mailbox (no "
            "mailbox connected); reconnect (the mailbox refuses LIA's access); "
            "switched_off (the person's switch went off: nothing was kept); superseded "
            "(the style was forgotten or learned again meanwhile: this learning kept "
            "nothing)"
        )
    )
    mails_read: int = Field(description="How many sent e-mails were read (0 when none was)")


async def _learned(run: AssistRun, user_id: UUID, replaces: datetime | None) -> Learning:
    """Learn on the assist's run; a mailbox's own failure is said in the page's words."""
    try:
        return await learn_writing_style(
            user_id, replaces=replaces, config=run.config, reading=run.reading
        )
    except SentMailUnreadable as unreadable:
        refuse_provider_failure(unreadable.__cause__ or unreadable, act=False)


@router.post(
    "/learn",
    response_model=WritingStyleLearning,
    summary="Learn the person's writing style now",
    description=(
        "Reads the person's latest sent e-mails and learns how they write — their voice, "
        "never their facts — replacing what was learned before. Nothing else ever learns it."
    ),
)
async def learn_writing_style_now(user: Person) -> WritingStyleLearning:
    """Learn the style at the person's click, the account's one learning at a time.

    Args:
        user: The authenticated account.

    Returns:
        How it ended, and what it cost (nothing when another request's learning served it).

    Raises:
        BaseAPIException: A workbench refusal: a spending ceiling, the mailbox's failure,
            or no usable answer from the model.
    """
    # What the click replaces is read as it arrives, before anything waits.
    replaces = await learned_record_at(user.id)

    async def work(run: AssistRun) -> Learning:
        return await learn_one_at_a_time(user.id, lambda: _learned(run, user.id, replaces))

    done = await run_assist(
        ToolAssist.WRITING_STYLE_LEARN, user.id, normalize_language(user.language), work
    )
    return WritingStyleLearning(
        outcome=done.value.outcome, mails_read=done.value.mails_read, usage=done.usage
    )


__all__ = ["WritingStyleLearning", "router"]
