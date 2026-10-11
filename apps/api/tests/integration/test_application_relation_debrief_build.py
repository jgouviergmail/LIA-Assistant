"""A paid debrief request is a proposal until exact approval and source claim."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.llm_usage import LLMUsage
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.relation_debrief_build import (
    execute_relation_debrief_build,
    prepare_relation_debrief_build,
)
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildRequest,
)
from src.domains.agents.tools import application_relation_tools
from src.domains.relations.debrief.controls import check_debrief_boundary
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.relations.debrief.schemas import DebriefBody, DebriefStatus, RelationDebriefRead
from src.domains.relations.overview import OverviewEvidence
from src.domains.relations.schemas import RelationDetail
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


async def test_debrief_build_tool_only_prepares_confirmation(async_session, test_user, monkeypatch):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_relation_tools, "get_db_context", session)
    source = AsyncMock(side_effect=AssertionError("Preparation cannot build"))
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService.build", source
    )
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_relation_tools.generate_lia_relation_debrief_tool.coroutine(
            request={"name": "Alice", "force": False},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert result.success and result.metadata["requires_confirmation"]
    assert (
        await async_session.scalar(
            select(RelationDebrief.id).where(RelationDebrief.user_id == owner)
        )
        is None
    )
    source.assert_not_awaited()


@pytest.mark.parametrize(
    "scenario",
    [
        "paid",
        "empty",
        "failed",
        "expired",
        "stale",
        "late_off",
        "before_paid_off",
        "rate_limit",
        "claim_lost_ack",
        "claim_committed_lost_ack",
        "paid_lost_ack",
        "paid_committed_lost_ack",
        "false_source_result",
    ],
)
async def test_debrief_source_claim_model_and_settlement_boundaries(
    async_session, test_user, monkeypatch, scenario
):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in (
        "src.domains.agents.application.relation_debrief_build",
        "src.domains.relations.debrief.service",
    ):
        monkeypatch.setattr(f"{module}.get_db_context", session)
    detail = RelationDetail(
        display_name="Alice",
        identity_confidence="exact",
        open_loops=[],
        recent_calls=[],
        memories=[],
        peer_messages=[],
        open_loops_total=0,
        recent_calls_total=0,
        memories_total=0,
        peer_messages_total=0,
        peer_link=None,
        is_favorite=False,
        is_peer=False,
    )
    evidence = OverviewEvidence(
        detail=detail,
        blocks={} if scenario == "empty" else {"open_loops": [{"subject": "Call Alice"}]},
        unavailable=[],
    )

    async def fetch(*args, **kwargs):
        if scenario == "before_paid_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return evidence

    monkeypatch.setattr("src.domains.relations.debrief.service.build_overview_evidence", fetch)

    async def write(**kwargs):
        await check_debrief_boundary(owner, "work")
        if scenario == "failed":
            raise RuntimeError("Provider refused")
        if scenario == "late_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return DebriefBody(headline="Stored result", where_we_stand="Source evidence"), LLMUsage(
            tokens_in=3,
            tokens_out=2,
            cost_eur=0,
            model_name="controlled-model",
            accounting_handled=True,
        )

    model = AsyncMock(side_effect=write)
    monkeypatch.setattr("src.domains.relations.debrief.service.write_debrief", model)
    monkeypatch.setattr(
        "src.domains.relations.debrief.service.RelationDebriefService._record_consultations",
        lambda *args: None,
    )
    request = RelationDebriefBuildRequest(name="Alice", force=True)
    draft = await prepare_relation_debrief_build(async_session, owner, request)
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "stale":
        await async_session.execute(update(User).where(User.id == owner).values(language="en"))
        await async_session.commit()
    if scenario == "rate_limit":
        monkeypatch.setattr(settings, "relation_debrief_daily_build_cap", 1)
        limiter = await get_rate_limiter()
        assert await limiter.acquire(
            key=f"auth:relations_debrief_build:user:{owner}", max_calls=1, window_seconds=86400
        )
    if scenario == "false_source_result":
        monkeypatch.setattr(
            "src.domains.relations.debrief.service.RelationDebriefService.build",
            AsyncMock(
                return_value=RelationDebriefRead(
                    status=DebriefStatus.READY,
                    person="Alice",
                    body=DebriefBody(headline="Invented", where_we_stand="Not stored"),
                )
            ),
        )
    if scenario.endswith("lost_ack"):
        commit = async_session.commit
        target_state = (
            DebriefState.BUILDING if scenario.startswith("claim_") else DebriefState.READY
        )

        async def lose_ack():
            state = await async_session.scalar(
                select(RelationDebrief.state).where(RelationDebrief.user_id == owner)
            )
            if state is target_state:
                if "committed" in scenario:
                    await commit()
                raise OperationalError("commit", {}, RuntimeError("lost ACK"))
            await commit()

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    errors = {
        "expired": CommandRejected,
        "stale": ResourceConflictError,
        "failed": CommandRejected,
        "late_off": AuthorizationError,
        "before_paid_off": AuthorizationError,
        "rate_limit": CommandRejected,
        "claim_lost_ack": CommandRejected,
        "claim_committed_lost_ack": CommandRejected,
        "paid_lost_ack": CommandRejected,
        "paid_committed_lost_ack": CommandRejected,
        "false_source_result": ResourceConflictError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_relation_debrief_build(async_session, owner, draft, receipt)
        await async_session.rollback()
    else:
        await execute_relation_debrief_build(async_session, owner, draft, receipt)
        assert receipt.committed
    row = await async_session.scalar(
        select(RelationDebrief).where(RelationDebrief.user_id == owner)
    )
    if scenario in {"expired", "stale", "rate_limit", "claim_lost_ack", "false_source_result"}:
        assert row is None
        model.assert_not_awaited()
    elif scenario.endswith("lost_ack"):
        assert row is not None
        assert row.state is (
            DebriefState.READY if scenario == "paid_committed_lost_ack" else DebriefState.BUILDING
        )
        assert "Stored result" not in str(receipt.values)
        if scenario.startswith("claim_"):
            model.assert_not_awaited()
            assert not receipt.committed
        else:
            assert (
                receipt.committed
                and receipt.values["relation_debrief"]["generation_status"] == "completion_unknown"
            )
    else:
        assert row is not None and row.claim_owner is None
        assert row.state is (
            DebriefState.READY
            if scenario == "paid"
            else DebriefState.EMPTY if scenario == "empty" else DebriefState.FAILED
        )
    if scenario in {"empty", "expired", "stale", "before_paid_off"}:
        model.assert_not_awaited()
    if scenario == "late_off":
        assert "Stored result" not in str(receipt.values)
    if scenario == "paid":
        model.assert_awaited_once()
        assert receipt.values["relation_debrief"]["new_synthesis"]
        no_op = PreferenceWriteReceipt()
        reused = await prepare_relation_debrief_build(
            async_session, owner, RelationDebriefBuildRequest(name="Alice", force=False)
        )
        await execute_relation_debrief_build(async_session, owner, reused, no_op)
        assert no_op.committed and no_op.no_op
        assert no_op.values["relation_debrief"]["generation_status"] == "reused"
        assert not no_op.values["relation_debrief"]["new_synthesis"]
        model.assert_awaited_once()
        checked = await prepare_relation_debrief_build(
            async_session, owner, RelationDebriefBuildRequest(name="Alice", force=True)
        )
        checked_receipt = PreferenceWriteReceipt()
        await execute_relation_debrief_build(async_session, owner, checked, checked_receipt)
        assert checked_receipt.committed
        assert checked_receipt.values["relation_debrief"]["generation_status"] == "unchanged"
        assert not checked_receipt.values["relation_debrief"]["new_synthesis"]
        model.assert_awaited_once()
