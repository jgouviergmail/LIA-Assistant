"""One synthetic message crosses the actual SQL surfaces; external IO stays fake."""

import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.account_export import builder
from src.domains.account_export.models import AccountExportJob
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.sms_card import SmsCard
from src.domains.agents.sms.read_service import SmsToolReader
from src.domains.agents.sms.schemas import SmsListRequest
from src.domains.agents.tools.sms_tools import sms_output
from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
from src.domains.heartbeat.sms_context import fetch_sms_context, sms_decision_allowed
from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult
from src.domains.notifications.models import UserFCMToken
from src.domains.sms.facade import SmsFacade
from src.domains.sms.identity import ContactIdentity, IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.read_schemas import SmsQuery
from src.domains.sms.relation_reader import SmsRelationReader
from src.domains.sms.summary import read_sms_summary, sms_signal_current
from src.domains.users.models import User
from src.infrastructure.proactive.notification import NotificationDispatcher
from src.infrastructure.proactive.runner import ProactiveTaskRunner
from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_delivery_worker import sessions
from tests.integration.test_sms_ingestion import authority, message
from tests.integration.test_sms_relations import sms_actor_session as sms_actor_session

pytestmark = pytest.mark.integration


async def test_one_source_has_consistent_archive_tools_relations_home_delivery_and_export(
    sms_actor_session, async_engine, tmp_path, monkeypatch
):
    db, user = sms_actor_session
    user.sms_preferences = {"assistant_enabled": True}
    user.timezone = "Europe/Paris"
    device = UserFCMToken(
        user_id=user.id,
        token=f"synthetic:{uuid4()}",
        device_type="web",
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db.add(device)
    await db.commit()
    principal = await authority(db, user)
    entries = [
        message(sender="+33612345678", body="Rendez-vous à 10h30. <script>untrusted()</script>"),
        message(sender="SyntheticBank", body="Votre code de connexion est 123456"),
    ]
    ingest_started = perf_counter()
    first = await SmsIngestionService(db).ingest(principal, entries)
    acknowledged_at = perf_counter()
    acknowledgement_seconds = acknowledged_at - ingest_started
    retry = await SmsIngestionService(db).ingest(principal, entries)
    assert (first.inserted, first.ignored, retry.duplicate) == (1, 1, 2)
    book = IdentityBook(
        contacts=(ContactIdentity("Alice", numbers=("+33612345678",)),), complete=True
    )
    monkeypatch.setattr(
        "src.domains.sms.identity_resolution.load_identity_book", AsyncMock(return_value=book)
    )
    monkeypatch.setattr(
        "src.domains.sms.identity_resolution.load_relation_book", AsyncMock(return_value=book)
    )
    archive = await SmsFacade(db).list(user.id, SmsQuery(limit=2), assistant=False)
    assert archive.total == 1 and archive.items[0].display_name == "Alice"
    await db.commit()
    tool = await SmsToolReader(db).list(user.id, SmsListRequest(limit=1))
    assert tool.total == 1 and "10h30" in str(sms_output(tool, "list_sms_tool"))
    html = SmsCard().render(
        tool.sms_messages[0].model_dump(mode="json"),
        RenderContext(language="fr", timezone="Europe/Paris"),
    )
    assert "&lt;script&gt;" in html and "<script>" not in html
    await db.commit()
    relation = await SmsRelationReader().read(user.id, person="Alice", limit=2, assistant=False)
    home = await read_sms_summary(user.id)
    assert relation.total == home.total == home.window_total == 1

    notices = []
    delivered_after_ack_ms = []

    class Transport:
        async def send(self, envelope):
            async with AsyncSession(async_engine) as separate:
                await separate.execute(text("SET LOCAL lock_timeout='150ms'"))
                await separate.scalar(select(User.id).where(User.id == user.id).with_for_update())
            assert "10h30" not in envelope.body and "Alice" not in envelope.title
            notices.append(envelope.destination_key)
            delivered_after_ack_ms.append(round((perf_counter() - acknowledged_at) * 1000, 3))
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    worker_started = perf_counter()
    await worker.run_once(limit=10)
    worker_seconds = perf_counter() - worker_started
    await worker.run_once(limit=10)
    assert set(notices) == {"sse", f"device:{device.id}"} and len(notices) == 2

    source = await fetch_sms_context(user.id, user, settings)
    assert source is not None and len(source.messages) == 1
    decision = HeartbeatDecision(
        action="notify",
        reason="Concrete appointment",
        message_draft="Le rendez-vous d’Alice est à 10h30.",
        sources_used=["SMS"],
        sms_actionable=True,
        sms_message_ids=[source.messages[0].id],
    )
    context = HeartbeatContext(sms=source)
    assert sms_decision_allowed(context, decision)
    target = HeartbeatTarget(
        context=context,
        decision=decision,
        decision_tokens_in=1,
        decision_tokens_out=1,
        decision_tokens_cache=0,
    )
    task = HeartbeatProactiveTask()
    monkeypatch.setattr(task, "_get_user_personality", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
        AsyncMock(return_value=("Le rendez-vous d’Alice est à 10h30.", 11, 7, 0, 0, ())),
    )
    result = await task.generate_content(user.id, target, "fr")
    assert result.success
    assert (result.tokens_in, result.tokens_out) == (12, 8)
    dispatch = NotificationDispatcher(
        fcm_enabled=True, sse_enabled=True, archive_enabled=True, channel_enabled=True
    )
    dispatch._archive_message = AsyncMock(return_value={"archived": True})
    dispatch._send_fcm = AsyncMock(return_value={"success": 1})
    dispatch._publish_sse = AsyncMock()
    dispatch._send_channels = AsyncMock(return_value=1)
    # The runner's own door to the dispatcher. An SMS in view is personal data like
    # a mail (ADR-357 amendment 2026-10-23): the push carries the words and the
    # external channels receive them, as for a notification drawn from a mail.
    sent = await ProactiveTaskRunner(task, dispatcher=dispatch)._dispatch_notification(
        user, result, target, db
    )
    assert sent.durably_delivered and "10h30" in dispatch._send_fcm.await_args.kwargs["body"]
    dispatch._send_channels.assert_awaited_once()
    await task.on_notification_sent(user.id, target, result)
    assert await fetch_sms_context(user.id, user, settings) is None
    assert not await sms_signal_current(source)

    job = AccountExportJob(user_id=user.id, status="running")
    db.add(job)
    await db.commit()
    monkeypatch.setattr(builder.settings, "exports_storage_path", str(tmp_path))
    archive_path, _ = await builder.build_export_archive(user.id, job.id)
    with zipfile.ZipFile(archive_path) as zipped:
        rows = json.loads(zipped.read("data/sms_messages.json"))
        assert len(rows) == 1 and rows[0]["proactive_mentioned_at"] is not None
        assert entries[1]["body"] not in zipped.read("readable/sms_messages.md").decode()
        assert "10h30" in zipped.read("readable/sms_messages.md").decode()
        assert "ingestion_key_encrypted" not in zipped.read("profile.json").decode()

    report = {
        "accepted": first.inserted,
        "excluded": first.ignored,
        "service_commit_ack_ms": round(acknowledgement_seconds * 1000, 3),
        "explicit_worker_tick_ms": round(worker_seconds * 1000, 3),
        "fake_delivery_after_ack_ms": delivered_after_ack_ms,
    }
    destination = (
        Path(__file__).resolve().parents[4]
        / ".tmp/sms-implementation/cross-surface-qualification.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
