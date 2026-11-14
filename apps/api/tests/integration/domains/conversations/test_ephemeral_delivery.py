"""Only the owning invocation may queue cards; every exit retires its local payloads."""

import asyncio
from uuid import uuid4

import pytest

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.domains.agents.tools.browser_screenshot_store import (
    get_and_clear_last_screenshot,
    store_last_browser_screenshot,
)
from src.domains.shared.pending_cards import PendingCards
from src.infrastructure.streaming.run_admission import owned_execution, reserve_execution

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("ending", ["completed", "failed", "cancelled"])
async def test_every_exit_discards_only_its_own_delivery_payloads(
    reserved: RunAdmission, ending: str
) -> None:
    runtime, other = str(reserved.target.runtime_id), str(uuid4())
    cards: PendingCards[str] = PendingCards("delivery-test")
    cards.add(other, "another discussion")
    store_last_browser_screenshot(other, b"other")
    try:
        try:
            async with owned_execution(reserved):
                cards.add(runtime, "generated file card")
                store_last_browser_screenshot(runtime, b"screenshot")
                if ending == "failed":
                    raise OSError("lost transport")
                if ending == "cancelled":
                    raise asyncio.CancelledError()
        except OSError:
            assert ending == "failed"
        except asyncio.CancelledError:
            assert ending == "cancelled"

        assert cards.peek(runtime) == []
        assert get_and_clear_last_screenshot(runtime) is None
        assert cards.peek(other) == ["another discussion"]
        assert get_and_clear_last_screenshot(other) == b"other"
    finally:
        cards.clear()
        get_and_clear_last_screenshot(runtime)
        get_and_clear_last_screenshot(other)


@pytest.mark.parametrize("family", ["card", "screenshot"])
@pytest.mark.parametrize("refusal", ["revoked", "other_runtime"])
async def test_revoked_or_misdirected_writer_cannot_queue_late_payloads(
    reserved: RunAdmission, family: str, refusal: str
) -> None:
    runtime = str(reserved.target.runtime_id if refusal == "revoked" else uuid4())
    cards: PendingCards[str] = PendingCards("delivery-test")
    try:
        async with owned_execution(reserved) as authority:
            authority.revoked = refusal == "revoked"
            with pytest.raises(ExecutionRevoked):
                if family == "card":
                    cards.add(runtime, "late card")
                else:
                    store_last_browser_screenshot(runtime, b"late image")
    finally:
        cards.clear()
        get_and_clear_last_screenshot(runtime)


async def test_nested_borrower_does_not_discard_the_owners_cards(reserved: RunAdmission) -> None:
    runtime = str(reserved.target.runtime_id)
    cards: PendingCards[str] = PendingCards("delivery-test")
    async with owned_execution(reserved):
        async with owned_execution(reserved):
            cards.add(runtime, "keep until the answer archives it")
        assert cards.peek(runtime) == ["keep until the answer archives it"]
    assert cards.peek(runtime) == []


async def test_retried_old_closure_never_discards_the_successors_payloads(
    reserved: RunAdmission,
) -> None:
    runtime = str(reserved.target.runtime_id)
    cards: PendingCards[str] = PendingCards("delivery-test")
    async with owned_execution(reserved) as previous:
        cards.add(runtime, "previous answer")
    next_admission = await reserve_execution(
        reserved.target, run_id=str(uuid4()), stream_id=str(uuid4()), relayed=False
    )
    assert isinstance(next_admission, RunAdmission)
    async with owned_execution(next_admission):
        cards.add(runtime, "current answer")
        previous.clear_payloads()
        assert cards.peek(runtime) == ["current answer"]
    assert cards.peek(runtime) == []
