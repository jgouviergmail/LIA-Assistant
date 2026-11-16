"""Learning the writing style from the conversation, on the person's exact confirmation.

The card binds what the settings would do at the click — the switch on, the latest sent
e-mails read, the record it replaces — and the learning runs on the confirmed turn: the
read of the sent mail is filed as the turn's consultation and the model call is billed to
the turn (``writing_style.py``, the ``TURN`` road). It is the account's one learning at
a time, the same claim the settings' click takes (``learn_one_at_a_time``), and it keeps
its result only in place of the record the card bound. The transaction that checked the
card is committed before the mailbox and the model are waited on (ADR-304). How the
learning ended is said in the tools' vocabulary (ADR-303): a missing mailbox is
``CONNECTOR_NOT_ACTIVATED``, a mailbox refusing LIA's access ``UNAUTHORIZED``, a switch
turned off or a record forgotten or learned again meanwhile a stale state; too few
e-mails is a learning that kept what it found.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.writing_style_queries import learn_scope
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleLearnPatch,
    WritingStyleLearnRequest,
    WritingStyleRecord,
)
from src.domains.agents.application.writing_style_spec import WRITING_STYLE_LEARN_OPERATION
from src.domains.agents.emails.writing_style import (
    EmptyStyleProfile,
    SentMailUnreadable,
    learn_one_at_a_time,
    learn_writing_style,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.workbench.errors import (
    PROVIDER_RATE_LIMITED,
    RECONNECT_REQUIRED,
    refusal_for,
)

#: How a mailbox's own failure reads in the tools' vocabulary (classified structurally).
_MAILBOX_FAILURES: dict[str, ToolErrorCode] = {
    RECONNECT_REQUIRED: ToolErrorCode.UNAUTHORIZED,
    PROVIDER_RATE_LIMITED: ToolErrorCode.RATE_LIMIT_EXCEEDED,
}


def _stale() -> ResourceConflictError:
    return ResourceConflictError("writing_style", detail={"error_code": "STALE_STATE"})


def _instant(record: WritingStyleRecord | None) -> datetime | None:
    """The instant naming the record a card bound, None for nothing learned (pure)."""
    return datetime.fromisoformat(record.learned_at) if record is not None else None


async def prepare_writing_style_learning(
    db: AsyncSession,
    actor_id: UUID,
    request: WritingStyleLearnRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    """The card of a learning: what it reads and the record it replaces; nothing read yet."""
    WritingStyleLearnRequest.model_validate(request.model_dump())
    scope = await learn_scope(db, actor_id)
    public = scope.model_dump(mode="json")
    return build_action_content(
        actor_id,
        WRITING_STYLE_LEARN_OPERATION,
        WritingStyleLearnPatch(writing_style_learning=scope),
        {"writing_style_learning": public},
        {"writing_style_learning": {**public, "requested": True}},
        command_id=command_id,
    )


def canonical_writing_style_learning(draft: ApplicationActionDraftContent) -> bool:
    """Whether the card says exactly what its intent binds (pure)."""
    learning = WritingStyleLearnPatch.model_validate(draft.intent).writing_style_learning
    scope = learning.model_dump(mode="json")
    return draft.before == {"writing_style_learning": scope} and draft.after == {
        "writing_style_learning": {**scope, "requested": True}
    }


def mailbox_failure_code(error: BaseException) -> str:
    """The tools' code for a mailbox that answered the read with a failure (pure)."""
    code, _facts = refusal_for(error, act=False)
    return _MAILBOX_FAILURES.get(code, ToolErrorCode.EXTERNAL_API_ERROR).value


async def execute_writing_style_learning(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    """Learn on the confirmed state, then say how it ended.

    Raises:
        CommandRejected: Not the actor's card, expired, or a learning that could not
            keep anything (its code says why).
        ResourceConflictError: The switch or the record changed since the card.
    """
    if (
        draft.actor_id != actor_id
        or draft.operation_id != WRITING_STYLE_LEARN_OPERATION.operation_id
    ):
        raise CommandRejected("FORBIDDEN")
    if not canonical_writing_style_learning(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = WritingStyleLearnPatch.model_validate(draft.intent).writing_style_learning
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    if await learn_scope(db, actor_id) != expected:
        raise _stale()
    replaces = _instant(expected.replaces)
    # Nothing is held while the mailbox and the model answer (ADR-304).
    await db.commit()
    try:
        learning = await learn_one_at_a_time(
            actor_id, lambda: learn_writing_style(actor_id, replaces=replaces, config=None)
        )
    except SentMailUnreadable as unreadable:
        cause = unreadable.__cause__ or unreadable
        raise CommandRejected(mailbox_failure_code(cause)) from unreadable
    except EmptyStyleProfile as empty:
        raise CommandRejected(ToolErrorCode.EMPTY_RESULT.value) from empty
    if learning.outcome == "no_mailbox":
        raise CommandRejected(ToolErrorCode.CONNECTOR_NOT_ACTIVATED.value)
    if learning.outcome == "reconnect":
        raise CommandRejected(ToolErrorCode.UNAUTHORIZED.value)
    if learning.outcome in ("switched_off", "superseded"):
        raise _stale()
    receipt.committed = True
    receipt.values = {
        "writing_style_learning": {
            "outcome": learning.outcome,
            "mails_read": learning.mails_read,
        }
    }
