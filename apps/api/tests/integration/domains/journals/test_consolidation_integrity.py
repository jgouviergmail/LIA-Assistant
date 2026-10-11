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
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals import consolidation_lifecycle as lifecycle
from src.domains.journals import consolidation_service as consolidation
from src.domains.journals import consolidation_settlement as settlement
from src.domains.journals.constants import JOURNAL_PORTRAIT_POLICY_VERSION
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


def _review_payload(messages):
    try:
        payload = json.loads(messages[-1].text)
    except AttributeError, TypeError, ValueError:
        return None
    return payload if isinstance(payload, dict) and "facets" in payload else None


def _claim(
    entry,
    text="Quand il demande explicitement une aide urgente, il attend une prochaine action concrète.",
):
    return {
        "facet": "interaction",
        "text": text,
        "supports": [{"source": f"journal:{entry.id}", "quote": entry.content}],
        "in_brief": True,
    }


def _answer(monkeypatch, payload, *, supported=True, on_generation=None, on_review=None):
    async def answer(**kwargs):
        review = _review_payload(kwargs["messages"])
        if review is not None:
            if on_review is not None:
                await on_review()
            content = {
                "reviews": [
                    {
                        "index": facet["index"],
                        "supported": supported,
                        "scope_preserved": True,
                        "uncertainty_preserved": True,
                        "synthesized": True,
                    }
                    for facet in review["facets"]
                ]
            }
            tokens_in, tokens_out = 5, 3
        else:
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


async def test_last_deletion_invalidates_portrait_and_remains_schedulable(isolated_runtime):
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
    assert user.journal_portrait_full is None and not await portrait_is_current(db, user)
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


async def test_bad_portrait_support_rolls_back_maintenance(isolated_runtime, monkeypatch):
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
    assert await _run(user) == 0
    await db.refresh(entry)
    await db.refresh(user)
    assert entry.title == "Rule" and user.journal_last_consolidated_at is None
    assert call.await_count == 1


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
    assert call.await_count == 2 and attempt.status == "success"


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


async def test_semantic_rejection_applies_no_action_and_consumes_no_success(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    call = _answer(
        monkeypatch,
        {
            "actions": [_independent_action()],
            "portrait_claims": [
                _claim(entry, "Il privilégie toujours la décision à l'exploration.")
            ],
        },
        supported=False,
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert call.await_count == 2
    rows = (await db.scalars(select(JournalEntry).where(JournalEntry.user_id == user.id))).all()
    assert [row.id for row in rows] == [entry.id]
    assert user.journal_last_attempt_status == "invalid_output"
    assert user.journal_last_consolidated_at is None
    assert user.journal_consolidated_revision is None and user.journal_portrait_full is None
    assert consolidation._file_consolidation.await_args.kwargs["failed"] is True


async def test_disable_before_review_prevents_additional_call(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)

    async def disable():
        user.journals_enabled = False
        user.extraction_revision += 1
        await db.commit()

    call = _answer(
        monkeypatch,
        {"actions": [_independent_action()], "portrait_claims": [_claim(entry)]},
        on_generation=disable,
    )
    assert await _run(user) == 0
    await db.refresh(user)
    assert call.await_count == 1
    assert user.journal_last_attempt_status == "stale"
    assert user.journal_last_consolidated_at is None and user.journal_portrait_full is None
    assert (await JournalService(db).get_all_active(user.id)) == [entry]
    assert consolidation._persist_journal_tokens.await_count == 1


async def test_edit_during_semantic_review_refuses_stale_publication(isolated_runtime, monkeypatch):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    changed = "WHEN urgent -> DO ask whether several options are wanted."

    async def edit():
        # Production workers have separate ORM identities. Sequential sessions
        # share only this test's isolated connection, never concurrent I/O.
        async with AsyncSession(
            bind=db.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as editor:
            current = await editor.get(JournalEntry, entry.id)
            await JournalService(editor).update_entry(
                current, content=changed, precomputed_embeddings=(None, None)
            )
            await editor.commit()

    call = _answer(
        monkeypatch,
        {"actions": [_independent_action()], "portrait_claims": [_claim(entry)]},
        on_review=edit,
    )
    assert await _run(user) == 0
    await db.refresh(entry)
    await db.refresh(user)
    assert call.await_count == 2
    assert entry.content == changed
    assert user.journal_last_attempt_status == "stale"
    assert user.journal_last_consolidated_at is None and user.journal_portrait_full is None
    assert (await JournalService(db).get_all_active(user.id)) == [entry]


async def test_approved_natural_portrait_keeps_private_proofs_out_of_display(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    claim = _claim(entry)
    call = _answer(monkeypatch, {"actions": [], "portrait_claims": [claim]})
    assert await _run(user) == 0
    await db.refresh(user)
    assert call.await_count == 2 and user.journal_last_attempt_status == "success"
    assert user.journal_portrait_full == user.journal_portrait_brief == claim["text"]
    assert entry.content not in user.journal_portrait_full
    assert str(entry.id) not in user.journal_portrait_full
    provenance = user.journal_portrait_sources
    assert provenance["claims"] == [claim]
    assert provenance["portrait_review"]["policy"] == JOURNAL_PORTRAIT_POLICY_VERSION
    assert len(provenance["portrait_review"]["digest"]) == 64
    assert provenance["portrait_pending"] is False
    assert await portrait_is_current(db, user)
    assert not await lifecycle.consolidation_needed(db, user)
    review = _review_payload(call.await_args_list[1].kwargs["messages"])
    assert review["facets"][0]["support_indices"] == [0]
    assert len(review["proofs"]) == 1
    assert review["proofs"][0]["quote"] == entry.content
    assert review["proofs"][0]["revision"] == entry.revision
    assert review["facets"][0]["in_brief"] is True


async def test_generation_and_review_share_billing_run_and_one_cost_projection(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    user = await _user(db)
    entry = await _entry(db, user)
    _answer(monkeypatch, {"actions": [], "portrait_claims": [_claim(entry)]})
    assert await _run(user) == 0
    persist = consolidation._persist_journal_tokens
    assert persist.await_count == 2
    first, second = [call.kwargs for call in persist.await_args_list]
    assert first["parent_run_id"] == second["parent_run_id"]
    assert first["node_name"] == second["node_name"] == "journal_consolidation"
    projection = consolidation._update_user_last_cost
    projection.assert_awaited_once()
    capture = projection.await_args.kwargs["capture"]
    assert capture is first["capture"] is second["capture"]
    records = capture.get_billing_records("synthetic-offline")
    assert [(record.tokens_in, record.tokens_out) for record in records] == [(11, 7), (5, 3)]
    assert capture.tokens_in == 16 and capture.tokens_out == 10


async def test_support_mutated_by_same_batch_is_refused_before_review(
    isolated_runtime, monkeypatch
):
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
    assert await _run(user) == 0
    await db.refresh(entry)
    await db.refresh(user)
    assert call.await_count == 1
    assert entry.title == "Rule" and user.journal_last_attempt_status == "invalid_output"
    assert user.journal_last_consolidated_at is None and user.journal_portrait_full is None
