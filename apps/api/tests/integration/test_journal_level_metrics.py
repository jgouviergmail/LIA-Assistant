"""Persisted level transitions and reaction metrics on disposable PostgreSQL.

The old mock-only tests could not prove SQL arithmetic or replay handling.
These cases assert committed values and the real Prometheus counter deltas.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.infrastructure.observability.metrics_journals import (
    journal_consolidation_promotions_total,
    journal_evidence_total,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def counter_value(counter, **labels):
    return sum(
        sample.value
        for metric in counter.collect()
        for sample in metric.samples
        if sample.name.endswith("_total") and sample.labels == labels
    )


@pytest.fixture
async def journal_case(async_engine, committed_user_ids):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        user = User(email=f"journal-metrics-{uuid4().hex}@example.test", hashed_password="x")
        db.add(user)
        await db.flush()
        committed_user_ids.append(user.id)
        entry = JournalEntry(
            user_id=user.id,
            theme="learnings",
            title="Test rule",
            content="WHEN choosing -> compare",
            char_count=24,
            source="conversation",
            status="active",
            level="L1",
            confidence="medium",
            evidence_count=0,
            contradiction_count=0,
        )
        db.add(entry)
        await db.commit()
        return factory, entry.id


@pytest.mark.parametrize("before,after,delta", [("L1", "L2", 1), ("L1", "L1", 0), ("L2", "L1", 1)])
async def test_level_transition_commits_and_emits_once(journal_case, before, after, delta):
    factory, entry_id = journal_case
    labels = {"from_level": before, "to_level": after}
    metric_before = counter_value(journal_consolidation_promotions_total, **labels)
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        entry.level = before
        await db.commit()
        await JournalService(db).update_entry(
            entry, level=after, precomputed_embeddings=(None, None)
        )
        await db.commit()
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        assert entry.level == after
        assert entry.revision == (2 if before != after else 1)
    assert counter_value(journal_consolidation_promotions_total, **labels) == metric_before + delta


@pytest.mark.parametrize(
    "outcome,start_evidence,start_contradiction,end_evidence,end_contradiction",
    [
        ("evidence", 3, 1, 4, 1),
        ("contradiction", 2, 0, 2, 1),
        ("garbage", 5, 2, 5, 2),
        (None, 7, 3, 7, 3),
    ],
)
async def test_outcome_owns_persisted_arithmetic_and_metric(
    journal_case, outcome, start_evidence, start_contradiction, end_evidence, end_contradiction
):
    factory, entry_id = journal_case
    metric_before = counter_value(journal_evidence_total, outcome=outcome)
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        entry.evidence_count, entry.contradiction_count = start_evidence, start_contradiction
        await db.commit()
        await JournalService(db).update_entry(
            entry,
            evidence_outcome=outcome,
            event_key="one-reaction",
            confidence="high",
            precomputed_embeddings=(None, None),
        )
        await db.commit()
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        assert (entry.evidence_count, entry.contradiction_count) == (
            end_evidence,
            end_contradiction,
        )
        assert entry.confidence == "low"  # Every fixture contains a contradiction after the write.
    assert counter_value(journal_evidence_total, outcome=outcome) == metric_before + (
        1 if outcome in ("evidence", "contradiction") else 0
    )


@pytest.mark.parametrize("current_events", [0, 1])
async def test_high_requires_two_current_events_instead_of_one_or_legacy_totals(
    journal_case, current_events
):
    factory, entry_id = journal_case
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        entry.confidence, entry.evidence_count = "low", 10
        await db.commit()
        service = JournalService(db)
        for index in range(current_events):
            await service.update_entry(
                entry, evidence_outcome="evidence", event_key=f"event-{index}"
            )
        await service.update_entry(entry, confidence="high")
        await db.commit()
    async with factory() as db:
        assert (await db.get(JournalEntry, entry_id)).confidence == "medium"


async def test_duplicate_reaction_emits_metric_once(journal_case):
    factory, entry_id = journal_case
    before = counter_value(journal_evidence_total, outcome="evidence")
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        service = JournalService(db)
        for _ in range(2):
            await service.update_entry(
                entry, evidence_outcome="evidence", event_key="replayed-message"
            )
        await db.commit()
    async with factory() as db:
        assert (await db.get(JournalEntry, entry_id)).evidence_count == 1
    assert counter_value(journal_evidence_total, outcome="evidence") == before + 1


async def test_promotion_does_not_apply_the_previous_levels_reaction(journal_case):
    factory, entry_id = journal_case
    promotions = counter_value(
        journal_consolidation_promotions_total, from_level="L1", to_level="L2"
    )
    evidence = counter_value(journal_evidence_total, outcome="evidence")
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        entry.evidence_count = 4
        await db.commit()
        await JournalService(db).update_entry(
            entry,
            level="L2",
            confidence="high",
            evidence_outcome="evidence",
            event_key="old-L1-reaction",
        )
        await db.commit()
    async with factory() as db:
        entry = await db.get(JournalEntry, entry_id)
        assert (entry.level, entry.revision, entry.confidence, entry.evidence_count) == (
            "L2",
            2,
            "medium",
            0,
        )
    assert (
        counter_value(journal_consolidation_promotions_total, from_level="L1", to_level="L2")
        == promotions + 1
    )
    assert counter_value(journal_evidence_total, outcome="evidence") == evidence
