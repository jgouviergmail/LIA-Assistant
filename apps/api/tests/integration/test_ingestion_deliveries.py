"""Durable per-destination claims are fenced and never replay ambiguous sends."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from src.domains.ingestion.models import IngestionDelivery
from src.domains.sms.ingestion import SmsIngestionService
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def queued(db, user):
    actor = await authority(db, user)
    await SmsIngestionService(db).ingest(actor, [message()])
    return actor


async def test_lease_reclaim_before_sending_fences_the_previous_worker(db_session, test_user):
    from src.domains.ingestion.delivery_repository import claim_next, mark_sending, settle_delivery
    from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult

    await queued(db_session, test_user)
    now = datetime.now(UTC)
    old = await claim_next(db_session, uuid4(), now=now, lease_seconds=10)
    assert old is not None
    await db_session.commit()
    assert await claim_next(db_session, uuid4(), now=now, lease_seconds=10) is None
    new = await claim_next(db_session, uuid4(), now=now + timedelta(seconds=11), lease_seconds=10)
    assert new is not None and new.fence > old.fence
    assert not await mark_sending(db_session, old, now=now + timedelta(seconds=11))
    assert await mark_sending(db_session, new, now=now + timedelta(seconds=11))
    assert not await settle_delivery(
        db_session, old, DeliveryResult(DeliveryDisposition.ACCEPTED), now=now
    )
    assert await settle_delivery(
        db_session, new, DeliveryResult(DeliveryDisposition.ACCEPTED), now=now
    )
    assert (await db_session.scalar(select(IngestionDelivery))).state == "sent"


async def test_fanout_preserves_each_destination_and_success_is_never_retried(
    db_session, test_user
):
    from src.domains.ingestion.delivery_repository import (
        claim_next,
        expand_fanout,
        mark_sending,
        settle_delivery,
    )
    from src.domains.ingestion.delivery_types import (
        DeliveryDestination,
        DeliveryDisposition,
        DeliveryResult,
    )

    await queued(db_session, test_user)
    now = datetime.now(UTC)
    root = await claim_next(db_session, uuid4(), now=now)
    one, two = uuid4(), uuid4()
    assert await expand_fanout(
        db_session,
        root,
        (DeliveryDestination(f"device:{one}", one), DeliveryDestination(f"device:{two}", two)),
        now=now,
    )
    await db_session.commit()
    a = await claim_next(db_session, uuid4(), now=now)
    assert await mark_sending(db_session, a, now=now)
    assert await settle_delivery(
        db_session, a, DeliveryResult(DeliveryDisposition.ACCEPTED), now=now
    )
    b = await claim_next(db_session, uuid4(), now=now)
    assert b.id != a.id
    assert await mark_sending(db_session, b, now=now)
    assert await settle_delivery(
        db_session,
        b,
        DeliveryResult(
            DeliveryDisposition.RETRYABLE,
            error_code="TRANSPORT_UNAVAILABLE",
            retry_after_seconds=60,
        ),
        now=now,
    )
    await db_session.commit()
    retry = await claim_next(db_session, uuid4(), now=now + timedelta(seconds=61))
    assert retry.id == b.id and retry.id != a.id
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(IngestionDelivery)
            .where(IngestionDelivery.state == "sent")
        )
        == 1
    )


async def test_expired_send_is_terminal_unknown_and_never_automatically_retried(
    db_session, test_user
):
    from src.domains.ingestion.delivery_repository import (
        claim_next,
        mark_sending,
        recover_expired_send,
    )

    await queued(db_session, test_user)
    now = datetime.now(UTC)
    claim = await claim_next(db_session, uuid4(), now=now, lease_seconds=10)
    assert await mark_sending(db_session, claim, now=now)
    await db_session.commit()
    recovered = await recover_expired_send(db_session, now=now + timedelta(seconds=11))
    assert recovered is not None and recovered.id == claim.id
    await db_session.commit()
    assert (await db_session.scalar(select(IngestionDelivery))).state == "unknown"
    assert await claim_next(db_session, uuid4(), now=now + timedelta(days=1)) is None


async def test_sms_worker_does_not_claim_another_resource_queue(db_session, test_user):
    from src.domains.ingestion.delivery_repository import claim_next
    from src.domains.ingestion.models import IngestionSource

    await queued(db_session, test_user)
    source = await db_session.scalar(select(IngestionSource))
    source.resource = "health"
    await db_session.flush()
    assert await claim_next(db_session, uuid4(), now=datetime.now(UTC)) is None
