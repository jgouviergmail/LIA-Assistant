"""Real PostgreSQL acceptance for snapshot, rollback and portrait lineage."""

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import delete, select

from src.domains.journals import consolidation_lifecycle as lifecycle
from src.domains.journals import consolidation_service as consolidation
from src.domains.journals import consolidation_settlement as settlement
from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_sources import PortraitSourceBundle
from src.domains.journals.repository import build_consolidation_eligible_users_query
from src.domains.journals.service import JournalService
from src.domains.journals.source_state import portrait_source_state
from src.domains.memories.models import Memory
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def isolated_runtime(async_session, monkeypatch):
    @asynccontextmanager
    async def db_context():
        yield async_session

    monkeypatch.setattr(lifecycle, "get_db_context", db_context)
    monkeypatch.setattr(settlement, "get_db_context", db_context)
    monkeypatch.setattr("src.infrastructure.database.get_db_context", db_context)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", db_context)
    monkeypatch.setattr(portrait_sources, "_REGISTRY", {})
    monkeypatch.setattr(lifecycle, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(
        consolidation, "get_llm", lambda *_: SimpleNamespace(model_name="synthetic-offline")
    )
    monkeypatch.setattr(
        consolidation,
        "get_llm_config_for_agent",
        lambda *_: SimpleNamespace(model="synthetic-offline"),
    )
    monkeypatch.setattr(
        "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
        AsyncMock(return_value=False),
    )
    for name in ("_persist_journal_tokens", "_update_user_last_cost", "_file_consolidation"):
        monkeypatch.setattr(consolidation, name, AsyncMock())
    for name in ("_build_usage_patterns_section", "_maybe_build_health_signals_section"):
        monkeypatch.setattr(consolidation, name, AsyncMock(return_value=""))
    monkeypatch.setattr(
        consolidation,
        "build_portrait_source_sections",
        AsyncMock(
            return_value=PortraitSourceBundle(
                sections=dict.fromkeys(portrait_sources.PORTRAIT_SOURCE_KEYS, ""),
                provenance={"version": 1, "journal_entries": 1, "sources": {}},
            )
        ),
    )
    monkeypatch.setattr(
        "src.domains.journals.maintenance_actions.prepare_embeddings",
        AsyncMock(return_value=(None, None)),
    )
    return async_session


async def _user(db):
    user = User(
        email=f"journal-safe-{uuid4()}@example.test",
        hashed_password="x",
        journals_enabled=True,
        journal_consolidation_enabled=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    return user


async def _entry(db, user, content="WHEN urgent -> DO give one step BECAUSE action was requested."):
    result = await JournalService(db).create_entry(
        user.id, "learnings", "Rule", content, precomputed_embeddings=(None, None)
    )
    await db.commit()
    await db.refresh(user)
    return result


def _claim(
    entry,
    text="Quand il demande explicitement une aide urgente, il attend une prochaine action concrète.",
):
    return {
        "facet": "interaction",
        "text": text,
        "supports": [{"source": f"journal:{entry.id}", "quote": entry.content}],
        "placement": "full",
    }


def _answer(monkeypatch, payload, *, on_generation=None):
    """The ONE model call of a consolidation answers the given payload."""

    async def answer(**kwargs):
        if on_generation is not None:
            await on_generation()
        content = payload
        tokens_in, tokens_out = 11, 7
        return AIMessage(
            content=content if isinstance(content, str) else json.dumps(content),
            usage_metadata={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "total_tokens": tokens_in + tokens_out,
            },
        )

    call = AsyncMock(side_effect=answer)
    monkeypatch.setattr(consolidation, "invoke_with_instrumentation", call)
    return call


async def _run(user):
    return await consolidation.consolidate_journals_for_user(user.id, None, None, "fr")


async def test_invalid_json_records_failed_attempt_without_consuming_success(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    await _entry(db, user)
    _answer(monkeypatch, "{")
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "invalid_output"
    assert user.journal_last_attempted_at is not None
    assert user.journal_last_consolidated_at is None
    assert user.journal_consolidated_revision is None
    assert user.journal_consolidation_owner is None
    assert consolidation._file_consolidation.await_args.kwargs["failed"] is True
    query = build_consolidation_eligible_users_query(datetime.now(UTC) - timedelta(hours=1), 1)
    assert user.id not in [row.id for row in (await db.scalars(query)).all()]


async def test_failed_action_rolls_back_other_actions_and_portrait(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    _answer(
        monkeypatch,
        {
            "actions": [
                {
                    "action": "create",
                    "theme": "learnings",
                    "title": "First",
                    "content": "A useful first rule.",
                },
                {
                    "action": "create",
                    "theme": "learnings",
                    "title": "Second",
                    "content": "A useful second rule.",
                },
            ],
            "portrait_claims": [_claim(entry)],
        },
    )
    original = JournalService.create_entry

    async def create(service, **kwargs):
        if kwargs["title"] == "Second":
            raise RuntimeError("simulated settlement failure")
        return await original(service, **kwargs)

    monkeypatch.setattr(JournalService, "create_entry", create)
    assert await _run(user) == 0
    # The shared-session fixture expires ORM identities on rollback; production
    # settlements use a separate session from the caller.
    await db.refresh(user)
    await db.refresh(entry)
    rows = (await db.scalars(select(JournalEntry).where(JournalEntry.user_id == user.id))).all()
    assert [row.id for row in rows] == [entry.id]
    await db.refresh(user)
    assert user.journal_portrait_full is None and user.journal_last_consolidated_at is None
    assert user.journal_last_attempt_status == "failed"


async def test_edit_during_model_call_is_not_swallowed_by_completion_stamp(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)

    async def answer(**kwargs):
        await JournalService(db).update_entry(
            entry, content="WHEN urgent -> DO ask for options.", precomputed_embeddings=(None, None)
        )
        await db.commit()
        return AIMessage(content='{"actions":[],"portrait_claims":[]}')

    monkeypatch.setattr(consolidation, "invoke_with_instrumentation", answer)
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "stale"
    assert user.journal_last_consolidated_at is None
    assert user.journal_consolidated_revision != user.journal_revision


async def test_disabling_consent_during_call_prevents_settlement(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    await _entry(db, user)

    async def answer(**kwargs):
        user.journals_enabled = False
        user.extraction_revision += 1
        await db.commit()
        return AIMessage(content='{"actions":[],"portrait_claims":[]}')

    monkeypatch.setattr(consolidation, "invoke_with_instrumentation", answer)
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "stale"
    assert user.journal_portrait_compiled_at is None


async def test_last_deletion_marks_the_portrait_stale_and_remains_schedulable(isolated_runtime):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    user.journal_portrait_full = "A complete current passage."
    user.journal_portrait_sources = {
        "journal_revision": user.journal_revision,
        "source_state": await portrait_source_state(db, user),
    }
    user.journal_consolidated_revision = user.journal_revision
    await db.commit()
    assert await portrait_is_current(db, user)
    await JournalService(db).delete_entry(entry)
    await db.commit()
    await db.refresh(user)
    # The words stay and read as stale; the account is eligible again.
    assert user.journal_portrait_full is not None
    assert not await portrait_is_current(db, user)
    users = (await db.scalars(build_consolidation_eligible_users_query(datetime.now(UTC), 1))).all()
    assert user.id in [row.id for row in users]


async def test_same_account_manual_and_scheduled_work_share_a_lease(isolated_runtime):
    db = isolated_runtime
    user = await _user(db)
    first = await lifecycle.claim_consolidation(user.id, uuid4(), manual=False)
    assert first is not None
    assert await lifecycle.claim_consolidation(user.id, uuid4(), manual=True) is None
    await lifecycle.finish_attempt(user.id, first, "failed")
    second = await lifecycle.claim_consolidation(user.id, uuid4(), manual=True)
    assert second is not None
    # An old worker cannot release its successor's lease.
    await lifecycle.finish_attempt(user.id, first, "success")
    await db.refresh(user)
    assert user.journal_consolidation_owner == second.owner
    await lifecycle.finish_attempt(user.id, second, "no_op")


async def test_success_consumes_own_revision_and_explicit_empty_portrait_clears(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    _answer(
        monkeypatch,
        {
            "actions": [{"action": "update", "entry_id": str(entry.id), "title": "Useful rule"}],
            "portrait_claims": [],
        },
    )
    assert await _run(user) == 1
    await db.refresh(user)
    assert user.journal_consolidated_revision == user.journal_revision
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert user.journal_last_consolidated_at is not None
    assert user.journal_portrait_sources["portrait_pending"] is True
    assert await lifecycle.consolidation_needed(db, user)


async def test_bad_portrait_support_is_dropped_and_maintenance_applies(
    isolated_runtime, monkeypatch
):
    """An unprovable claim is dropped and counted; the batch is never refused for it."""
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    call = _answer(
        monkeypatch,
        {
            "actions": [{"action": "update", "entry_id": str(entry.id), "title": "New title"}],
            "portrait_claims": [
                {
                    **_claim(entry),
                    "supports": [
                        {"source": f"journal:{entry.id}", "quote": "The user is always decisive."}
                    ],
                }
            ],
        },
    )
    assert await _run(user) == 1
    await db.refresh(entry)
    await db.refresh(user)
    assert entry.title == "New title" and user.journal_last_consolidated_at is not None
    assert user.journal_last_attempt_status == "success"
    # Nothing admitted: one model call, nothing published.
    assert call.await_count == 1 and user.journal_portrait_full is None
    assert user.journal_portrait_sources["portrait_pending"] is True


async def test_explicit_empty_portrait_reports_publication_success(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    user.journal_portrait_full = "Previously stored portrait."
    user.journal_portrait_brief = "Previously stored portrait."
    await db.commit()
    _answer(monkeypatch, {"actions": [], "portrait_claims": []})
    attempt = lifecycle.ConsolidationAttempt()
    assert (
        await consolidation.consolidate_journals_for_user(
            user.id, None, None, "fr", manual=True, attempt=attempt
        )
        == 0
    )
    await db.refresh(user)
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert attempt.status == "success"
    assert user.journal_portrait_sources["portrait_pending"] is False


async def test_source_deletion_gate_and_nonmax_edit_invalidate_lineage(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    permission = {"enabled": True}

    async def allowed(_user):
        return permission["enabled"]

    monkeypatch.setattr(
        portrait_sources,
        "_REGISTRY",
        {
            "memories": (
                None,
                portrait_sources.FreshnessProbe(
                    table="memories",
                    user_column="user_id",
                    stamp_column="updated_at",
                    allowed=allowed,
                ),
            )
        },
    )
    first = Memory(user_id=user.id, content="First", category="personal", char_count=5)
    future = Memory(
        user_id=user.id,
        content="Second",
        category="personal",
        char_count=6,
        updated_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add_all([first, future])
    await db.commit()
    state = await portrait_source_state(db, user)
    user.journal_portrait_full = "Source-derived passage."
    user.journal_portrait_sources = {
        "journal_revision": user.journal_revision,
        "source_state": state,
    }
    user.journal_consolidated_revision = user.journal_revision
    await db.commit()
    assert await portrait_is_current(db, user)
    first.content = "Changed"
    await db.commit()
    assert not await portrait_is_current(db, user)  # MAX still belongs to future
    first.updated_at = datetime.now(UTC)
    user.journal_portrait_sources = {
        "journal_revision": user.journal_revision,
        "source_state": await portrait_source_state(db, user),
    }
    await db.commit()
    await db.execute(delete(Memory).where(Memory.id == first.id))
    await db.commit()
    assert not await portrait_is_current(db, user)
    assert await lifecycle.consolidation_needed(db, user)
    user.journal_portrait_sources = {
        "journal_revision": user.journal_revision,
        "source_state": await portrait_source_state(db, user),
    }
    await db.commit()
    permission["enabled"] = False
    assert not await portrait_is_current(db, user)


async def test_failed_source_read_is_paced_and_never_paid(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    await _entry(db, user)
    call = _answer(monkeypatch, {"actions": [], "portrait_claims": []})
    monkeypatch.setattr(
        consolidation,
        "build_portrait_source_sections",
        AsyncMock(
            return_value=PortraitSourceBundle(
                sections=dict.fromkeys(portrait_sources.PORTRAIT_SOURCE_KEYS, ""),
                provenance={
                    "version": 1,
                    "journal_entries": 1,
                    "sources": {"memories": {"status": "unavailable", "used": 0, "total": 0}},
                },
            )
        ),
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "sources_unavailable"
    assert user.journal_last_consolidated_at is None
    assert await lifecycle.consolidation_needed(db, user)
    call.assert_not_awaited()


async def test_stale_scheduler_candidate_cannot_repeat_paid_work(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    await _entry(db, user)
    call = _answer(monkeypatch, {"actions": [], "portrait_claims": []})
    assert await _run(user) == 0
    assert call.await_count == 1
    # A second worker may still hold the candidate fetched before completion.
    assert await _run(user) == 0
    assert call.await_count == 1
    attempt = lifecycle.ConsolidationAttempt()
    await consolidation.consolidate_journals_for_user(
        user.id, None, None, "fr", manual=True, attempt=attempt
    )
    assert call.await_count == 2 and attempt.status == "success"  # the manual run


async def test_refused_manual_attempt_does_not_report_previous_success(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    user.journals_enabled = False
    user.journal_last_attempt_status = "success"
    await db.commit()
    call = _answer(monkeypatch, {"actions": []})
    attempt = lifecycle.ConsolidationAttempt()
    assert (
        await consolidation.consolidate_journals_for_user(
            user.id, None, None, "fr", manual=True, attempt=attempt
        )
        == 0
    )
    assert attempt.status == "disabled"
    call.assert_not_awaited()


async def test_unchanged_update_is_not_reported_as_a_mutation(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    _answer(
        monkeypatch,
        {"actions": [{"action": "update", "entry_id": str(entry.id), "title": entry.title}]},
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "no_op"


def _independent_action():
    return {
        "action": "create",
        "theme": "learnings",
        "title": "Independent rule",
        "content": "WHEN planning a long-term project -> DO compare several options.",
    }


async def test_an_admitted_natural_portrait_keeps_private_proofs_out_of_display(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    claim = _claim(entry)
    call = _answer(monkeypatch, {"actions": [], "portrait_claims": [claim]})
    assert await _run(user) == 0
    await db.refresh(user)
    assert call.await_count == 1 and user.journal_last_attempt_status == "success"
    # A `full` claim writes the full portrait; the brief is its own claims (none here).
    assert user.journal_portrait_full == claim["text"] and user.journal_portrait_brief is None
    assert entry.content not in user.journal_portrait_full
    assert str(entry.id) not in user.journal_portrait_full
    provenance = user.journal_portrait_sources
    assert provenance["claims"] == [claim]
    assert "portrait_review" not in provenance
    assert provenance["portrait_pending"] is False
    assert await portrait_is_current(db, user)
    assert not await lifecycle.consolidation_needed(db, user)


async def test_support_mutated_by_same_batch_is_dropped_and_never_published(
    isolated_runtime, monkeypatch
):
    """A claim resting on an entry this batch changes is dropped at admission and
    never reaches the words (found by this net, 2026-10-12).
    """
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    call = _answer(
        monkeypatch,
        {
            "actions": [{"action": "update", "entry_id": str(entry.id), "title": "Changed"}],
            "portrait_claims": [_claim(entry)],
        },
    )
    assert await _run(user) == 1
    await db.refresh(entry)
    await db.refresh(user)
    assert call.await_count == 1
    assert entry.title == "Changed" and user.journal_last_attempt_status == "success"
    assert user.journal_last_consolidated_at is not None
    assert user.journal_portrait_full is None and user.journal_portrait_brief is None
    assert user.journal_portrait_sources["portrait_pending"] is True


async def test_a_zero_effect_update_does_not_bar_the_claims_citing_its_entry(
    isolated_runtime, monkeypatch
):
    """An update that changes nothing is no change: the reading citing the entry is published."""
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    _answer(
        monkeypatch,
        {
            "actions": [{"action": "update", "entry_id": str(entry.id), "title": entry.title}],
            "portrait_claims": [_claim(entry)],
        },
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "success"
    assert user.journal_portrait_full == _claim(entry)["text"]


async def test_a_synthesis_its_supports_cannot_carry_no_longer_voids_the_paid_pass(
    isolated_runtime, monkeypatch
):
    """Measured 2026-10-12 c: one such synthesis lost the whole paid run, portrait included.

    The synthesis is created at L1 (its supports are immature), the other actions and
    the portrait proceed, and the run is a success.
    """
    db = isolated_runtime
    user = await _user(db)
    first = await _entry(db, user)
    second = await _entry(db, user, "WHEN reporting -> DO cite the source BECAUSE trust.")
    call = _answer(
        monkeypatch,
        {
            "actions": [
                {
                    "action": "create",
                    "theme": "user_observations",
                    "title": "Evidence first",
                    "content": "Across contexts, the user decides on evidence first.",
                    "level": "L2",
                    "confidence": "high",
                    "support_ids": [str(first.id), str(second.id)],
                },
                {"action": "update", "entry_id": str(second.id), "title": "Sources"},
            ],
            "portrait_claims": [_claim(first)],
        },
    )
    assert await _run(user) == 2
    await db.refresh(user)
    assert call.await_count == 1
    assert user.journal_last_attempt_status == "success"
    assert user.journal_portrait_full == _claim(first)["text"]
    created = (
        await db.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user.id, JournalEntry.title == "Evidence first"
            )
        )
    ).scalar_one()
    assert (created.level, created.confidence) == ("L1", "medium")


async def test_a_support_cited_by_its_portrait_id_no_longer_voids_the_paid_pass(
    isolated_runtime, monkeypatch
):
    """Measured 2026-10-13: three actions citing `pi_` ids refused the whole paid run.

    The unreadable action is dropped alone; the valid one applies and the portrait
    is published.
    """
    db = isolated_runtime
    user = await _user(db)
    first = await _entry(db, user)
    second = await _entry(db, user, "WHEN reporting -> DO cite the source BECAUSE trust.")
    call = _answer(
        monkeypatch,
        {
            "actions": [
                {
                    "action": "update",
                    "entry_id": str(second.id),
                    "level": "L2",
                    "support_ids": ["pi_" + "0" * 64, str(first.id)],
                },
                {"action": "update", "entry_id": str(second.id), "title": "Sources"},
            ],
            "portrait_claims": [_claim(first)],
        },
    )
    assert await _run(user) == 1
    await db.refresh(user)
    await db.refresh(second)
    assert call.await_count == 1
    assert user.journal_last_attempt_status == "success"
    assert user.journal_portrait_full == _claim(first)["text"]
    # The unreadable promotion never applied; the readable retitle, alone on its entry, did.
    assert second.title == "Sources" and second.level == "L1"


async def test_an_action_on_an_unknown_entry_is_dropped_and_the_rest_applies(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    first = await _entry(db, user)
    second = await _entry(db, user, "WHEN reporting -> DO cite the source BECAUSE trust.")
    _answer(
        monkeypatch,
        {
            "actions": [
                {"action": "update", "entry_id": str(uuid4()), "title": "Ghost"},
                {"action": "update", "entry_id": str(second.id), "title": "Sources"},
            ],
            "portrait_claims": [_claim(first)],
        },
    )
    assert await _run(user) == 1
    await db.refresh(user)
    await db.refresh(second)
    assert user.journal_last_attempt_status == "success"
    assert second.title == "Sources"
    assert user.journal_portrait_full == _claim(first)["text"]


async def test_every_action_refused_and_no_portrait_answer_stays_invalid(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    await _entry(db, user)
    _answer(
        monkeypatch, {"actions": [{"action": "update", "entry_id": str(uuid4()), "title": "X"}]}
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert user.journal_last_attempt_status == "invalid_output"
    assert user.journal_last_consolidated_at is None
