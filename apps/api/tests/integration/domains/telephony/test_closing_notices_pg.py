"""A call a sweep closes is never closed in silence (2026-11-14), on PostgreSQL.

The stale-call reaper and the return reaper used to close a call and say
nothing (production: ``stale_no_webhook``, 2026-07-17, no notice, no return).
They now arm the call's return outbox in the same transaction, in the owner's
language, and the notification reaper picks it up past its grace window.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.i18n_telephony import get_return_phrases
from src.core.security.utils import encrypt_data
from src.domains.telephony.closing_notices import ClosingReason, arm_closing_notices
from src.domains.telephony.models import (
    CallKind,
    NotificationStatus,
    PhoneCall,
    PhoneCallStatus,
)
from src.domains.telephony.repository import TelephonyRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

_LONG_AGO = timedelta(hours=2)


async def _stale_calls(
    db: AsyncSession, *, language: str
) -> tuple[PhoneCall, PhoneCall, PhoneCall, PhoneCall]:
    """Four in-flight calls past the stale threshold, one per account (an account
    holds one active call at a time), all in ``language``: a third-party call,
    an owner call, a Live owner call and a verification."""
    users = [UserFactory.create() for _ in range(4)]
    for user in users:
        user.language = language
    db.add_all(users)
    await db.flush()
    calls = (
        PhoneCall(
            user_id=users[0].id,
            callee_display="Garage Martin",
            callee_phone="+33600000001",
            objective="Book a service",
            status=PhoneCallStatus.DIALING,
            call_kind=CallKind.THIRD_PARTY,
        ),
        PhoneCall(
            user_id=users[1].id,
            callee_display="Alex",
            callee_phone="+33600000002",
            objective="Owner call",
            status=PhoneCallStatus.IN_PROGRESS,
            call_kind=CallKind.SELF,
            call_mode="direct",
        ),
        PhoneCall(
            user_id=users[2].id,
            callee_display="Alex",
            callee_phone="+33600000002",
            objective="Live owner call",
            status=PhoneCallStatus.IN_PROGRESS,
            call_kind=CallKind.SELF,
            call_mode="delegated",
        ),
        PhoneCall(
            user_id=users[3].id,
            callee_display="Alex",
            callee_phone="+33600000002",
            objective="Verification",
            status=PhoneCallStatus.DIALING,
            call_kind=CallKind.VERIFICATION,
        ),
    )
    db.add_all(calls)
    await db.flush()
    for call in calls:
        call.created_at = datetime.now(UTC) - _LONG_AGO
    await db.flush()
    return calls


async def test_the_stale_sweep_closes_and_tells_in_the_owners_language(
    async_session: AsyncSession,
) -> None:
    third, owner, live, verification = await _stale_calls(async_session, language="de")
    repo = TelephonyRepository(async_session)

    closed = await repo.recover_stale(timeout_minutes=15)
    armed = await arm_closing_notices(async_session, repo, closed, ClosingReason.NO_REPORT)
    await async_session.commit()

    assert {c.id for c in closed} == {third.id, owner.id, live.id, verification.id}
    assert armed == 2
    phrases = get_return_phrases("de")
    for call in (third, owner, live, verification):
        await async_session.refresh(call)
        assert call.status == PhoneCallStatus.FAILED
        assert call.error == "stale_no_webhook"
        assert call.completed_at is not None
    assert third.notification_status == NotificationStatus.PENDING
    assert third.notification_payload == {
        "content": phrases["no_report"].format(callee="Garage Martin"),
        "title": phrases["title"],
    }
    assert owner.notification_status == NotificationStatus.PENDING
    assert owner.notification_payload == {
        "content": phrases["relay_no_report"],
        "title": phrases["self_call_title"],
    }
    # Nothing left to return: a Live call's requests reached the chat during
    # the call; a verification call only read a code.
    assert live.notification_status is None
    assert verification.notification_status is None


async def test_the_notification_reaper_picks_up_what_the_stale_sweep_armed(
    async_session: AsyncSession,
) -> None:
    third, owner, _live, _verification = await _stale_calls(async_session, language="fr")
    repo = TelephonyRepository(async_session)
    closed = await repo.recover_stale(timeout_minutes=15)
    await arm_closing_notices(async_session, repo, closed, ClosingReason.NO_REPORT)
    await async_session.commit()

    # Past the grace window, both notices are the reaper's to deliver.
    recoverable = await repo.fetch_recoverable_notifications(
        cutoff=datetime.now(UTC) + timedelta(minutes=1), max_attempts=5, limit=50
    )
    assert {third.id, owner.id} <= {c.id for c in recoverable}


async def test_a_synthesis_given_up_is_told_and_its_transcript_purged(
    async_session: AsyncSession,
) -> None:
    third, *_others = await _stale_calls(async_session, language="it")
    repo = TelephonyRepository(async_session)
    now = datetime.now(UTC)
    await repo.persist_return_inbox(
        third.id, encrypted_payload=encrypt_data("{}"), received_at=now - timedelta(hours=3)
    )

    retired = await repo.expire_stale_returns(max_age_cutoff=now - timedelta(minutes=60))
    armed = await arm_closing_notices(async_session, repo, retired, ClosingReason.SYNTHESIS_GAVE_UP)
    await async_session.commit()

    assert [c.id for c in retired] == [third.id] and armed == 1
    await async_session.refresh(third)
    assert third.return_webhook_encrypted is None
    assert third.error == "return_synthesis_gave_up"
    phrases = get_return_phrases("it")
    assert third.notification_payload == {
        "content": phrases["fallback"],
        "title": phrases["title"],
    }


async def test_a_notice_already_armed_is_never_overwritten(async_session: AsyncSession) -> None:
    third, *_others = await _stale_calls(async_session, language="en")
    repo = TelephonyRepository(async_session)
    third.notification_status = NotificationStatus.DELIVERED
    third.notification_payload = {"content": "delivered before", "title": "t"}
    await async_session.flush()

    assert not await repo.arm_closing_notice(third.id, content="new", title="t")
    await async_session.refresh(third)
    assert third.notification_payload == {"content": "delivered before", "title": "t"}
