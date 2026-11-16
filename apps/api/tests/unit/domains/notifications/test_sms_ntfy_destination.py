"""An ingested message reaches ntfy as one more destination of its durable outbox (ADR-391).

The outbox retries what it may and never what it must not: ntfy's own verdict decides. Accepted
by a server is delivered; nothing to publish to is cancelled; a refusal before anything left may
be retried; a publication that left unanswered is unknown, never repeated.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult
from src.domains.notifications.ntfy_delivery import NtfyBatch, NtfyTargetsUnreadable
from src.infrastructure.external.ntfy_client import NtfyOutcome
from src.infrastructure.scheduler import ingestion_transport
from src.infrastructure.scheduler.ingestion_delivery import DeliveryEnvelope
from src.infrastructure.scheduler.ingestion_transport import IngestionTransport

pytestmark = pytest.mark.unit


def _envelope() -> DeliveryEnvelope:
    return DeliveryEnvelope(
        user_id=uuid4(),
        message_id=uuid4(),
        occurrence=uuid4(),
        destination_key="ntfy",
        device_id=None,
        title="Generic",
        body="Generic",
        language="fr",
    )


@pytest.mark.parametrize(
    ("outcomes", "retry_after", "disposition"),
    [
        ((NtfyOutcome.SENT,), None, DeliveryDisposition.ACCEPTED),
        ((NtfyOutcome.SENT, NtfyOutcome.SERVER_ERROR), None, DeliveryDisposition.ACCEPTED),
        ((), None, DeliveryDisposition.CANCELLED),
        ((NtfyOutcome.RATE_LIMITED,), 30, DeliveryDisposition.RETRYABLE),
        ((NtfyOutcome.UNREACHABLE,), None, DeliveryDisposition.RETRYABLE),
        ((NtfyOutcome.UNREACHABLE, NtfyOutcome.NO_ANSWER), None, DeliveryDisposition.UNKNOWN),
        ((NtfyOutcome.AUTH_REFUSED,), None, DeliveryDisposition.PERMANENT),
    ],
)
async def test_ntfy_s_verdict_decides_the_destination_s_fate(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: tuple[NtfyOutcome, ...],
    retry_after: int | None,
    disposition: DeliveryDisposition,
) -> None:
    door = AsyncMock(return_value=NtfyBatch(outcomes=outcomes, retry_after_seconds=retry_after))
    monkeypatch.setattr(ingestion_transport, "push_to_ntfy", door)

    result = await IngestionTransport().send(_envelope())

    assert result.disposition is disposition
    if disposition is DeliveryDisposition.RETRYABLE:
        # The server's own delay when it states one, the outbox's default otherwise.
        assert result.retry_after_seconds == (
            retry_after or DeliveryResult(disposition).retry_after_seconds
        )
        assert isinstance(result.retry_after_seconds, int)


async def test_subscriptions_that_could_not_be_read_are_tried_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing left: neither « nobody subscribed » (cancelled) nor « unknown » (never retried)."""
    door = AsyncMock(side_effect=NtfyTargetsUnreadable())
    monkeypatch.setattr(ingestion_transport, "push_to_ntfy", door)

    result = await IngestionTransport().send(_envelope())

    assert (result.disposition, result.error_code) == (
        DeliveryDisposition.RETRYABLE,
        "TRANSPORT_UNAVAILABLE",
    )


async def test_it_carries_the_generic_notice_and_opens_the_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    door = AsyncMock(return_value=NtfyBatch(outcomes=(NtfyOutcome.SENT,)))
    monkeypatch.setattr(ingestion_transport, "push_to_ntfy", door)
    envelope = _envelope()

    await IngestionTransport().send(envelope)

    assert door.await_args_list[-1].args == (envelope.user_id,)
    kwargs = door.await_args_list[-1].kwargs
    assert (kwargs["title"], kwargs["body"]) == ("Generic", "Generic")
    assert kwargs["click_path"] == f"/fr/dashboard/sms?message={envelope.message_id}"
