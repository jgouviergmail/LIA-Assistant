"""Replay the canonical message/feedback/policy flow on disposable PostgreSQL."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.analysis.efficacy_context import EfficacyAnalysis, EfficacyTurnContext
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.efficacy_evidence import EfficacyCapture
from src.domains.agents.services.efficacy_feedback import record_final_message
from src.domains.agents.services.efficacy_provenance import finalize_provenance
from src.domains.agents.services.efficacy_runtime import build_efficacy_block
from src.domains.chat.models import TokenUsageLog
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.response_feedback import persist_verdict
from src.domains.psyche.efficacy_repository import EfficacyRepository
from src.domains.psyche.engine import PADVector
from src.domains.psyche.models import PsycheState
from src.domains.psyche.reset_policy import apply_psyche_reset

pytestmark = pytest.mark.integration


async def prepare(db, user, monkeypatch):
    monkeypatch.setattr(settings, "psyche_enabled", True)
    monkeypatch.setattr(settings, "psyche_efficacy_collection_enabled", True)
    monkeypatch.setattr(settings, "psyche_efficacy_influence_enabled", True)
    user.psyche_enabled = True
    state = PsycheState(user_id=user.id)
    db.add_all([state, Conversation(id=user.id, user_id=user.id)])
    await db.flush()
    return state


async def message(db, user, *, ambiguous=True, partial=False):
    repo = EfficacyRepository(db)
    epoch = await repo.capture_epoch(user.id)
    turn = EfficacyTurnContext(
        owner_id=user.id,
        run_id=str(uuid4()),
        epoch=epoch,
        analysis=EfficacyAnalysis(
            domains=(("organization",) if partial else ("technical",)),
            ambiguous=ambiguous,
            verification_needed=partial,
        ),
        issued_at=datetime.now(UTC),
    )
    capture = EfficacyCapture()
    capture.update(
        {
            "query_intelligence": {
                "efficacy_context": turn.model_dump(mode="json"),
                "domains": [],
                "original_query": "",
                "requested_outcomes": [],
            }
        },
        run_id=turn.run_id,
    )
    if partial:
        capture.update(partial_state(turn), run_id=turn.run_id)
    row = ConversationMessage(
        conversation_id=user.id,
        role="assistant",
        content="A useful answer",
        message_metadata={"run_id": turn.run_id, **capture.envelope(run_id=turn.run_id)},
    )
    db.add(row)
    db.add(
        TokenUsageLog(
            user_id=user.id,
            run_id=turn.run_id,
            node_name="response",
            model_name="test-model",
            provider="test-provider",
            llm_type="response",
        )
    )
    await db.flush()
    return row, turn


async def test_feedback_before_collector_and_reversal_does_not_invent_factual_success(
    async_session, test_user, monkeypatch
):
    await prepare(async_session, test_user, monkeypatch)
    row, turn = await message(async_session, test_user)
    await persist_verdict(async_session, test_user.id, row.id, "thumbs_up", None)
    assert not await record_final_message(async_session, test_user.id, row.id, "thumbs_up")
    assert await finalize_provenance(async_session, test_user.id, row.id)
    assert await record_final_message(async_session, test_user.id, row.id)
    repo = EfficacyRepository(async_session)
    profile = await repo.read_profile(test_user.id, now=datetime.now(UTC))
    domain = next(item for item in profile.domains if item.domain == "technical")
    assert domain.feedback.helpful == 1 and domain.result_count == 0
    await persist_verdict(async_session, test_user.id, row.id, "thumbs_down", None)
    assert await record_final_message(async_session, test_user.id, row.id, "thumbs_down")
    assert await record_final_message(async_session, test_user.id, row.id)
    domain = next(
        item
        for item in (await repo.read_profile(test_user.id, now=datetime.now(UTC))).domains
        if item.domain == "technical"
    )
    assert domain.feedback.helpful == 0 and domain.feedback.unhelpful == 1
    assert domain.results.unknown == 1


async def test_actual_private_feedback_changes_bounded_policy_but_off_reset_and_current_run_win(
    async_session, test_user, monkeypatch
):
    state = await prepare(async_session, test_user, monkeypatch)
    for _ in range(5):
        row, turn = await message(async_session, test_user)
        assert await finalize_provenance(async_session, test_user.id, row.id)
        assert await record_final_message(async_session, test_user.id, row.id, "thumbs_down")
    from src.domains.agents.services import efficacy_runtime

    runtime = LiaRuntimeContext.for_conversation(
        user_id=test_user.id, conversation_id=test_user.id, psyche_enabled=True
    )
    monkeypatch.setattr(efficacy_runtime, "runtime_context_if_running", lambda: runtime)

    @asynccontextmanager
    async def connection():
        yield async_session

    monkeypatch.setattr(efficacy_runtime, "get_db_context", connection)
    on = await build_efficacy_block(turn, run_id=turn.run_id, can_verify=False)
    assert '"action":"clarify"' in on
    assert (
        await build_efficacy_block(
            turn, run_id=turn.run_id, state=partial_state(turn, complete=True)
        )
        == ""
    )
    assert await build_efficacy_block(turn, run_id=turn.run_id, clarification_resolved=True) == ""
    assert "result_score" not in on
    assert await build_efficacy_block(turn, run_id="different-turn") == ""
    monkeypatch.setattr(settings, "psyche_efficacy_influence_enabled", False)
    assert await build_efficacy_block(turn, run_id=turn.run_id) == ""
    monkeypatch.setattr(settings, "psyche_efficacy_influence_enabled", True)
    apply_psyche_reset(state, "full", PADVector(0, 0, 0))
    await async_session.flush()
    assert await build_efficacy_block(turn, run_id=turn.run_id) == ""
    assert not await record_final_message(async_session, test_user.id, row.id)


@pytest.mark.parametrize(
    "exclusion", ["hitl_question", "interrupted", "provisional", "hidden_column", "user_disabled"]
)
async def test_feedback_on_ineligible_message_or_disabled_owner_is_neutral(
    async_session, test_user, monkeypatch, exclusion
):
    await prepare(async_session, test_user, monkeypatch)
    row, turn = await message(async_session, test_user)
    assert await finalize_provenance(async_session, test_user.id, row.id)
    if exclusion == "hidden_column":
        row.hidden = True
    elif exclusion == "user_disabled":
        test_user.psyche_enabled = False
    else:
        row.message_metadata = {**row.message_metadata, exclusion: True}
    await async_session.flush()
    assert not await record_final_message(async_session, test_user.id, row.id, "thumbs_down")
    profile = await EfficacyRepository(async_session).read_profile(
        test_user.id, now=datetime.now(UTC)
    )
    assert sum(item.feedback_count for item in profile.domains) == 0


def partial_state(turn, *, complete=False):
    from src.domains.agents.analysis.requested_outcomes import GoalRequirement
    from src.domains.agents.services.outcome_evidence import OutcomeEvidence

    goal = GoalRequirement(
        domain="event",
        label="All events",
        source_quote="tous mes rendez-vous",
        collection_key="events",
        requires_complete=True,
    )
    proof = OutcomeEvidence(
        tool_name="get_events_tool",
        domain="event",
        kind="read",
        success=True,
        complete=complete,
        arguments={},
        data={"events": [{"summary": "One event"}]},
    )
    return {
        "query_intelligence": {
            "efficacy_context": turn.model_dump(mode="json"),
            "domains": ["event"],
            "original_query": "tous mes rendez-vous",
            "requested_outcomes": [goal.model_dump(mode="json")],
        },
        "requested_outcome_evidence": [proof.model_dump(mode="json")],
    }


async def test_repeated_observed_partial_coverage_can_verify_or_state_limit_without_scoring_failure(
    async_session, test_user, monkeypatch
):
    await prepare(async_session, test_user, monkeypatch)
    for _ in range(5):
        row, turn = await message(async_session, test_user, ambiguous=False, partial=True)
        assert await finalize_provenance(async_session, test_user.id, row.id)
        assert await record_final_message(async_session, test_user.id, row.id)
    repo = EfficacyRepository(async_session)
    domain = next(
        item
        for item in (await repo.read_profile(test_user.id, now=datetime.now(UTC))).domains
        if item.domain == "organization"
    )
    assert domain.results.partial == 5 and domain.result_count == 0 and domain.result_score is None
    from src.domains.agents.services import efficacy_runtime

    runtime = LiaRuntimeContext.for_conversation(
        user_id=test_user.id, conversation_id=test_user.id, psyche_enabled=True
    )
    monkeypatch.setattr(efficacy_runtime, "runtime_context_if_running", lambda: runtime)

    @asynccontextmanager
    async def connection():
        yield async_session

    monkeypatch.setattr(efficacy_runtime, "get_db_context", connection)
    assert '"action":"verify"' in await build_efficacy_block(
        turn, run_id=turn.run_id, can_verify=True
    )
    assert '"action":"state_limit"' in await build_efficacy_block(
        turn, run_id=turn.run_id, can_verify=False
    )
    assert (
        await build_efficacy_block(
            turn, run_id=turn.run_id, state=partial_state(turn, complete=True), can_verify=True
        )
        == ""
    )


@pytest.mark.parametrize("status", ["inactive", "deleted"])
async def test_inactive_or_deleted_owner_cannot_collect(
    async_session, test_user, monkeypatch, status
):
    await prepare(async_session, test_user, monkeypatch)
    row, turn = await message(async_session, test_user)
    assert await finalize_provenance(async_session, test_user.id, row.id)
    if status == "inactive":
        test_user.is_active = False
    else:
        test_user.deleted_at = datetime.now(UTC)
    await async_session.flush()
    assert not await record_final_message(async_session, test_user.id, row.id, "thumbs_up")


async def test_optional_collection_deadline_releases_session_under_real_owner_contention(
    async_engine, committed_user_ids, monkeypatch
):
    import time

    from sqlalchemy import select

    from src.domains.agents.services import efficacy_feedback
    from src.domains.psyche.efficacy_contracts import EfficacyEpoch
    from src.domains.users.models import User

    async with AsyncSession(async_engine) as setup:
        account = User(
            email=f"deadline-{uuid4()}@example.test",
            full_name="Deadline test",
            is_active=True,
            psyche_enabled=True,
        )
        setup.add(account)
        await setup.flush()
        owner = account.id
        committed_user_ids.append(owner)
        await setup.commit()
    monkeypatch.setattr(settings, "psyche_enabled", True)
    monkeypatch.setattr(settings, "psyche_efficacy_collection_enabled", True)
    context = EfficacyTurnContext(
        owner_id=owner,
        run_id="blocked",
        epoch=EfficacyEpoch(state_id=uuid4(), generation=uuid4()),
        analysis=EfficacyAnalysis(domains=("technical",)),
        issued_at=datetime.now(UTC),
    )

    @asynccontextmanager
    async def connection():
        async with AsyncSession(async_engine) as session:
            yield session

    monkeypatch.setattr(efficacy_feedback, "get_db_context", connection)
    async with AsyncSession(async_engine) as blocker:
        await blocker.execute(select(User.id).where(User.id == owner).with_for_update())
        started = time.perf_counter()
        await efficacy_feedback.collect_final_message(owner, uuid4(), context=context)
        elapsed = time.perf_counter() - started
        assert 1.5 <= elapsed < 5.0
        await blocker.rollback()
