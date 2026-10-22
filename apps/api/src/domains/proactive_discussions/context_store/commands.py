"""Explicit user controls fence all earlier work and preserve exclusions through purge."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.proactive_discussions.context_store.admission import reference_key
from src.domains.proactive_discussions.context_store.models import (
    ContextExclusionRecord,
    ContextItemRecord,
    ContextObservationRecord,
    ContextResumeRecord,
    ContextSupportRecord,
)
from src.domains.proactive_discussions.context_store.purge import purge_all_data
from src.domains.proactive_discussions.context_store.reads import ContextReader
from src.domains.proactive_discussions.context_store.schemas import (
    ContextGeneration,
    ContextItem,
    ContextPurgePreview,
)
from src.domains.proactive_discussions.models import (
    DiscussionOpeningRecord,
    DiscussionOutbox,
    DiscussionPreference,
)


def _check_item_revision(
    row: ContextItemRecord | None,
    expected: int | None,
    *,
    restoring: bool,
    epoch: int | None,
) -> None:
    if row is None:
        return
    marker_restore = restoring and expected is None and epoch is not None
    if expected != row.revision and not marker_restore:
        raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})


class ContextCommands(ContextReader):
    """The person's explicit context controls; each one fences off every earlier run."""

    async def preview_purge(
        self,
        owner_id: UUID,
        *,
        selection: tuple[UUID, ...] | None,
        expected_epoch: int,
        expected_generation: int,
        now: datetime,
    ) -> ContextPurgePreview:
        """Count what a purge would remove, against the context the person read.

        Args:
            owner_id: The account.
            selection: The items to purge, or None for the whole context.
            expected_epoch: The context epoch read.
            expected_generation: The generation read.
            now: The current instant.

        Returns:
            The selected and affected counts, dependants included.

        Raises:
            ResourceConflictError: The context changed since it was read.
            ResourceNotFoundError: A selected item is not the account's.
            ValueError: The selection is empty, too large or names an item twice.
        """
        await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        state = await self._state(owner_id, lock=True)
        if preference.context_epoch != expected_epoch or state.generation != expected_generation:
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        query = (
            select(func.count())
            .select_from(ContextItemRecord)
            .where(ContextItemRecord.user_id == owner_id)
        )
        if selection is None:
            count = await self.db.scalar(query) or 0
            selected = count
        else:
            if not 1 <= len(selection) <= 100 or len(set(selection)) != len(selection):
                raise ValueError("invalid purge selection")
            roots = await self._purge_roots(owner_id, selection)
            keys = tuple(
                key
                for row in roots
                for key in (row.root, reference_key(str(row.data["reference"])))
            )
            count = (
                await self.db.scalar(query.where(ContextItemRecord.root_keys.overlap(list(keys))))
                or 0
            )
            selected = len(selection)
        return ContextPurgePreview(
            context_epoch=preference.context_epoch,
            generation=state.generation,
            selected_count=selected,
            affected_count=count,
        )

    async def _invalidate_context(self, preference: DiscussionPreference, now: datetime) -> None:
        await self._invalidate_claim(preference)
        preference.context_epoch += 1
        await self.db.execute(
            update(DiscussionOpeningRecord)
            .where(
                DiscussionOpeningRecord.user_id == preference.user_id,
                DiscussionOpeningRecord.state == "pending",
            )
            .values(state="expired", expires_at=now)
        )
        await self.db.execute(
            update(DiscussionOutbox)
            .where(
                DiscussionOutbox.user_id == preference.user_id,
                DiscussionOutbox.state.in_(("pending", "dispatching")),
            )
            .values(
                state=case(
                    (DiscussionOutbox.state == "dispatching", "uncertain"), else_="cancelled"
                )
            )
        )

    async def set_usable(
        self,
        owner_id: UUID,
        item_id: UUID,
        *,
        usable: bool,
        expected_revision: int | None,
        now: datetime,
        expected_epoch: int | None = None,
    ) -> ContextGeneration:
        """Exclude one item and its roots from use, or allow it again.

        An exclusion survives purges and rebuilds and covers what derives from the
        same roots; allowing a purged item again lifts the choice without recreating
        its content. Either way the context epoch moves, so nothing decided before
        the change is published.

        Args:
            owner_id: The account.
            item_id: The item.
            usable: Allow it (True) or exclude it (False).
            expected_revision: The item's revision read; required to exclude it.
            now: The current instant.
            expected_epoch: The context epoch read.

        Returns:
            The context generation after the change.

        Raises:
            ResourceConflictError: The item or the context changed since it was read.
            ResourceNotFoundError: The item is unknown, or carries no choice to lift.
        """
        await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        if expected_epoch is not None and expected_epoch != preference.context_epoch:
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        row = await self.db.scalar(
            select(ContextItemRecord)
            .where(
                ContextItemRecord.user_id == owner_id,
                ContextItemRecord.id == item_id,
            )
            .with_for_update()
        )
        _check_item_revision(row, expected_revision, restoring=usable, epoch=expected_epoch)
        if usable:
            # A purged item's content no longer exists, but its choice remains reversible.
            result = await self.db.execute(
                delete(ContextExclusionRecord)
                .where(
                    ContextExclusionRecord.user_id == owner_id,
                    ContextExclusionRecord.item_id == item_id,
                )
                .returning(ContextExclusionRecord.id)
            )
            if row is None and result.first() is None:
                raise ResourceNotFoundError("discussion_context")
        else:
            if row is None:
                raise ResourceNotFoundError("discussion_context")
            item = ContextItem.model_validate(row.data)
            roots = {
                root
                for proof in item.proofs
                for root in (proof.root, reference_key(proof.reference), *proof.support_roots)
            }
            for root in sorted(roots):
                await self.db.execute(
                    insert(ContextExclusionRecord)
                    .values(
                        user_id=owner_id,
                        item_id=item_id,
                        root=root,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            ContextExclusionRecord.user_id,
                            ContextExclusionRecord.item_id,
                            ContextExclusionRecord.root,
                        ]
                    )
                )
        await self._invalidate_context(preference, now)
        await self.db.flush()
        return await self.read_generation(owner_id, now=now)

    async def purge(
        self,
        owner_id: UUID,
        *,
        selection: tuple[UUID, ...] | None,
        expected_epoch: int,
        now: datetime,
        expected_generation: int | None = None,
    ) -> ContextGeneration:
        """Purge the whole context or selected items, keeping the person's non-use choices.

        Forgotten facts leave markers at their version so an unchanged source does not
        bring them back; the generation and the epoch move and a pending rebuild
        request is dropped.

        Args:
            owner_id: The account.
            selection: The items to purge, or None for the whole context.
            expected_epoch: The context epoch read.
            now: The current instant.
            expected_generation: The generation read, when the caller has it.

        Returns:
            The context generation after the purge.

        Raises:
            ResourceConflictError: The context changed since it was read.
            ResourceNotFoundError: A selected item is not the account's.
            ValueError: The selection is empty.
        """
        await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        if expected_epoch != preference.context_epoch:
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        state = await self._state(owner_id, lock=True)
        if expected_generation is not None and state.generation != expected_generation:
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        if selection is None:
            await purge_all_data(self.db, owner_id)
            roots = []
        else:
            roots = await self._purge_roots(owner_id, selection)
        for observation in roots:
            for marker in (observation.root, reference_key(str(observation.data["reference"]))):
                await self.db.execute(
                    insert(ContextResumeRecord)
                    .values(
                        user_id=owner_id,
                        root=marker,
                        version=observation.version,
                    )
                    .on_conflict_do_update(
                        index_elements=[ContextResumeRecord.user_id, ContextResumeRecord.root],
                        set_={"version": observation.version},
                    )
                )
        root_keys = tuple(
            key
            for observation in roots
            for key in (observation.root, reference_key(str(observation.data["reference"])))
        )
        await self._delete_derived(owner_id, root_keys)
        await self.db.execute(
            delete(ContextObservationRecord).where(
                ContextObservationRecord.user_id == owner_id,
                ContextObservationRecord.root.in_(root_keys),
            )
        )
        if selection is None:
            state.forgotten_at, state.coverage = now, []
        state.generation += 1
        state.refresh_requested = False
        await self._invalidate_context(preference, now)
        await self.db.flush()
        return await self.read_generation(owner_id, now=now)

    async def _purge_roots(
        self, owner_id: UUID, selection: tuple[UUID, ...] | None
    ) -> list[ContextObservationRecord]:
        query = select(ContextObservationRecord).where(ContextObservationRecord.user_id == owner_id)
        if selection is not None:
            if not selection:
                raise ValueError("empty purge selection")
            owned = (
                await self.db.scalars(
                    select(ContextItemRecord.id).where(
                        ContextItemRecord.user_id == owner_id, ContextItemRecord.id.in_(selection)
                    )
                )
            ).all()
            if set(owned) != set(selection):
                raise ResourceNotFoundError("discussion_context")
            supported = select(ContextSupportRecord.root).where(
                ContextSupportRecord.user_id == owner_id,
                ContextSupportRecord.item_id.in_(selection),
            )
            query = query.where(ContextObservationRecord.root.in_(supported))
        return list((await self.db.scalars(query)).all())

    async def _delete_derived(self, owner_id: UUID, roots: tuple[str, ...]) -> None:
        await self.db.execute(
            delete(ContextItemRecord).where(
                ContextItemRecord.user_id == owner_id,
                ContextItemRecord.root_keys.overlap(list(roots)),
            )
        )

    async def request_rebuild(
        self, owner_id: UUID, *, expected_epoch: int, now: datetime
    ) -> ContextGeneration:
        """Ask for a rebuild from the sources currently permitted.

        It lifts the forgetting markers, so what a purge forgot may be read again, and
        moves the epoch. Asking again while a rebuild is pending changes nothing: a new
        epoch would fence off the rebuild in flight, paid for nothing.

        Args:
            owner_id: The account.
            expected_epoch: The context epoch read.
            now: The current instant.

        Returns:
            The context generation, with the rebuild requested.

        Raises:
            ResourceConflictError: The context changed since it was read.
        """
        await self._owner(owner_id)
        preference = await self._preference(owner_id, lock=True)
        if expected_epoch != preference.context_epoch:
            raise ResourceConflictError("discussion_context", detail={"error_code": "STALE_STATE"})
        state = await self._state(owner_id, lock=True)
        if state.refresh_requested:
            # Already asked: a new epoch would fence off the rebuild in flight, paid for nothing.
            return await self.read_generation(owner_id, now=now)
        await self.db.execute(
            delete(ContextResumeRecord).where(ContextResumeRecord.user_id == owner_id)
        )
        state.forgotten_at, state.refresh_requested = None, True
        await self._invalidate_context(preference, now)
        await self.db.flush()
        return await self.read_generation(owner_id, now=now)
