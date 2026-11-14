"""Short SQL transitions of the message that waits for its turn (ADR-384, ADR-385).

Flush only: the operation's caller owns the single commit, and every caller that
decides on the account's occupancy holds the owner lock admission takes.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CHAT_MESSAGE_MAX_LENGTH, WAITING_MESSAGE_SEPARATOR
from src.core.conversation_execution import RunEnd
from src.core.conversation_target import ConversationRef
from src.core.repository import BaseRepository
from src.domains.conversations.waiting_models import WaitingMessage, WaitingStatus

_PENDING = (WaitingStatus.WAITING, WaitingStatus.HELD)
#: What the person may still change: a joining note is read only at the loop's next call.
_CHANGEABLE = (*_PENDING, WaitingStatus.JOINING)


@dataclass(frozen=True, slots=True)
class SettledRelease:
    """What a release did to the account's waiting messages."""

    #: Messages that will now leave only on the person's click.
    held: int
    #: Notes the closing run never read, given back to the waiting state.
    returned: int


#: A close that settled nothing (it did not close, or nothing waited).
NOTHING_SETTLED = SettledRelease(held=0, returned=0)


class WaitingMessageTooLong(Exception):
    """The words added would make the waiting message longer than one message may be."""


class WaitingMessageDeparting(Exception):
    """The discussion's waiting message is being sent: it takes no more words."""


class WaitingMessageRepository(BaseRepository[WaitingMessage]):
    """One waiting message per discussion, owner-scoped on every read and write."""

    def __init__(self, db: AsyncSession) -> None:
        """Use a caller-owned session that ends before any model or transport work."""
        super().__init__(db, WaitingMessage)

    async def for_discussion(self, owner_id: UUID, conversation_id: UUID) -> WaitingMessage | None:
        """Read the discussion's waiting message, whatever its status.

        Args:
            owner_id: The account reading it.
            conversation_id: The discussion it was written in.

        Returns:
            The row, or None.
        """
        row: WaitingMessage | None = await self.db.scalar(
            select(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.conversation_id == conversation_id,
            )
            .execution_options(populate_existing=True)
        )
        return row

    async def keep(
        self,
        target: ConversationRef,
        text: str,
        *,
        rendering: dict[str, Any] | None,
        status: WaitingStatus,
    ) -> tuple[WaitingMessage, bool]:
        """Keep new words, added after a blank line to what already waits.

        A note that joins the answer being written stays joining: the new words join
        it too, until the loop reads them (ADR-385).

        Args:
            target: The discussion and generation the words were written for.
            text: The person's new words.
            rendering: The browser's display hints, replacing earlier ones when given.
            status: ``WAITING`` or ``HELD``, as the caller decided from the account.

        Returns:
            The row and whether the words were added to an existing one.

        Raises:
            WaitingMessageTooLong: The combined text would exceed one message.
            WaitingMessageDeparting: The waiting message is being sent right now.
        """
        row = await self.db.scalar(
            select(WaitingMessage)
            .where(
                WaitingMessage.user_id == target.owner_id,
                WaitingMessage.conversation_id == target.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            _require_length(text)
            row = WaitingMessage(
                user_id=target.owner_id,
                conversation_id=target.id,
                conversation_revision=target.revision,
                content=text,
                status=status,
                version=1,
                rendering=rendering,
            )
            self.db.add(row)
            await self.db.flush()
            return row, False
        if row.status == WaitingStatus.DEPARTING:
            raise WaitingMessageDeparting()
        combined = f"{row.content}{WAITING_MESSAGE_SEPARATOR}{text}"
        _require_length(combined)
        row.content = combined
        if row.status != WaitingStatus.JOINING:
            row.status = status
        row.version += 1
        if rendering is not None:
            row.rendering = dict(rendering)
        await self.db.flush()
        return row, True

    async def replace_text(
        self, owner_id: UUID, conversation_id: UUID, text: str, *, version: int
    ) -> WaitingMessage | None:
        """Replace the words the person last saw; a departing message is frozen.

        A joining note may still change: the loop reads it only at its next call.

        Args:
            owner_id: The account editing.
            conversation_id: The discussion.
            text: The new words.
            version: The version the person edited.

        Returns:
            The edited row, or None when it left, changed or does not exist.

        Raises:
            WaitingMessageTooLong: The new text exceeds one message.
        """
        _require_length(text)
        edited: WaitingMessage | None = await self.db.scalar(
            update(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.conversation_id == conversation_id,
                WaitingMessage.status.in_(_CHANGEABLE),
                WaitingMessage.version == version,
            )
            .values(content=text, version=WaitingMessage.version + 1)
            .returning(WaitingMessage)
            .execution_options(populate_existing=True)
        )
        return edited

    async def withdraw(self, owner_id: UUID, conversation_id: UUID) -> bool:
        """Remove the waiting message, unless it is already being sent.

        A joining note may still be withdrawn until the loop reads it.

        Args:
            owner_id: The account withdrawing it.
            conversation_id: The discussion.

        Returns:
            Whether a message was withdrawn.
        """
        removed = await self.db.scalar(
            delete(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.conversation_id == conversation_id,
                WaitingMessage.status.in_(_CHANGEABLE),
            )
            .returning(WaitingMessage.id)
        )
        return removed is not None

    async def request_send(self, owner_id: UUID, conversation_id: UUID) -> WaitingMessage | None:
        """Mark the message to leave first at the next release, whatever the end.

        Args:
            owner_id: The account asking.
            conversation_id: The discussion.

        Returns:
            The marked row, or None when there is nothing to send.
        """
        marked: WaitingMessage | None = await self.db.scalar(
            update(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.conversation_id == conversation_id,
                WaitingMessage.status.in_(_PENDING),
            )
            # A repeated click keeps the place the first one took.
            .values(
                send_requested_at=func.coalesce(WaitingMessage.send_requested_at, datetime.now(UTC))
            )
            .returning(WaitingMessage)
            .execution_options(populate_existing=True)
        )
        return marked

    async def claim(self, row_id: UUID, version: int, *, stream_id: str) -> bool:
        """Claim the exact text read for the run that is about to send it.

        Args:
            row_id: The waiting message.
            version: The version whose text the run will send.
            stream_id: The admitted invocation sending it.

        Returns:
            Whether the claim was taken.
        """
        claimed = await self.db.scalar(
            update(WaitingMessage)
            .where(
                WaitingMessage.id == row_id,
                WaitingMessage.version == version,
                WaitingMessage.status.in_(_PENDING),
            )
            .values(status=WaitingStatus.DEPARTING, stream_id=stream_id)
            .returning(WaitingMessage.id)
        )
        return claimed is not None

    async def join(
        self, owner_id: UUID, conversation_id: UUID, *, version: int, stream_id: str
    ) -> WaitingMessage | None:
        """Address the message to the answer being written (ADR-385).

        The caller holds the owner lock and has read that ``stream_id`` runs for this
        discussion and takes notes: a close settles every joining message of its
        stream in the transaction that frees the account.

        Args:
            owner_id: The account.
            conversation_id: The discussion.
            version: The version the person saw.
            stream_id: The running invocation that will read it.

        Returns:
            The joining row, or None when it left, changed or does not exist.
        """
        joined: WaitingMessage | None = await self.db.scalar(
            update(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.conversation_id == conversation_id,
                WaitingMessage.status.in_(_PENDING),
                WaitingMessage.version == version,
            )
            .values(status=WaitingStatus.JOINING, stream_id=stream_id)
            .returning(WaitingMessage)
            .execution_options(populate_existing=True)
        )
        return joined

    async def take_joining(self, owner_id: UUID, stream_id: str) -> list[WaitingMessage]:
        """Delete the notes addressed to this invocation, for its loop to read them.

        Called in the transaction that archives them as the person's messages: a
        note is in the discussion or still joining, never both (ADR-385).

        Args:
            owner_id: The account the invocation belongs to.
            stream_id: The invocation's stream.

        Returns:
            The notes taken, oldest first; empty when none waited.
        """
        taken = await self.db.scalars(
            delete(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.stream_id == stream_id,
                WaitingMessage.status == WaitingStatus.JOINING,
            )
            .returning(WaitingMessage)
        )
        return sorted(taken, key=lambda row: (row.created_at, row.id))

    async def consume(self, owner_id: UUID, stream_id: str) -> UUID | None:
        """Delete the message a run is sending, in the transaction archiving it.

        Args:
            owner_id: The account the run belongs to.
            stream_id: The run's invocation.

        Returns:
            The consumed message's id, or None when this run sends none.
        """
        return await self.db.scalar(
            delete(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.stream_id == stream_id,
                WaitingMessage.status == WaitingStatus.DEPARTING,
            )
            .returning(WaitingMessage.id)
        )

    async def settle_release(self, owner_id: UUID, stream_id: str, end: RunEnd) -> SettledRelease:
        """Settle what waited, in the transaction that closes the run (ADR-384).

        A message the run was sending and did not archive goes back: held after a
        run that started — « send now » was honoured once and is not asked again,
        or a failing run would send it forever — waiting after one that never did.
        A note the run never read waits again (ADR-385). Then an interrupted end
        holds every waiting message the person did not ask to send now.

        Args:
            owner_id: The account the run belonged to.
            stream_id: The closing run's invocation.
            end: How the run ended.

        Returns:
            How many messages this release held, and how many notes it gave back.
        """
        started = end != RunEnd.UNSTARTED
        back = WaitingStatus.HELD if started else WaitingStatus.WAITING
        values: dict[str, object] = {"status": back, "stream_id": None}
        if started:
            values["send_requested_at"] = None
        returned = await self.db.execute(
            update(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.stream_id == stream_id,
                WaitingMessage.status == WaitingStatus.DEPARTING,
            )
            .values(**values)
            .returning(WaitingMessage.id)
        )
        held = len(returned.all()) if back == WaitingStatus.HELD else 0
        unread = await self.db.execute(
            update(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.stream_id == stream_id,
                WaitingMessage.status == WaitingStatus.JOINING,
            )
            .values(status=WaitingStatus.WAITING, stream_id=None)
            .returning(WaitingMessage.id)
        )
        notes_back = len(unread.all())
        if end == RunEnd.INTERRUPTED:
            waited = await self.db.execute(
                update(WaitingMessage)
                .where(
                    WaitingMessage.user_id == owner_id,
                    WaitingMessage.status == WaitingStatus.WAITING,
                    WaitingMessage.send_requested_at.is_(None),
                )
                .values(status=WaitingStatus.HELD)
                .returning(WaitingMessage.id)
            )
            held += len(waited.all())
        return SettledRelease(held=held, returned=notes_back)

    async def departure_candidates(self, owner_id: UUID, end: RunEnd) -> list[WaitingMessage]:
        """What may leave after a release, in the order it leaves.

        Messages the person asked to send now come first, oldest request first;
        after a normal end only, the waiting ones follow, oldest first.

        Args:
            owner_id: The released account.
            end: How the releasing run ended.

        Returns:
            The candidates, in departure order.
        """
        asked = await self.db.scalars(
            select(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.status.in_(_PENDING),
                WaitingMessage.send_requested_at.is_not(None),
            )
            .order_by(WaitingMessage.send_requested_at, WaitingMessage.created_at)
            .execution_options(populate_existing=True)
        )
        candidates = list(asked)
        if end != RunEnd.NORMAL:
            return candidates
        waiting = await self.db.scalars(
            select(WaitingMessage)
            .where(
                WaitingMessage.user_id == owner_id,
                WaitingMessage.status == WaitingStatus.WAITING,
                WaitingMessage.send_requested_at.is_(None),
            )
            .order_by(WaitingMessage.created_at, WaitingMessage.id)
            .execution_options(populate_existing=True)
        )
        return [*candidates, *waiting]


def _require_length(text: str) -> None:
    """Hold the one message bound the composer and the chat route publish."""
    if len(text) > CHAT_MESSAGE_MAX_LENGTH:
        raise WaitingMessageTooLong()
