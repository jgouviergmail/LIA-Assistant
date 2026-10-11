"""A call's displayed consumption cannot borrow a foreign account's same-named run."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.phone_history_operations import read_phone_history
from src.domains.chat.models import MessageTokenSummary
from src.domains.chat.repository import ChatRepository
from src.domains.telephony.history_gateway import SavedPhoneHistory
from src.domains.telephony.history_queries import read_call_history
from src.domains.telephony.history_schemas import PhoneHistoryRead
from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.users.models import User
from src.infrastructure.phone_history import configure_phone_history

pytestmark = pytest.mark.integration


async def test_phone_history_pages_ties_and_preserves_owned_recorded_usage_without_private_fields(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "telephony_enabled", True)
    other_id = uuid4()
    other = User(id=other_id, email=f"other-history-{other_id}@example.test", is_active=True)
    async_session.add(other)
    await async_session.flush()
    now = datetime.now(UTC)
    identities = sorted([uuid4(), uuid4(), uuid4()], reverse=True)
    calls = [
        PhoneCall(
            id=identity,
            user_id=test_user.id,
            callee_display="Callee",
            callee_phone="private-callee-cipher",
            objective="Objective",
            status=PhoneCallStatus.COMPLETED,
            call_mode="direct",
            created_at=now,
        )
        for identity in identities
    ]
    foreign = PhoneCall(
        id=uuid4(),
        user_id=other.id,
        callee_display="Foreign callee",
        callee_phone="private-foreign-cipher",
        objective="Private objective",
        status=PhoneCallStatus.COMPLETED,
        call_mode="direct",
        created_at=now,
    )
    usage = MessageTokenSummary(
        user_id=test_user.id,
        session_id=str(uuid4()),
        run_id=f"phone_call_{identities[0].hex}",
        total_prompt_tokens=10,
        total_cost_eur=Decimal("0.05"),
        google_api_cost_eur=Decimal("0.03"),
        image_generation_cost_eur=Decimal("0.04"),
        tts_cost_eur=Decimal("0.02"),
    )
    async_session.add_all([*calls, foreign, usage])
    await async_session.commit()
    first = await read_call_history(async_session, test_user.id, PhoneHistoryRead(limit=1))
    previous = configure_phone_history(SavedPhoneHistory())
    try:
        native = await read_phone_history(async_session, test_user.id, PhoneHistoryRead(limit=1))
        assert native == first
    finally:
        configure_phone_history(previous)
    second = await read_call_history(
        async_session, test_user.id, PhoneHistoryRead(limit=2, cursor=first.next_cursor)
    )
    assert first.total == 3 and first.calls[0].id == identities[0]
    assert [row.id for row in second.calls] == identities[1:] and second.next_cursor is None
    assert first.calls[0].usage.tokens_in == 10 and first.calls[0].usage.cost_eur == 0.14
    assert second.calls[0].usage is None
    public = first.model_dump_json() + second.model_dump_json()
    assert (
        "private-callee" not in public
        and "Foreign callee" not in public
        and "Private objective" not in public
    )
    assert first.usage_scope == "recorded_platform_runs"
    with pytest.raises(ValueError):
        await read_call_history(async_session, test_user.id, PhoneHistoryRead(cursor=foreign.id))


async def test_call_usage_batch_is_conditioned_on_the_acting_owner(
    async_session: AsyncSession, test_user: User
) -> None:
    run_id = f"phone_call_{uuid4().hex}"
    other_id = uuid4()
    other = User(
        id=other_id, email=f"foreign-phone-history-{other_id}@example.test", is_active=True
    )
    async_session.add(other)
    await async_session.flush()
    own_run = f"phone_call_{uuid4().hex}"
    own = MessageTokenSummary(
        user_id=test_user.id,
        session_id=str(uuid4()),
        run_id=own_run,
        total_prompt_tokens=10,
        total_completion_tokens=1,
        total_cached_tokens=0,
        total_cost_eur=Decimal("0.01"),
    )
    foreign = MessageTokenSummary(
        user_id=other.id,
        session_id=str(uuid4()),
        run_id=run_id,
        total_prompt_tokens=999,
        total_completion_tokens=1,
        total_cached_tokens=0,
        total_cost_eur=Decimal("99.99"),
    )
    async_session.add_all([own, foreign])
    await async_session.commit()
    summaries = await ChatRepository(async_session).get_token_summaries_by_run_ids(
        [run_id, own_run], user_id=test_user.id
    )
    assert run_id not in summaries
    assert summaries[own_run].id == own.id
    assert summaries[own_run].total_prompt_tokens == 10
