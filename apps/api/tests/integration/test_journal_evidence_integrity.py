"""Journal evidence belongs to a rule revision and a distinct source event."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.exceptions import ResourceConflictError
from src.domains.conversations.models import Conversation
from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.models import JournalEntry
from src.domains.journals.repository import JournalEntryRepository
from src.domains.journals.service import JournalService
from src.domains.shared.provenance import ProvenanceReference
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
RULE = "WHEN choosing -> DO compare alternatives BECAUSE explicitly requested"


async def seed(factory, committed_user_ids, *, content=RULE):
    async with factory() as db:
        user = User(
            email=f"journal-evidence-{uuid4().hex}@example.test",
            hashed_password="x",
            journals_enabled=True,
        )
        db.add(user)
        await db.flush()
        committed_user_ids.append(user.id)
        note = JournalEntry(
            user_id=user.id,
            theme="learnings",
            title="Choice rule",
            content=content,
            char_count=len(content),
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(note)
        await db.commit()
        return user.id, note.id


@pytest.fixture(autouse=True)
def no_paid_embeddings(monkeypatch):
    monkeypatch.setattr(
        "src.domains.journals.service._generate_dual_embeddings",
        AsyncMock(return_value=(None, None)),
    )


async def test_overlapping_snapshots_preserve_two_distinct_reactions(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as left, factory() as right:
        first = await left.get(JournalEntry, note_id)
        second = await right.get(JournalEntry, note_id)
        await JournalService(left).update_entry(
            first, evidence_outcome="evidence", event_key="turn-a"
        )
        await left.commit()
        await JournalService(right).update_entry(
            second, evidence_outcome="evidence", event_key="turn-b"
        )
        await right.commit()
    async with factory() as db:
        assert (await db.get(JournalEntry, note_id)).evidence_count == 2


async def test_dirty_stale_counter_is_not_flushed_before_atomic_increment(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as left, factory() as right:
        first = await left.get(JournalEntry, note_id)
        second = await right.get(JournalEntry, note_id)
        await JournalService(left).update_entry(
            first, evidence_outcome="evidence", event_key="left"
        )
        await left.commit()
        second.evidence_count = 99
        await JournalService(right).update_entry(
            second, evidence_outcome="evidence", event_key="right"
        )
        await right.commit()
    async with factory() as db:
        assert (await db.get(JournalEntry, note_id)).evidence_count == 2


@pytest.mark.parametrize(
    "keys,expected_count", [(["same-turn", "same-turn"], 1), (["turn-a", "turn-b"], 2)]
)
async def test_simultaneous_sessions_preserve_events_and_deduplicate_replays(
    async_engine, committed_user_ids, keys, expected_count
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    loaded = asyncio.Barrier(2)

    async def react(event_key):
        async with factory() as db:
            note = await db.get(JournalEntry, note_id)
            await loaded.wait()
            await JournalService(db).update_entry(
                note, evidence_outcome="evidence", event_key=event_key
            )
            await db.commit()

    await asyncio.gather(*(react(event_key) for event_key in keys))
    async with factory() as db:
        assert (await db.get(JournalEntry, note_id)).evidence_count == expected_count
        events = (
            (
                await db.execute(
                    select(JournalEvidenceEvent).where(
                        JournalEvidenceEvent.journal_entry_id == note_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {event.event_key for event in events} == set(keys)


async def test_replayed_reaction_counts_once(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        service = JournalService(db)
        await service.update_entry(note, evidence_outcome="evidence", event_key="same-user-message")
        await service.update_entry(note, evidence_outcome="evidence", event_key="same-user-message")
        await db.commit()
        await db.refresh(note)
        assert note.evidence_count == 1


async def test_replacing_the_proposition_retires_its_validation(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        note.evidence_count, note.confidence = 5, "high"
        await db.commit()
        original_revision = getattr(note, "revision", 1)
        await JournalService(db).update_entry(
            note,
            content="WHEN choosing -> DO give only one option",
            evidence_outcome="evidence",
            event_key="old-rule-reaction",
        )
        await db.commit()
        await db.refresh(note)
        assert (note.evidence_count, note.contradiction_count, note.confidence) == (0, 0, "medium")
        assert note.revision == original_revision + 1


async def test_title_edit_keeps_the_current_proposition_validation(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        service = JournalService(db)
        for index in range(5):
            await service.update_entry(
                note, evidence_outcome="evidence", event_key=f"reaction-{index}", confidence="high"
            )
        await db.commit()
        original_revision = getattr(note, "revision", 1)
        await service.update_entry(note, title="Compare before deciding", content=RULE)
        await db.commit()
        await db.refresh(note)
        assert (note.evidence_count, note.confidence, note.revision) == (
            5,
            "high",
            original_revision,
        )


async def test_stale_revision_cannot_validate_or_replace_new_words(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        service = JournalService(db)
        await service.update_entry(note, content="The corrected rule")
        with pytest.raises(ResourceConflictError):
            await service.update_entry(
                note, evidence_outcome="evidence", event_key="stale-turn", expected_revision=1
            )
        assert note.evidence_count == 0


async def test_identical_rule_merge_unions_source_events(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Same rule",
            content=RULE,
            char_count=len(RULE),
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(loser)
        await db.flush()
        service = JournalService(db)
        await service.update_entry(winner, evidence_outcome="evidence", event_key="shared-turn")
        await service.update_entry(loser, evidence_outcome="evidence", event_key="shared-turn")
        await service.update_entry(loser, evidence_outcome="evidence", event_key="another-turn")
        revisions = {str(winner.id): winner.revision, str(loser.id): loser.revision}
        loser_id = loser.id
        await service.merge_entries(winner, [loser.id], revisions)
        await db.commit()
        await db.refresh(winner)
        assert winner.evidence_count == 2
        assert (
            await db.execute(select(JournalEntry).where(JournalEntry.id == loser_id))
        ).scalar_one_or_none() is None


async def test_opposing_rules_cannot_be_merged(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Opposite rule",
            content="WHEN choosing -> DO avoid comparing alternatives",
            char_count=49,
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(loser)
        await db.flush()
        with pytest.raises(ResourceConflictError):
            await JournalService(db).merge_entries(
                winner,
                [loser.id],
                {
                    str(winner.id): getattr(winner, "revision", 1),
                    str(loser.id): getattr(loser, "revision", 1),
                },
            )
        assert (
            await db.execute(select(JournalEntry).where(JournalEntry.id == loser.id))
        ).scalar_one() is loser


async def test_legacy_positive_totals_cannot_recertify_high_confidence(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        note.evidence_count = 20
        await db.commit()
        await JournalService(db).update_entry(note, confidence="high")
        assert (note.evidence_count, note.confidence) == (20, "medium")


@pytest.mark.parametrize(
    "keys,expected_confidence",
    [(["response:answer-1", "response:answer-2"], "medium"), (["turn-1", "turn-2"], "high")],
)
async def test_whole_answer_likes_are_descriptive_not_causal_validation(
    async_engine, committed_user_ids, keys, expected_confidence
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        for event_key in keys:
            await JournalService(db).update_entry(
                note, evidence_outcome="evidence", event_key=event_key, confidence="high"
            )
        assert note.evidence_count == 2
        assert note.confidence == expected_confidence


async def test_evidence_without_a_stable_event_key_is_refused(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        with pytest.raises(ValueError, match="event key"):
            await JournalService(db).update_entry(note, evidence_outcome="evidence")
        assert note.evidence_count == 0
        assert (
            await db.execute(
                select(JournalEvidenceEvent).where(JournalEvidenceEvent.journal_entry_id == note_id)
            )
        ).scalars().all() == []


async def test_merge_keeps_global_likes_without_certifying_them(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Duplicate",
            content=RULE,
            char_count=len(RULE),
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(loser)
        await db.flush()
        service = JournalService(db)
        await service.update_entry(
            winner, evidence_outcome="evidence", event_key="response:answer-1"
        )
        await service.update_entry(
            loser, evidence_outcome="evidence", event_key="response:answer-2"
        )
        winner.confidence = "high"
        await db.flush()
        await service.merge_entries(
            winner, [loser.id], {str(winner.id): winner.revision, str(loser.id): loser.revision}
        )
        assert (winner.evidence_count, winner.confidence) == (2, "medium")


async def test_contradicted_rule_is_readable_but_not_automatically_applied(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        service = JournalService(db)
        for index in range(2):
            await service.update_entry(
                note, evidence_outcome="evidence", event_key=f"positive-{index}", confidence="high"
            )
        assert note.confidence == "high"
        await service.update_entry(note, evidence_outcome="contradiction", event_key="correction")
        assert (note.confidence, note.contradiction_count) == ("low", 1)
        repo = JournalEntryRepository(db)
        assert await repo.get_recent_for_user(user_id, operational_only=True) == []
        assert [entry.id for entry in await repo.get_recent_for_user(user_id)] == [note_id]


async def test_event_and_explanation_keep_owned_source_and_survive_its_deletion(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        conversation = Conversation(user_id=user_id)
        db.add(conversation)
        await db.flush()
        conversation_id = conversation.id
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).update_entry(
            note,
            evidence_outcome="evidence",
            event_key="reaction",
            evidence_source=str(conversation.id),
        )
        event = (
            await db.execute(
                select(JournalEvidenceEvent).where(JournalEvidenceEvent.journal_entry_id == note_id)
            )
        ).scalar_one()
        reference = (
            await db.execute(
                select(ProvenanceReference).where(ProvenanceReference.journal_entry_id == note_id)
            )
        ).scalar_one()
        assert event.source_conversation_id == reference.conversation_id == conversation_id
        await db.delete(conversation)
        await db.flush()
        await db.refresh(event)
        await db.refresh(reference)
        assert event.source_conversation_id is None and reference.conversation_id is None
        assert event.event_key == "reaction"


async def test_foreign_source_is_not_preserved_as_a_persons_evidence(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    foreign_user_id, _ = await seed(factory, committed_user_ids)
    async with factory() as db:
        foreign_conversation = Conversation(user_id=foreign_user_id)
        db.add(foreign_conversation)
        await db.flush()
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).update_entry(
            note,
            evidence_outcome="evidence",
            event_key="source-unavailable",
            evidence_source=str(foreign_conversation.id),
        )
        event = (
            await db.execute(
                select(JournalEvidenceEvent).where(JournalEvidenceEvent.journal_entry_id == note_id)
            )
        ).scalar_one()
        assert event.source_conversation_id is None
        assert (
            await db.execute(
                select(ProvenanceReference).where(ProvenanceReference.journal_entry_id == note_id)
            )
        ).scalars().all() == []


async def test_merge_does_not_erase_retired_proposition_events(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Former rule",
            content="The previous instruction",
            char_count=24,
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(loser)
        await db.flush()
        service = JournalService(db)
        await service.update_entry(loser, evidence_outcome="evidence", event_key="old-proposition")
        await service.update_entry(loser, content=RULE)
        with pytest.raises(ResourceConflictError):
            await service.merge_entries(
                winner, [loser.id], {str(winner.id): winner.revision, str(loser.id): loser.revision}
            )
        assert (
            await db.execute(
                select(JournalEvidenceEvent).where(
                    JournalEvidenceEvent.journal_entry_id == loser.id
                )
            )
        ).scalar_one().event_key == "old-proposition"


async def test_positive_reaction_preserves_portrait_and_advances_its_work_revision(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        user = await db.get(User, user_id)
        user.journal_portrait_full = "The current grounded portrait"
        user.journal_portrait_brief = "Current portrait"
        user.journal_portrait_sources = {"journal_revision": user.journal_revision}
        before = user.journal_revision
        await db.commit()
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).update_entry(
            note, evidence_outcome="evidence", event_key="positive-turn"
        )
        await db.refresh(user)
        assert user.journal_revision == before + 1
        assert user.journal_portrait_sources["journal_revision"] == user.journal_revision
        assert user.journal_portrait_full == "The current grounded portrait"


async def test_contradiction_immediately_retires_the_derived_portrait(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        user = await db.get(User, user_id)
        user.journal_portrait_full, user.journal_portrait_brief = "Old view", "Old"
        user.journal_portrait_sources = {"journal_revision": user.journal_revision}
        await db.commit()
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).update_entry(
            note, evidence_outcome="contradiction", event_key="refutation"
        )
        await db.refresh(user)
        assert user.journal_portrait_full is user.journal_portrait_brief is None
        assert user.journal_portrait_sources is None


async def test_delete_immediately_retires_the_derived_portrait(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        user = await db.get(User, user_id)
        user.journal_portrait_full, user.journal_portrait_brief = "Old view", "Old"
        await db.commit()
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).delete_entry(note, expected_revision=note.revision)
        await db.refresh(user)
        assert user.journal_portrait_full is user.journal_portrait_brief is None


@pytest.mark.parametrize("change", [{"level": "L2"}, {"theme": "user_observations"}])
async def test_changed_abstraction_retires_prior_validation_and_rejects_old_reactions(
    async_engine, committed_user_ids, change
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    _, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await db.get(JournalEntry, note_id)
        service = JournalService(db)
        for index in range(2):
            await service.update_entry(
                note, evidence_outcome="evidence", event_key=f"support-{index}", confidence="high"
            )
        await service.update_entry(
            note, **change, confidence="high", evidence_outcome="evidence", event_key="old-level"
        )
        assert (note.revision, note.confidence, note.evidence_count) == (2, "medium", 0)
        with pytest.raises(ResourceConflictError):
            await service.update_entry(
                note, evidence_outcome="evidence", event_key="delayed", expected_revision=1
            )
        assert (
            len(
                (
                    await db.execute(
                        select(JournalEvidenceEvent).where(
                            JournalEvidenceEvent.journal_entry_id == note_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            == 2
        )


async def test_malformed_legacy_portrait_revision_does_not_break_a_positive_reaction(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, note_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        user = await db.get(User, user_id)
        user.journal_portrait_sources = {"journal_revision": "old-unversioned"}
        await db.commit()
        note = await db.get(JournalEntry, note_id)
        await JournalService(db).update_entry(
            note, evidence_outcome="evidence", event_key="positive-after-upgrade"
        )
        await db.refresh(user)
        assert note.evidence_count == 1
        assert user.journal_portrait_sources == {"journal_revision": "old-unversioned"}


async def test_new_consolidated_abstraction_does_not_start_as_certified_high(
    async_engine, committed_user_ids
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, _ = await seed(factory, committed_user_ids)
    async with factory() as db:
        note = await JournalService(db).create_entry(
            user_id,
            "learnings",
            "Validated synthesis",
            RULE,
            source="consolidation",
            level="L2",
            confidence="high",
        )
        assert (note.confidence, note.evidence_count, note.revision) == ("medium", 0, 1)


@pytest.mark.parametrize("change", [{"level": "L2"}, {"theme": "user_observations"}])
async def test_merge_does_not_transfer_validation_between_abstractions(
    async_engine, committed_user_ids, change
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Same words, another abstraction",
            content=RULE,
            char_count=len(RULE),
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        for key, value in change.items():
            setattr(loser, key, value)
        db.add(loser)
        await db.flush()
        await JournalService(db).update_entry(
            loser, evidence_outcome="evidence", event_key="other-rule"
        )
        with pytest.raises(ResourceConflictError):
            await JournalService(db).merge_entries(
                winner, [loser.id], {str(winner.id): winner.revision, str(loser.id): loser.revision}
            )
        assert await db.get(JournalEntry, loser.id) is not None


@pytest.mark.parametrize("reference_count", [5, 6])
async def test_merge_preserves_all_provenance_or_refuses_an_over_budget_merge(
    async_engine, committed_user_ids, reference_count
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    user_id, winner_id = await seed(factory, committed_user_ids)
    async with factory() as db:
        winner = await db.get(JournalEntry, winner_id)
        loser = JournalEntry(
            user_id=user_id,
            theme="learnings",
            title="Duplicate",
            content=RULE,
            char_count=len(RULE),
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(loser)
        await db.flush()
        references = [
            ProvenanceReference(
                user_id=user_id,
                journal_entry_id=winner.id if index < 2 else loser.id,
                outcome="origin",  # NULL sources are historical tombstones, not absent records.
            )
            for index in range(reference_count)
        ]
        db.add_all(references)
        await db.flush()
        reference_ids = {reference.id for reference in references}
        service = JournalService(db)
        revisions = {str(winner.id): winner.revision, str(loser.id): loser.revision}
        if reference_count == 6:
            with pytest.raises(ResourceConflictError):
                await service.merge_entries(winner, [loser.id], revisions)
            assert await db.get(JournalEntry, loser.id) is not None
        else:
            await service.merge_entries(winner, [loser.id], revisions)
        rows = (
            (
                await db.execute(
                    select(ProvenanceReference).where(ProvenanceReference.id.in_(reference_ids))
                )
            )
            .scalars()
            .all()
        )
        assert {reference.id for reference in rows} == reference_ids
        if reference_count == 5:
            db.expire_all()
            refreshed = (
                (
                    await db.execute(
                        select(ProvenanceReference).where(ProvenanceReference.id.in_(reference_ids))
                    )
                )
                .scalars()
                .all()
            )
            assert {reference.journal_entry_id for reference in refreshed} == {winner_id}
