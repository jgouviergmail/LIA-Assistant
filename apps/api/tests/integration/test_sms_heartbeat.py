"""Real SQL selection, bounded identity projection and successful-delivery bookkeeping."""

from uuid import uuid4

import pytest
from sqlalchemy import select

from src.core.exceptions import AuthorizationError
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from src.domains.sms.summary import read_sms_signal
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message
from tests.integration.test_sms_relations import sms_actor_session as sms_actor_session

pytestmark = pytest.mark.integration


async def test_only_chosen_delivered_sms_are_consumed_and_no_other_owner_can_be_marked(
    sms_actor_session,
):
    from src.domains.sms.proactive import mark_sms_mentioned

    db, user = sms_actor_session
    actor = await authority(db, user)
    user.sms_preferences = {"assistant_enabled": True}
    await db.commit()
    await SmsIngestionService(db).ingest(
        actor, [message(body=f"Appointment {i}") for i in range(4)]
    )
    original = await read_sms_signal(user.id, unmentioned_only=True)
    assert len(original.messages) == 3
    chosen = original.messages[0].id
    await mark_sms_mentioned(db, original, [chosen, uuid4()])
    await db.commit()
    assert (
        await db.scalar(select(SmsMessage).where(SmsMessage.id == chosen))
    ).proactive_mentioned_at is not None
    await db.commit()
    remaining = await read_sms_signal(user.id, unmentioned_only=True)
    assert len(remaining.messages) == 3 and chosen not in {item.id for item in remaining.messages}
    await mark_sms_mentioned(db, remaining, [item.id for item in remaining.messages])
    await db.commit()
    assert not (await read_sms_signal(user.id, unmentioned_only=True)).messages


async def test_withdrawal_before_successful_delivery_cannot_write_a_mention(sms_actor_session):
    from src.domains.sms.proactive import mark_sms_mentioned

    db, user = sms_actor_session
    actor = await authority(db, user)
    user.sms_preferences = {"assistant_enabled": True}
    await db.commit()
    await SmsIngestionService(db).ingest(actor, [message(body="Private appointment")])
    original = await read_sms_signal(user.id, unmentioned_only=True)
    user.sms_preferences = {"assistant_enabled": False}
    await db.commit()
    with pytest.raises(AuthorizationError):
        await mark_sms_mentioned(db, original, [original.messages[0].id])
    await db.rollback()
    row = await db.scalar(select(SmsMessage).where(SmsMessage.id == original.messages[0].id))
    assert row.proactive_mentioned_at is None


@pytest.mark.parametrize("private_result", [True, False])
async def test_private_proactive_audit_never_reenters_memory_or_later_decisions(
    sms_actor_session, monkeypatch, private_result
):
    from unittest.mock import AsyncMock

    from src.core.notification_privacy import NotificationPrivacy
    from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
    from src.domains.heartbeat.repository import HeartbeatNotificationRepository
    from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
    from src.infrastructure.proactive.base import ProactiveTaskResult

    db, user = sms_actor_session
    actor = await authority(db, user)
    user.sms_preferences = {"assistant_enabled": True}
    await db.commit()
    await SmsIngestionService(db).ingest(actor, [message(body="Private appointment")])
    source = await read_sms_signal(user.id, unmentioned_only=True)
    target = HeartbeatTarget(
        context=HeartbeatContext(sms=source),
        decision=HeartbeatDecision(
            action="notify",
            reason="Concrete appointment",
            message_draft="Private appointment",
            sources_used=["SMS"],
            sms_actionable=True,
            sms_message_ids=[source.messages[0].id],
        ),
        decision_tokens_in=1,
        decision_tokens_out=1,
        decision_tokens_cache=0,
    )
    result = ProactiveTaskResult(
        success=True,
        content="Private appointment",
        target_id=str(uuid4()),
        privacy=(
            NotificationPrivacy.IN_APP_SENSITIVE if private_result else NotificationPrivacy.NORMAL
        ),
        metadata={"sources_used": ["SMS"]},
    )
    sink = AsyncMock()
    monkeypatch.setattr("src.infrastructure.proactive.context_sink.write_heartbeat_context", sink)
    await HeartbeatProactiveTask().on_notification_sent(user.id, target, result)
    sink.assert_not_awaited()
    repo = HeartbeatNotificationRepository(db)
    rows = await repo.get_recent_by_user(user.id)
    assert len(rows) == 1 and rows[0].sensitive_context is True
    assert await repo.get_recent_by_user(user.id, for_context=True) == []
