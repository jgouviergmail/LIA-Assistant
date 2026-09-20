"""The vendor's bill at the end of a session: read on the person's key, shown, never recorded."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import (
    LIVE_VENDOR_BILL_SETTLE_ATTEMPTS,
    LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS,
)
from src.domains.live.schemas import LiveVendorBill
from src.domains.live.session_store import LiveSessionRecord
from src.domains.live.vendor_bill import fetch_vendor_bill

pytestmark = pytest.mark.unit

MODULE = "src.domains.live.vendor_bill"
BILL = LiveVendorBill(
    provider="elevenlabs", cost_usd=0.12, credits=12, llm_credits=4, call_credits=8
)


def _record(provider: str) -> LiveSessionRecord:
    now = datetime.now(UTC)
    return LiveSessionRecord(
        session_id="s" * 32,
        user_id=uuid.uuid4(),
        provider=provider,
        model="agent_1",
        run_id="live_session_s",
        started_at=now,
        expires_at=now + timedelta(minutes=5),
        token="t",
    )


def _connectors() -> MagicMock:
    connectors = MagicMock()
    connectors.connector_of = AsyncMock(
        return_value=SimpleNamespace(connector_type="elevenlabs_live")
    )
    connectors.api_key_of = AsyncMock(return_value="sk_test")
    return connectors


class _Billing:
    """A provider that states its bill (the ``VendorBilling`` protocol, structurally).

    ``answers`` plays the vendor read by read: None while it is still settling
    the conversation, then the bill.
    """

    provider_id = "elevenlabs"

    def __init__(
        self,
        bill: LiveVendorBill | None = BILL,
        error: Exception | None = None,
        answers: list[LiveVendorBill | None] | None = None,
    ):
        self.bill, self.error = bill, error
        self.answers = answers
        self.asked: list[tuple[str, str]] = []

    async def conversation_bill(
        self, api_key: str, conversation_id: str, *, timeout: float
    ) -> LiveVendorBill | None:
        self.asked.append((api_key, conversation_id))
        if self.error is not None:
            raise self.error
        if self.answers is not None:
            return self.answers.pop(0) if self.answers else None
        return self.bill


async def test_the_bill_is_read_on_the_persons_key_under_the_conversation_the_wire_named() -> None:
    provider = _Billing()
    user = SimpleNamespace(id=uuid.uuid4())
    with patch(f"{MODULE}.PROVIDERS", {"x": provider}):
        bill = await fetch_vendor_bill(_connectors(), user, _record("elevenlabs"), "conv_42")
    assert bill == BILL
    assert provider.asked == [("sk_test", "conv_42")]


async def test_no_conversation_no_billing_provider_or_a_vendor_failure_reads_as_no_bill() -> None:
    user = SimpleNamespace(id=uuid.uuid4())
    silent = SimpleNamespace(provider_id="gemini")  # states no bill: not a VendorBilling
    failing = _Billing(error=RuntimeError("vendor down"))
    with patch(f"{MODULE}.PROVIDERS", {"a": silent, "b": failing}):
        assert await fetch_vendor_bill(_connectors(), user, _record("elevenlabs"), None) is None
        assert await fetch_vendor_bill(_connectors(), user, _record("gemini"), "conv_1") is None
        assert await fetch_vendor_bill(_connectors(), user, _record("elevenlabs"), "conv_1") is None
    # The provider that stated no bill was never asked; the failing one was, once.
    assert failing.asked == [("sk_test", "conv_1")]


async def test_a_vendor_still_settling_the_conversation_is_asked_again_briefly() -> None:
    """Measured 2026-09-20 on the real API: the socket's close frame lands, the
    browser posts ``/end`` tens of milliseconds later, and the vendor still
    reads the conversation ``in-progress`` with no cost — while 0.3 s after
    the close handshake the bill is stated. Two sessions in a row showed
    NOTHING to the person. The seam asks again, bounded, sleeping between
    reads."""
    provider = _Billing(answers=[None, None, BILL])
    user = SimpleNamespace(id=uuid.uuid4())
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with (
        patch(f"{MODULE}.PROVIDERS", {"x": provider}),
        patch(f"{MODULE}.asyncio.sleep", _sleep),
    ):
        bill = await fetch_vendor_bill(_connectors(), user, _record("elevenlabs"), "conv_42")
    assert bill == BILL
    assert len(provider.asked) == 3
    assert sleeps == [LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS] * 2


async def test_a_vendor_that_never_states_the_bill_is_asked_a_bounded_number_of_times() -> None:
    provider = _Billing(answers=[])  # None on every read
    user = SimpleNamespace(id=uuid.uuid4())
    with (
        patch(f"{MODULE}.PROVIDERS", {"x": provider}),
        patch(f"{MODULE}.asyncio.sleep", AsyncMock()),
    ):
        bill = await fetch_vendor_bill(_connectors(), user, _record("elevenlabs"), "conv_42")
    assert bill is None
    assert len(provider.asked) == LIVE_VENDOR_BILL_SETTLE_ATTEMPTS


def test_the_bill_reaches_no_row_no_ledger_and_no_card() -> None:
    """The figure is the vendor's on the person's key: shown, recorded nowhere (directive 2026-09-16/19)."""
    import inspect

    from src.domains.agents.api import archive_metadata
    from src.infrastructure.scheduler import voice_session_closing

    assert "vendor_bill" not in inspect.getsource(archive_metadata)
    assert "vendor_bill" not in inspect.getsource(voice_session_closing)
    assert "vendor_bill" not in inspect.getsource(
        archive_metadata.build_live_session_summary_metadata
    )
