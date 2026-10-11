"""History projection is a shared bounded owner read; retained rows never imply a full invoice."""

from datetime import UTC, datetime
from decimal import Decimal
from importlib import import_module
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.chat.models import MessageTokenSummary
from src.domains.telephony.models import CallKind, PhoneCall, PhoneCallStatus

pytestmark = pytest.mark.unit


def test_new_source_history_field_requires_a_reviewed_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    monkeypatch.setattr(
        module.TelephonyCallSummary,
        "__pydantic_fields__",
        {**module.TelephonyCallSummary.model_fields, "future_private_field": object()},
    )
    with pytest.raises(AssertionError, match="projection review"):
        module.assert_history_projection_coverage()


@pytest.mark.parametrize("schema", ["StructuredCallData", "TelephonyCallUsage"])
def test_new_nested_source_field_requires_a_reviewed_projection(
    monkeypatch: pytest.MonkeyPatch, schema: str
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    model = getattr(module, schema)
    monkeypatch.setattr(
        model, "__pydantic_fields__", {**model.model_fields, "future_private_field": object()}
    )
    with pytest.raises(AssertionError, match="projection review"):
        module.assert_history_projection_coverage()


async def test_history_projection_uses_one_owner_conditioned_usage_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    actor_id = uuid4()
    call = PhoneCall(
        id=uuid4(),
        user_id=actor_id,
        callee_display="Callee",
        callee_phone="private-cipher",
        objective="Question",
        status=PhoneCallStatus.COMPLETED,
        call_kind=CallKind.THIRD_PARTY,
        call_mode="direct",
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(module, "delegated_runs_of", AsyncMock(return_value={}))
    batch = AsyncMock(return_value={})
    monkeypatch.setattr(module.ChatRepository, "get_token_summaries_by_run_ids", batch)
    listed = await module.project_call_history(AsyncMock(spec=AsyncSession), actor_id, [call])
    assert len(listed) == 1 and listed[0].usage is None
    assert "private-cipher" not in str(listed)
    batch.assert_awaited_once_with([f"phone_call_{call.id.hex}"], user_id=actor_id)


async def test_empty_history_does_not_issue_billing_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    batch = AsyncMock()
    monkeypatch.setattr(module.ChatRepository, "get_token_summaries_by_run_ids", batch)
    assert await module.project_call_history(AsyncMock(spec=AsyncSession), uuid4(), []) == []
    batch.assert_not_awaited()


async def test_foreign_call_row_is_refused_before_any_recorded_usage_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    batch = AsyncMock()
    monkeypatch.setattr(module.ChatRepository, "get_token_summaries_by_run_ids", batch)
    with pytest.raises(AuthorizationError):
        await module.project_call_history(
            AsyncMock(spec=AsyncSession), uuid4(), [PhoneCall(user_id=uuid4())]
        )
    batch.assert_not_awaited()


async def test_duplicate_delegation_stamps_cannot_charge_the_own_run_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = import_module("src.domains.telephony.history_queries")
    actor_id = uuid4()
    call = PhoneCall(
        id=uuid4(),
        user_id=actor_id,
        callee_display="Callee",
        callee_phone="private",
        objective="Question",
        status=PhoneCallStatus.COMPLETED,
        call_kind=CallKind.SELF,
        call_mode="delegated",
        created_at=datetime.now(UTC),
    )
    own = f"phone_call_{call.id.hex}"
    row = MessageTokenSummary(
        user_id=actor_id,
        session_id="session",
        run_id=own,
        total_prompt_tokens=10,
        total_completion_tokens=3,
        total_cached_tokens=2,
        total_cost_eur=Decimal("0.1"),
        google_api_requests=1,
    )
    monkeypatch.setattr(module, "delegated_runs_of", AsyncMock(return_value={own: [own, own]}))
    batch = AsyncMock(return_value={own: row})
    monkeypatch.setattr(module.ChatRepository, "get_token_summaries_by_run_ids", batch)
    listed = await module.project_call_history(AsyncMock(spec=AsyncSession), actor_id, [call])
    assert listed[0].usage.tokens_in == 10 and listed[0].usage.cost_eur == 0.1
    batch.assert_awaited_once_with([own], user_id=actor_id)
