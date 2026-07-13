"""Integration tests for TelephonyRepository (P1.4 + P4).

Exercises the DB-level partial unique index (F12) and the status-predicated
UPDATEs (``mark_completed`` exactly-once, ``recover_stale``) — the latter can
ONLY be trusted against real PostgreSQL because ``Enum(native_enum=False)``
stores the member NAME uppercase, and a mismatched ``.in_(...)`` bind would make
the conditional UPDATE silently match nothing (the P1 name/value trap).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from src.domains.telephony.models import PhoneCall, PhoneCallOutcome, PhoneCallStatus
from src.domains.telephony.repository import TelephonyRepository


def _call_data(user_id, **overrides):
    data = {
        "user_id": user_id,
        "callee_display": "Marie",
        "callee_phone": "encrypted-number",
        "objective": "restaurant Saturday noon",
        "status": PhoneCallStatus.DIALING,
    }
    data.update(overrides)
    return data


@pytest.mark.integration
async def test_get_active_for_user_none_when_no_active(async_session, test_user):
    repo = TelephonyRepository(async_session)
    assert await repo.get_active_for_user(test_user.id) is None


@pytest.mark.integration
async def test_one_active_call_per_user_is_enforced(async_session, test_user):
    repo = TelephonyRepository(async_session)
    first = await repo.create(_call_data(test_user.id))
    assert first.id is not None

    active = await repo.get_active_for_user(test_user.id)
    assert active is not None and active.id == first.id

    # A second in-flight call for the same user violates the partial unique index.
    with pytest.raises(IntegrityError):
        await repo.create(_call_data(test_user.id, objective="second call"))


@pytest.mark.integration
async def test_completed_call_frees_the_active_slot(async_session, test_user):
    repo = TelephonyRepository(async_session)
    first = await repo.create(_call_data(test_user.id))

    # Complete the first call → it leaves the "active" partial index.
    first.status = PhoneCallStatus.COMPLETED
    await async_session.flush()

    second = await repo.create(_call_data(test_user.id, objective="second call"))
    assert second.id is not None

    active = await repo.get_active_for_user(test_user.id)
    assert active is not None and active.id == second.id


@pytest.mark.integration
async def test_get_by_elevenlabs_conversation_id(async_session, test_user):
    repo = TelephonyRepository(async_session)
    call = await repo.create(_call_data(test_user.id, elevenlabs_conversation_id="conv_abc"))
    found = await repo.get_by_elevenlabs_conversation_id("conv_abc")
    assert found is not None and found.id == call.id
    assert await repo.get_by_elevenlabs_conversation_id("missing") is None


@pytest.mark.integration
async def test_mark_completed_is_exactly_once(async_session, test_user):
    """The conditional UPDATE matches the active row once (proves the enum predicate)."""
    repo = TelephonyRepository(async_session)
    call = await repo.create(_call_data(test_user.id))

    won = await repo.mark_completed(
        call.id,
        status=PhoneCallStatus.COMPLETED,
        call_seconds=Decimal("42"),
        summary="She is free Tuesday.",
        structured_data={"agreed": True},
        outcome=PhoneCallOutcome.OBJECTIVE_MET,
        completed_at=datetime.now(UTC),
    )
    assert won is True  # rowcount>0 → the .in_(_ACTIVE_STATUSES) predicate matched

    await async_session.refresh(call)
    assert call.status == PhoneCallStatus.COMPLETED
    assert call.summary == "She is free Tuesday."
    assert call.structured_data == {"agreed": True}
    assert call.outcome == PhoneCallOutcome.OBJECTIVE_MET

    # A duplicated webhook loses the race — the row is already terminal.
    lost = await repo.mark_completed(
        call.id,
        status=PhoneCallStatus.COMPLETED,
        call_seconds=None,
        summary="DUPLICATE",
        structured_data={},
        outcome=None,
        completed_at=datetime.now(UTC),
    )
    assert lost is False
    await async_session.refresh(call)
    assert call.summary == "She is free Tuesday."  # not overwritten


@pytest.mark.integration
async def test_recover_stale_marks_old_active_failed(async_session, test_user):
    """An in-flight call older than the timeout is swept to failed (rowcount proves it)."""
    repo = TelephonyRepository(async_session)
    call = await repo.create(_call_data(test_user.id))

    # Backdate created_at past the timeout window.
    await async_session.execute(
        update(PhoneCall)
        .where(PhoneCall.id == call.id)
        .values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await async_session.flush()

    count = await repo.recover_stale(timeout_minutes=15)
    assert count == 1  # the active + old row was matched and transitioned

    await async_session.refresh(call)
    assert call.status == PhoneCallStatus.FAILED


@pytest.mark.integration
async def test_purge_expired_clears_content_only(async_session, test_user):
    """The retention reaper clears summary/structured_data but keeps the row (D-8)."""
    repo = TelephonyRepository(async_session)
    call = await repo.create(
        _call_data(
            test_user.id,
            status=PhoneCallStatus.COMPLETED,
            summary="sensitive recap",
            structured_data={"agreed": True},
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )

    count = await repo.purge_expired()
    assert count == 1

    await async_session.refresh(call)
    assert call.summary is None
    assert call.structured_data == {}
    assert call.callee_display == "Marie"  # the row itself survives (audit)


@pytest.mark.integration
async def test_list_recent_for_user_orders_newest_first(async_session, test_user):
    repo = TelephonyRepository(async_session)
    first = await repo.create(_call_data(test_user.id, objective="first call"))
    first.status = PhoneCallStatus.COMPLETED  # free the active slot (F12)
    await async_session.flush()
    second = await repo.create(_call_data(test_user.id, objective="second call"))

    recent = await repo.list_recent_for_user(test_user.id, limit=10)
    assert [c.id for c in recent] == [second.id, first.id]
