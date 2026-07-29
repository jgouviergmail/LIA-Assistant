"""Integration tests for the T1 approach-A pre-synthesis return inbox.

Real-PostgreSQL coverage of the durability contract that closes the "crash
during synthesis loses the return" window: the webhook is persisted (encrypted)
as a ``RECEIVED`` inbox row before the 200, the return reaper replays stranded
rows, ``mark_completed`` purges the transcript, and neither the stale-call reaper
nor a duplicate webhook can corrupt the recovery.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.telephony.models import (
    PhoneCall,
    PhoneCallStatus,
    ReturnSynthesisStatus,
)
from src.domains.telephony.repository import TelephonyRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _make_active_call(db: AsyncSession, *, created_at: datetime | None = None) -> PhoneCall:
    """Persist a user + one DIALING (in-flight) PhoneCall, returning the call."""
    user = UserFactory.create()
    db.add(user)
    await db.flush()

    call = PhoneCall(
        user_id=user.id,
        callee_display="Dr. Smith",
        callee_phone="+33600000000",  # encrypted by the service layer in prod; raw here
        objective="Book an appointment",
        status=PhoneCallStatus.DIALING,
    )
    db.add(call)
    await db.flush()
    if created_at is not None:
        call.created_at = created_at
        await db.flush()
    return call


def _payload() -> dict:
    return {"data": {"transcript": [{"role": "agent", "message": "hi"}]}}


class TestPersistReturnInbox:
    async def test_persists_received_with_encrypted_payload(self, async_session: AsyncSession):
        call = await _make_active_call(async_session)
        repo = TelephonyRepository(async_session)
        received_at = datetime.now(UTC)

        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("secret-transcript"), received_at=received_at
        )

        await async_session.refresh(call)
        assert call.return_status == ReturnSynthesisStatus.RECEIVED
        assert call.return_received_at is not None
        # The transcript is stored ONLY encrypted (D-8) but is recoverable.
        assert call.return_webhook_encrypted is not None
        assert call.return_webhook_encrypted != "secret-transcript"
        assert decrypt_data(call.return_webhook_encrypted) == "secret-transcript"

    async def test_is_idempotent_for_a_duplicate_webhook(self, async_session: AsyncSession):
        call = await _make_active_call(async_session)
        repo = TelephonyRepository(async_session)
        now = datetime.now(UTC)
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("first"), received_at=now
        )
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("second"), received_at=now
        )
        await async_session.refresh(call)
        assert call.return_status == ReturnSynthesisStatus.RECEIVED
        assert decrypt_data(call.return_webhook_encrypted) == "second"

    async def test_never_reverts_a_synthesized_row(self, async_session: AsyncSession):
        call = await _make_active_call(async_session)
        repo = TelephonyRepository(async_session)
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("x"), received_at=datetime.now(UTC)
        )
        await repo.mark_completed(
            call.id,
            status=PhoneCallStatus.COMPLETED,
            call_seconds=Decimal("12.0"),
            summary="done",
            structured_data={},
            debrief=None,
            outcome=None,
            completed_at=datetime.now(UTC),
            notification_content="Return ready",
            notification_title="Call complete",
        )
        # A late duplicate webhook must NOT drag a completed synthesis back to RECEIVED.
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("late"), received_at=datetime.now(UTC)
        )
        await async_session.refresh(call)
        assert call.return_status == ReturnSynthesisStatus.SYNTHESIZED
        assert call.return_webhook_encrypted is None


class TestMarkCompletedPurgesInbox:
    async def test_synthesis_closes_inbox_and_purges_transcript(self, async_session: AsyncSession):
        call = await _make_active_call(async_session)
        repo = TelephonyRepository(async_session)
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("transcript"), received_at=datetime.now(UTC)
        )
        claimed = await repo.mark_completed(
            call.id,
            status=PhoneCallStatus.COMPLETED,
            call_seconds=Decimal("30.0"),
            summary="s",
            structured_data={},
            debrief=None,
            outcome=None,
            completed_at=datetime.now(UTC),
            notification_content="c",
            notification_title="t",
        )
        assert claimed is True
        await async_session.refresh(call)
        assert call.return_status == ReturnSynthesisStatus.SYNTHESIZED
        assert call.return_webhook_encrypted is None  # transcript purged (D-8)


class TestFetchRecoverableReturns:
    async def test_windows_on_grace_and_max_age(self, async_session: AsyncSession):
        repo = TelephonyRepository(async_session)
        now = datetime.now(UTC)

        recent = await _make_active_call(async_session)  # inside grace → skip
        await repo.persist_return_inbox(
            recent.id, encrypted_payload=encrypt_data("r"), received_at=now - timedelta(seconds=10)
        )
        recoverable = await _make_active_call(async_session)  # in window → picked
        await repo.persist_return_inbox(
            recoverable.id,
            encrypted_payload=encrypt_data("g"),
            received_at=now - timedelta(minutes=5),
        )
        ancient = await _make_active_call(async_session)  # past max-age → skip (expire owns it)
        await repo.persist_return_inbox(
            ancient.id, encrypted_payload=encrypt_data("a"), received_at=now - timedelta(hours=3)
        )

        rows = await repo.fetch_recoverable_returns(
            grace_cutoff=now - timedelta(seconds=120),
            max_age_cutoff=now - timedelta(minutes=60),
            limit=50,
        )
        ids = {c.id for c in rows}
        assert recoverable.id in ids
        assert recent.id not in ids
        assert ancient.id not in ids


class TestExpireStaleReturns:
    async def test_retires_and_purges_past_max_age(self, async_session: AsyncSession):
        repo = TelephonyRepository(async_session)
        now = datetime.now(UTC)
        call = await _make_active_call(async_session)
        await repo.persist_return_inbox(
            call.id, encrypted_payload=encrypt_data("old"), received_at=now - timedelta(hours=3)
        )
        count = await repo.expire_stale_returns(max_age_cutoff=now - timedelta(minutes=60))
        assert count == 1
        await async_session.refresh(call)
        assert call.return_status == ReturnSynthesisStatus.FAILED
        assert call.return_webhook_encrypted is None  # purged
        assert call.status == PhoneCallStatus.FAILED
        assert call.error == "return_synthesis_gave_up"


class TestRecoverStaleExcludesInbox:
    async def test_stale_reaper_never_fails_a_received_inbox_row(self, async_session: AsyncSession):
        repo = TelephonyRepository(async_session)
        old = datetime.now(UTC) - timedelta(hours=2)

        # A call whose webhook arrived (RECEIVED) — the return reaper owns it.
        with_inbox = await _make_active_call(async_session, created_at=old)
        await repo.persist_return_inbox(
            with_inbox.id, encrypted_payload=encrypt_data("t"), received_at=datetime.now(UTC)
        )
        # An ordinary in-flight call that never got a webhook — must still be reaped.
        no_webhook = await _make_active_call(async_session, created_at=old)

        reaped = await repo.recover_stale(timeout_minutes=30)
        await async_session.commit()

        await async_session.refresh(with_inbox)
        await async_session.refresh(no_webhook)
        assert with_inbox.status == PhoneCallStatus.DIALING  # untouched
        assert with_inbox.return_status == ReturnSynthesisStatus.RECEIVED
        assert no_webhook.status == PhoneCallStatus.FAILED  # reaped
        assert reaped >= 1
