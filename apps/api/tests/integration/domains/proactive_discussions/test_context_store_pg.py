"""Real SQL: generation CAS, exclusion persistence and forgetting fences."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.proactive_discussions.context_store.observations import apply_observations
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.schemas import (
    ContextCandidate,
    ContextProposal,
)
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey, SourceSnapshot

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


async def test_restoring_a_known_item_reopens_interpretation_without_waiting_for_source_changes(
    async_engine, discussion_owner
):
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        state = await publish(db, discussion_owner, candidate())
        item = state.items[0]
        await repo.set_usable(
            discussion_owner,
            item.id,
            usable=False,
            expected_revision=item.revision,
            expected_epoch=0,
            now=NOW,
        )
        await db.commit()
        await repo.set_usable(
            discussion_owner,
            item.id,
            usable=True,
            expected_revision=item.revision,
            expected_epoch=1,
            now=NOW,
        )
        await db.commit()
        changed = await repo.changed_inputs(
            discussion_owner,
            (snapshot(discussion_owner),),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        assert len(changed) == 1


async def test_changing_cadence_never_relaxes_a_known_sensitive_classification(
    async_engine, discussion_owner
):
    source = snapshot(discussion_owner)
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        annotated = source.items[0].model_copy(update={"sensitive_topics": ("health",)})
        await apply_observations(
            db, discussion_owner, (annotated,), now=NOW, policy_revision=0, directives_revision=None
        )
        await repo.update_policy(
            discussion_owner, DiscussionPolicyPatch(daily_max=3), expected_revision=0
        )
        await db.commit()
        facts = await repo.filter_inputs(
            discussion_owner,
            (source,),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        assert facts == ()


async def test_context_filters_apply_before_exact_total_and_pagination(
    async_engine, discussion_owner
):
    from src.domains.proactive_discussions.context_store.filters import ContextFilters

    async with AsyncSession(async_engine) as db:
        await publish(db, discussion_owner, candidate())
        await db.commit()
        repo = ContextRepository(db)
        assert (
            await repo.read_generation(
                discussion_owner, now=NOW, filters=ContextFilters(source=SourceKey.SMS)
            )
        ).total == 0
        assert (
            await repo.read_generation(
                discussion_owner, now=NOW, filters=ContextFilters(kind="pattern")
            )
        ).total == 0
        assert (
            await repo.read_generation(
                discussion_owner, now=NOW, filters=ContextFilters(query="%_")
            )
        ).total == 0
        assert (
            await repo.read_generation(
                discussion_owner, now=NOW, filters=ContextFilters(usable=False)
            )
        ).total == 1


async def test_the_search_folds_the_needle_as_sql_folds_the_summary(async_engine, discussion_owner):
    # The summary is folded by SQL ``lower()``; the needle must be folded the same
    # way. ``casefold()`` turns « ß » into « ss », which ``lower()`` never does, so
    # a person typing the word as the summary spells it found nothing.
    from src.domains.proactive_discussions.context_store.filters import ContextFilters

    async with AsyncSession(async_engine) as db:
        await publish(db, discussion_owner, candidate(summary="Rendez-vous Hauptstraße"))
        await db.commit()
        repo = ContextRepository(db)
        for needle in ("Hauptstraße", "HAUPTSTRAßE", "straße"):
            assert (
                await repo.read_generation(
                    discussion_owner, now=NOW, filters=ContextFilters(query=needle)
                )
            ).total == 1, needle


async def test_expiration_maintenance_removes_expired_context_even_when_producer_off(
    async_engine, discussion_owner
):
    from sqlalchemy import select, update

    from src.domains.proactive_discussions.context_store.maintenance import expire_context
    from src.domains.proactive_discussions.context_store.models import (
        ContextExclusionRecord,
        ContextItemRecord,
    )

    async with AsyncSession(async_engine) as db:
        await publish(db, discussion_owner, candidate())
        await db.commit()
        row = await db.scalar(
            select(ContextItemRecord).where(ContextItemRecord.user_id == discussion_owner)
        )
        db.add(
            ContextExclusionRecord(user_id=discussion_owner, item_id=row.id, root=row.root_keys[0])
        )
        await db.execute(
            update(ContextItemRecord)
            .where(ContextItemRecord.user_id == discussion_owner)
            .values(expires_at=NOW - timedelta(seconds=1))
        )
        await db.commit()
        assert await expire_context(db, discussion_owner, now=NOW) == 1
        await db.commit()
        assert (
            await db.scalar(
                select(ContextItemRecord.id).where(ContextItemRecord.user_id == discussion_owner)
            )
            is None
        )
        assert (
            await db.scalar(
                select(ContextExclusionRecord.id).where(
                    ContextExclusionRecord.user_id == discussion_owner
                )
            )
            is not None
        )


async def test_retention_is_lifecycle_never_forgetting(async_engine, discussion_owner):
    # Measured 2026-10-21: the location observation lives 15 minutes and the weather
    # 30; each expiry moved the epoch, voided every other checkpoint (each opening run
    # re-interpreted twelve facts), abandoned the run in flight and expired the
    # opening LIA had just written, 4 to 16 minutes after it.
    from sqlalchemy import select, update

    from src.domains.proactive_discussions.context_store.maintenance import expire_context
    from src.domains.proactive_discussions.context_store.models import ContextObservationRecord
    from src.domains.proactive_discussions.context_store.observations import (
        changed_observations,
    )
    from src.domains.proactive_discussions.models import DiscussionPreference

    kept, aged = (
        snapshot(discussion_owner)
        .items[0]
        .model_copy(update={"reference": f"calendar:{name}", "object_id": name})
        for name in ("kept", "aged")
    )
    fences = select(DiscussionPreference.context_epoch, DiscussionPreference.run_fence).where(
        DiscussionPreference.user_id == discussion_owner
    )
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await repo._preference(discussion_owner)
        await apply_observations(
            db,
            discussion_owner,
            (kept, aged),
            now=NOW,
            policy_revision=0,
            directives_revision="directives",
            signature="signature",
        )
        await db.commit()
        before = (await db.execute(fences)).one()
        await db.execute(
            update(ContextObservationRecord)
            .where(
                ContextObservationRecord.user_id == discussion_owner,
                ContextObservationRecord.data["reference"].astext == "calendar:aged",
            )
            .values(expires_at=NOW - timedelta(seconds=1))
        )
        await db.commit()
        generation = (await repo.read_generation(discussion_owner, now=NOW)).generation
        await expire_context(db, discussion_owner, now=NOW)
        await db.commit()
        # The aged observation is gone and the generation says so...
        assert (await repo.read_generation(discussion_owner, now=NOW)).generation == generation + 1
        # ...but no forgetting happened: the epoch and the run fence hold,
        assert (await db.execute(fences)).one() == before
        # and the checkpoint that did not age out is not paid for again.
        assert await changed_observations(
            db,
            discussion_owner,
            (kept, aged),
            now=NOW,
            signature="signature",
            directives_revision="directives",
            context_epoch=before.context_epoch,
        ) == (aged,)


async def test_semantic_topic_cache_restricts_only_the_same_native_version(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    source = snapshot(discussion_owner)
    annotated = source.items[0].model_copy(update={"sensitive_topics": ("health",)})
    async with AsyncSession(async_engine) as db:
        await apply_observations(
            db, discussion_owner, (annotated,), now=NOW, policy_revision=0, directives_revision=None
        )
        await db.commit()
        repo = ContextRepository(db)
        args = {
            "allowed_sources": frozenset({SourceKey.CALENDAR}),
            "allowed_topics": frozenset(),
            "now": NOW,
        }
        assert await repo.filter_inputs(discussion_owner, (source,), **args) == ()
        assert (
            len(
                await repo.filter_inputs(
                    discussion_owner, (snapshot(discussion_owner, version="v2"),), **args
                )
            )
            == 1
        )


async def test_expired_interpretation_is_rebuilt_only_from_fresh_verified_source_data(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    later = NOW + timedelta(days=366)
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await publish(db, discussion_owner, candidate())
        await db.commit()
        source = snapshot(discussion_owner)
        fresh = source.model_copy(
            update={
                "read_at": later,
                "items": (source.items[0].model_copy(update={"observed_at": later}),),
            }
        )
        args = {
            "allowed_sources": frozenset({SourceKey.CALENDAR}),
            "allowed_topics": frozenset(),
            "now": later,
        }
        assert len(await repo.changed_inputs(discussion_owner, (fresh,), **args)) == 1
        await repo.publish_generation(
            discussion_owner, candidate(generation=1), snapshots=(fresh,), **args
        )
        await db.commit()
        assert len((await repo.read_generation(discussion_owner, now=later)).items) == 1


async def test_interpretation_checkpoint_follows_what_its_meaning_depends_on(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await publish(db, discussion_owner, candidate())
        await db.commit()

        async def changed() -> int:
            return len(
                await repo.changed_inputs(
                    discussion_owner,
                    (snapshot(discussion_owner),),
                    allowed_sources=frozenset({SourceKey.CALENDAR}),
                    allowed_topics=frozenset(),
                    now=NOW,
                )
            )

        # The daily limit decides when LIA may speak, never what a fact means:
        # editing it must not have every fact interpreted, and paid for, again.
        await repo.update_policy(
            discussion_owner, DiscussionPolicyPatch(daily_max=3), expected_revision=0
        )
        await db.commit()
        assert await changed() == 0
        # The consented topics change what a fact may be read as.
        await repo.update_policy(
            discussion_owner,
            DiscussionPolicyPatch(sensitive_topics=("health",)),
            expected_revision=1,
        )
        await db.commit()
        assert await changed() == 1


async def test_retrieval_filters_verified_supports_before_paging_and_refreshes_reference_addresses(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    template = snapshot(discussion_owner)
    facts = tuple(
        template.items[0].model_copy(
            update={"object_id": str(index), "reference": f"calendar:{index}"}
        )
        for index in range(60)
    )
    value = ContextCandidate(
        base_generation=0,
        context_epoch=0,
        policy_revision=0,
        proposals=tuple(
            ContextProposal(
                kind="observation",
                summary=f"Fictional appointment {index}",
                qualification="planned",
                anchor=fact.reference,
                references=(fact.reference,),
            )
            for index, fact in enumerate(facts)
        ),
    )
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await repo.publish_generation(
            discussion_owner,
            value,
            snapshots=(template.model_copy(update={"items": facts, "total": 60}),),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        await db.commit()
        all_items = await repo.read_generation(discussion_owner, now=NOW, limit=100)
        last = all_items.items[-1]
        verified = next(
            fact for fact in facts if fact.reference == last.proofs[0].reference
        ).model_copy(update={"reference": "calendar:fresh-address"})
        retrieved = await repo.usable_items(
            discussion_owner,
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            verified_evidence=(verified,),
            now=NOW,
        )
        assert len(retrieved) == 1 and retrieved[0].id == last.id
        assert retrieved[0].proofs[0].reference == "calendar:fresh-address"


def snapshot(
    owner: UUID, *, version: str = "v1", text: str = "Source body stays ephemeral"
) -> SourceSnapshot:
    return SourceSnapshot(
        source=SourceKey.CALENDAR,
        owner_id=owner,
        status="ok",
        read_at=NOW,
        window_start=NOW - timedelta(days=3),
        window_end=NOW + timedelta(days=3),
        complete=True,
        total=1,
        items=(
            DiscussionEvidence(
                source=SourceKey.CALENDAR,
                reference="calendar:one",
                object_id="one",
                version=version,
                observed_at=NOW,
                recorded_at=NOW - timedelta(days=2),
                occurred_at=NOW - timedelta(days=1),
                excerpt=text,
                assertion="planned",
            ),
        ),
    )


def candidate(
    *, generation: int = 0, epoch: int = 0, summary: str = "A planned appointment"
) -> ContextCandidate:
    return ContextCandidate(
        base_generation=generation,
        context_epoch=epoch,
        policy_revision=0,
        proposals=(
            ContextProposal(
                kind="observation",
                summary=summary,
                qualification="planned",
                anchor="calendar:one",
                references=("calendar:one",),
            ),
        ),
    )


async def publish(db: AsyncSession, owner: UUID, value: ContextCandidate, *, version: str = "v1"):
    published = await ContextRepository(db).publish_generation(
        owner,
        value,
        snapshots=(snapshot(owner, version=version),),
        allowed_sources=frozenset({SourceKey.CALENDAR}),
        allowed_topics=frozenset(),
        now=NOW,
    )
    return published.generation


async def test_idempotent_semantics_does_not_keep_source_body_or_change_item_identity(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        first = await publish(db, discussion_owner, candidate())
        await db.commit()
        same = await publish(db, discussion_owner, candidate(generation=first.generation))
        await db.commit()
        assert same.generation == first.generation
        assert len(same.items) == 1
        assert same.items[0].id == first.items[0].id
        assert "Source body" not in same.model_dump_json()
        changed = await publish(
            db,
            discussion_owner,
            candidate(generation=first.generation, summary="Rephrased summary"),
            version="v2",
        )
        assert changed.items[0].id == first.items[0].id
        assert changed.items[0].revision == first.items[0].revision + 1


async def test_a_pass_publication_leaves_the_rebuild_request_to_the_rebuilds_end(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    # Each pass of a covering rebuild publishes; clearing the request there meant a
    # rebuild cut short after its first pass was never served again.
    async with AsyncSession(async_engine) as db:
        requested = await ContextRepository(db).request_rebuild(
            discussion_owner, expected_epoch=0, now=NOW
        )
        await db.commit()
        published = await ContextRepository(db).publish_generation(
            discussion_owner,
            candidate(epoch=requested.context_epoch),
            snapshots=(snapshot(discussion_owner),),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        await db.commit()
    assert published.generation.refresh_requested


async def test_a_proposal_its_evidence_cannot_carry_is_refused_alone(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    # Before 2026-10-21 one over-qualified proposal refused the whole generation, and
    # with it every other understanding of the pass.
    supported = candidate().proposals[0]
    value = candidate().model_copy(
        update={
            "proposals": (
                supported,
                # A plan is not testimony: its evidence cannot carry "observed".
                supported.model_copy(update={"kind": "episode", "qualification": "observed"}),
                supported.model_copy(update={"summary": "A second reading of the anchor"}),
                supported.model_copy(update={"kind": "episode", "sensitive_topics": ("health",)}),
            )
        }
    )
    async with AsyncSession(async_engine) as db:
        published = await ContextRepository(db).publish_generation(
            discussion_owner,
            value,
            snapshots=(snapshot(discussion_owner),),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        await db.commit()
    assert published.refused == {
        "unsupported_qualification": 1,
        "duplicate_item": 1,
        "refused_topic": 1,
    }
    assert [item.summary for item in published.generation.items] == [supported.summary]
    assert published.generation.generation == 1


async def test_exclusion_precedes_inputs_and_survives_purge_and_rebuild(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        first = await publish(db, discussion_owner, candidate())
        item = first.items[0]
        await repo.set_usable(
            discussion_owner, item.id, usable=False, expected_revision=item.revision, now=NOW
        )
        await db.commit()
        assert (
            await repo.filter_inputs(
                discussion_owner,
                (snapshot(discussion_owner, version="v2"),),
                allowed_sources=frozenset({SourceKey.CALENDAR}),
                allowed_topics=frozenset(),
                now=NOW,
            )
            == ()
        )
        state = await repo.purge(discussion_owner, selection=None, expected_epoch=1, now=NOW)
        await db.commit()
        assert state.context_epoch == 2 and state.items == ()
        assert len(state.exclusions) == 1
        await repo.request_rebuild(discussion_owner, expected_epoch=2, now=NOW)
        await db.commit()
        assert (
            await repo.filter_inputs(
                discussion_owner,
                (snapshot(discussion_owner),),
                allowed_sources=frozenset({SourceKey.CALENDAR}),
                allowed_topics=frozenset(),
                now=NOW,
            )
            == ()
        )
        await repo.set_usable(
            discussion_owner, item.id, usable=True, expected_revision=None, now=NOW
        )
        await db.commit()
        assert (
            len(
                await repo.filter_inputs(
                    discussion_owner,
                    (snapshot(discussion_owner),),
                    allowed_sources=frozenset({SourceKey.CALENDAR}),
                    allowed_topics=frozenset(),
                    now=NOW,
                )
            )
            == 1
        )


async def test_stale_generation_epoch_and_foreign_owner_cannot_publish_or_edit(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        first = await publish(db, discussion_owner, candidate())
        await db.commit()
        with pytest.raises(ResourceConflictError):
            await publish(db, discussion_owner, candidate())
        await db.rollback()
        with pytest.raises(ResourceNotFoundError):
            await ContextRepository(db).set_usable(
                uuid4(), first.items[0].id, usable=False, expected_revision=1, now=NOW
            )
        await db.rollback()
        await ContextRepository(db).purge(
            discussion_owner, selection=None, expected_epoch=0, now=NOW
        )
        await db.commit()
        with pytest.raises(ResourceConflictError):
            await publish(db, discussion_owner, candidate(generation=first.generation))


async def test_purged_unchanged_history_stays_forgotten_until_explicit_rebuild(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await publish(db, discussion_owner, candidate())
        await db.commit()
        await repo.purge(discussion_owner, selection=None, expected_epoch=0, now=NOW)
        await db.commit()
        args = {
            "allowed_sources": frozenset({SourceKey.CALENDAR}),
            "allowed_topics": frozenset(),
            "now": NOW,
        }

        assert (
            await repo.filter_inputs(discussion_owner, (snapshot(discussion_owner),), **args) == ()
        )
        await repo.request_rebuild(discussion_owner, expected_epoch=1, now=NOW)
        await db.commit()
        assert (
            len(await repo.filter_inputs(discussion_owner, (snapshot(discussion_owner),), **args))
            == 1
        )


async def test_known_support_reference_blocks_a_whole_portrait_before_interpretation(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        first = await publish(db, discussion_owner, candidate())
        await repo.set_usable(
            discussion_owner,
            first.items[0].id,
            usable=False,
            expected_revision=first.items[0].revision,
            now=NOW,
        )
        await db.commit()
        native = snapshot(discussion_owner)
        portrait = native.model_copy(
            update={
                "source": SourceKey.PORTRAIT,
                "items": (
                    native.items[0].model_copy(
                        update={
                            "source": SourceKey.PORTRAIT,
                            "object_id": "whole",
                            "reference": "portrait:whole",
                            "derived": True,
                            "supports": ("calendar:one",),
                        }
                    ),
                ),
            }
        )
        assert (
            await repo.filter_inputs(
                discussion_owner,
                (portrait,),
                allowed_sources=frozenset({SourceKey.PORTRAIT}),
                allowed_topics=frozenset(),
                now=NOW,
            )
            == ()
        )


async def test_two_workers_publish_one_generation_and_rollback_keeps_previous(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async def worker() -> bool:
        async with AsyncSession(async_engine) as db:
            try:
                await publish(db, discussion_owner, candidate())
                await db.commit()
                return True
            except ResourceConflictError:
                await db.rollback()
                return False

    assert sorted(await asyncio.gather(worker(), worker())) == [False, True]
    async with AsyncSession(async_engine) as db:
        prior = await ContextRepository(db).read_generation(discussion_owner, now=NOW)
        await publish(
            db, discussion_owner, candidate(generation=1, summary="Uncommitted"), version="v2"
        )
        await db.rollback()
        after = await ContextRepository(db).read_generation(discussion_owner, now=NOW)
        assert after == prior


async def test_source_versions_are_required_before_retrieval(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await publish(db, discussion_owner, candidate())
        await db.commit()
        args = {
            "allowed_sources": frozenset({SourceKey.CALENDAR}),
            "allowed_topics": frozenset(),
            "now": NOW,
        }
        assert (
            len(
                await repo.usable_items(
                    discussion_owner, verified_evidence=snapshot(discussion_owner).items, **args
                )
            )
            == 1
        )
        assert (
            await repo.usable_items(
                discussion_owner,
                verified_evidence=snapshot(discussion_owner, version="v2").items,
                **args,
            )
            == ()
        )
        assert await repo.usable_items(discussion_owner, verified_evidence=(), **args) == ()


async def test_unselected_but_analyzed_evidence_is_not_reanalyzed_unchanged(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        args = {
            "allowed_sources": frozenset({SourceKey.CALENDAR}),
            "allowed_topics": frozenset(),
            "now": NOW,
        }
        assert (
            len(await repo.changed_inputs(discussion_owner, (snapshot(discussion_owner),), **args))
            == 1
        )
        await repo.publish_generation(
            discussion_owner,
            ContextCandidate(base_generation=0, context_epoch=0, policy_revision=0, proposals=()),
            snapshots=(snapshot(discussion_owner),),
            **args,
        )
        await db.commit()
        assert (
            await repo.changed_inputs(discussion_owner, (snapshot(discussion_owner),), **args) == ()
        )
        assert (
            len(
                await repo.changed_inputs(
                    discussion_owner, (snapshot(discussion_owner, version="v2"),), **args
                )
            )
            == 1
        )


async def test_retained_exclusions_are_paged_after_purge(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        source = snapshot(discussion_owner)
        sources = source.model_copy(
            update={
                "items": tuple(
                    source.items[0].model_copy(
                        update={"object_id": str(index), "reference": f"calendar:{index}"}
                    )
                    for index in range(3)
                ),
                "total": 3,
            }
        )
        batch = ContextCandidate(
            base_generation=0,
            context_epoch=0,
            policy_revision=0,
            proposals=tuple(
                ContextProposal(
                    kind="observation",
                    summary=f"Plan {index}",
                    qualification="planned",
                    anchor=f"calendar:{index}",
                    references=(f"calendar:{index}",),
                )
                for index in range(3)
            ),
        )
        published = await repo.publish_generation(
            discussion_owner,
            batch,
            snapshots=(sources,),
            allowed_sources=frozenset({SourceKey.CALENDAR}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        generation = published.generation
        assert not published.refused
        for item in generation.items:
            await repo.set_usable(
                discussion_owner, item.id, usable=False, expected_revision=item.revision, now=NOW
            )
        await repo.purge(discussion_owner, selection=None, expected_epoch=3, now=NOW)
        await db.commit()
        first = await repo.read_generation(discussion_owner, now=NOW, limit=1)
        assert len(first.exclusions) == 1 and first.exclusions_total == 3
        assert first.exclusions_next_cursor is not None
        second = await repo.read_generation(
            discussion_owner, now=NOW, limit=1, after_exclusion_id=first.exclusions_next_cursor
        )
        assert second.exclusions[0].item_id != first.exclusions[0].item_id


async def test_partial_purge_removes_known_descendants_and_preserves_other_objects(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        native = snapshot(discussion_owner)
        derived = native.model_copy(
            update={
                "source": SourceKey.MEMORIES,
                "items": (
                    native.items[0].model_copy(
                        update={
                            "source": SourceKey.MEMORIES,
                            "reference": "memory:one",
                            "object_id": "derived",
                            "derived": True,
                            "supports": ("calendar:one",),
                        }
                    ),
                ),
            }
        )
        independent = native.items[0].model_copy(
            update={"reference": "calendar:other", "object_id": "other"}
        )
        native = native.model_copy(update={"items": (*native.items, independent), "total": 2})
        proposal = ContextCandidate(
            policy_revision=0,
            context_epoch=0,
            base_generation=0,
            proposals=(
                *candidate().proposals,
                ContextProposal(
                    kind="observation",
                    summary="Derived fact",
                    qualification="possible",
                    anchor="memory:one",
                    references=("memory:one",),
                ),
                ContextProposal(
                    kind="observation",
                    summary="Independent plan",
                    qualification="planned",
                    anchor="calendar:other",
                    references=("calendar:other",),
                ),
            ),
        )
        published = await repo.publish_generation(
            discussion_owner,
            proposal,
            snapshots=(native, derived),
            allowed_sources=frozenset({SourceKey.CALENDAR, SourceKey.MEMORIES}),
            allowed_topics=frozenset(),
            now=NOW,
        )
        first = published.generation
        await db.commit()
        selected = next(
            item.id for item in first.items if item.proofs[0].reference == "calendar:one"
        )
        preview = await repo.preview_purge(
            discussion_owner,
            selection=(selected,),
            expected_epoch=0,
            expected_generation=first.generation,
            now=NOW,
        )
        assert preview.selected_count == 1 and preview.affected_count == 2
        purged = await repo.purge(
            discussion_owner, selection=(selected,), expected_epoch=0, now=NOW
        )
        await db.commit()
        assert [item.summary for item in purged.items] == ["Independent plan"]


async def test_large_purge_keeps_all_forgetting_markers_without_one_insert_per_record(
    async_engine, discussion_owner
):
    from sqlalchemy import event, func, select

    from src.domains.proactive_discussions.context_store.admission import observation_key
    from src.domains.proactive_discussions.context_store.models import (
        ContextObservationRecord,
        ContextResumeRecord,
    )
    from src.domains.proactive_discussions.context_store.preparation import proof_of

    statements = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO DISCUSSION_CONTEXT_RESUME_MARKERS"):
            statements.append(statement)

    async with AsyncSession(async_engine) as db:
        repo = ContextRepository(db)
        await publish(db, discussion_owner, candidate())
        base = snapshot(discussion_owner).items[0]
        for index in range(300):
            fact = base.model_copy(
                update={"reference": f"calendar:bulk-{index}", "object_id": f"bulk-{index}"}
            )
            proof = proof_of(fact, {}, now=NOW)
            db.add(
                ContextObservationRecord(
                    user_id=discussion_owner,
                    root=observation_key(fact),
                    source=fact.source.value,
                    version=fact.version,
                    data=proof.model_dump(mode="json"),
                    expires_at=proof.expires_at,
                )
            )
        await db.commit()
        event.listen(async_engine.sync_engine, "before_cursor_execute", observe)
        try:
            result = await repo.purge(discussion_owner, selection=None, expected_epoch=0, now=NOW)
            await db.commit()
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", observe)
        assert result.total == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ContextResumeRecord)
                .where(ContextResumeRecord.user_id == discussion_owner)
            )
            == 602
        )
        assert len(statements) <= 8
