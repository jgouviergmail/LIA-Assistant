"""Paid background work never sends through a confirmed opt-out."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.llm_usage import LLMBillingRecord
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
from src.domains.users.models import User
from src.infrastructure.proactive.base import ProactiveTaskResult
from src.infrastructure.proactive.notification import NotificationResult
from src.infrastructure.proactive.runner import ProactiveTaskRunner, RunnerStats

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def stable_delivery_time(monkeypatch: pytest.MonkeyPatch) -> Mock:
    from src.domains.heartbeat import delivery_guard

    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 10, 7, 12, tzinfo=UTC)
    monkeypatch.setattr(delivery_guard, "datetime", clock, raising=False)
    return clock


@pytest.mark.parametrize("hour,expected", [(23, True), (5, True), (6, False), (12, False)])
async def test_publication_rechecks_the_local_overnight_window(
    monkeypatch: pytest.MonkeyPatch, stable_delivery_time: Mock, hour: int, expected: bool
) -> None:
    from src.domains.heartbeat import delivery_guard

    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    stable_delivery_time.now.return_value = datetime(2026, 10, 7, hour, tzinfo=UTC)
    current = actor(uuid4(), True)
    current.heartbeat_notify_start_hour, current.heartbeat_notify_end_hour = 22, 6
    db = authority_db()
    db.scalar.side_effect = [None, current, None]

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    assert (await delivery_guard.heartbeat_delivery_stamp(current.id) is not None) is expected


def actor(actor_id: UUID, enabled: bool) -> User:
    return User(
        id=actor_id,
        is_active=True,
        deleted_at=None,
        language="fr",
        timezone="UTC",
        heartbeat_enabled=enabled,
        heartbeat_notify_start_hour=0,
        heartbeat_notify_end_hour=23,
        heartbeat_disabled_sources=None,
        moment_kinds_disabled=None,
        extraction_revision=0,
    )


def authority_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = Mock(all=Mock(return_value=[]))
    return db


def record(tokens: int) -> LLMBillingRecord:
    return LLMBillingRecord(
        model_name="test-model",
        started_at=1.0,
        tokens_in=tokens,
        tokens_out=2,
        tokens_cache=0,
        cost_usd=0.1,
        cost_eur=0.09,
        usd_to_eur_rate=0.9,
    )


@pytest.mark.parametrize("change_after", ["selection", "generation", "none"])
async def test_opt_out_during_paid_work_suppresses_delivery_and_preserves_billing(
    monkeypatch: pytest.MonkeyPatch, change_after: str
) -> None:
    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    actor_id = uuid4()
    original = actor(actor_id, True)
    current = actor(actor_id, change_after == "none")
    db = authority_db()
    db.scalar.side_effect = (
        [None, original, None, None, current, None]
        if change_after == "selection"
        else [None, original, None, None, original, None, None, current, None]
    )

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", sessions)
    decision_record, generation_record = record(10), record(20)
    target = HeartbeatTarget(
        context=HeartbeatContext(),
        decision=HeartbeatDecision(action="notify", reason="Useful", message_draft="Draft"),
        decision_tokens_in=10,
        decision_tokens_out=2,
        billing_records=(decision_record,),
    )
    content = ProactiveTaskResult(
        success=True,
        content="Prepared notification",
        tokens_in=30,
        tokens_out=4,
        billing_records=(decision_record, generation_record),
        target_id=str(uuid4()),
    )
    task = Mock()
    task.task_type = "heartbeat"
    task.select_target = AsyncMock(return_value=target)
    task.generate_content = AsyncMock(return_value=content)
    task.on_notification_sent = AsyncMock()
    runner = ProactiveTaskRunner(task=task)
    dispatch = AsyncMock(return_value=NotificationResult(success=True))
    bill = AsyncMock(return_value="run")
    monkeypatch.setattr(runner, "_dispatch_and_settle_on_failure", dispatch)
    monkeypatch.setattr(runner, "_bill", bill)
    monkeypatch.setattr(runner, "_stamp_cost_metadata", Mock(return_value=0.18))
    stats = RunnerStats()
    sent = change_after == "none"
    assert await runner._serve_user(original, AsyncMock(spec=AsyncSession), stats, "run") is sent
    assert dispatch.await_count == int(sent)
    assert task.on_notification_sent.await_count == int(sent)
    bill.assert_awaited_once()
    call = bill.await_args
    assert call is not None and call.kwargs["failed"] is (not sent)
    expected = (decision_record,) if change_after == "selection" else content.billing_records
    assert call.args[1].billing_records == expected
    assert stats.skip_reasons == ({} if sent else {"settings_changed": 1})
    if change_after == "selection":
        task.generate_content.assert_not_awaited()


@pytest.mark.parametrize(
    "fault", ["missing", "inactive", "deleted", "foreign", "off", "operator", "outage"]
)
async def test_current_delivery_authority_is_closed_on_missing_rights_or_read_failure(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from src.domains.heartbeat import delivery_guard

    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    actor_id = uuid4()
    current = actor(actor_id, fault != "off")
    if fault == "inactive":
        current.is_active = False
    if fault == "deleted":
        current.deleted_at = datetime.now(UTC)
    if fault == "foreign":
        current.id = uuid4()
    db = authority_db()
    db.scalar.side_effect = [
        "false" if fault == "operator" else None,
        None if fault == "missing" else current,
    ]
    if fault == "outage":
        db.scalar.side_effect = OperationalError(
            "private connection", {}, RuntimeError("private secret")
        )

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", sessions)
    log = Mock()
    monkeypatch.setattr(delivery_guard, "logger", log)
    assert await delivery_guard.heartbeat_delivery_stamp(actor_id) is None
    assert "private connection" not in str(log.mock_calls)
    assert "private secret" not in str(log.mock_calls)


@pytest.mark.parametrize(
    "field",
    [
        "heartbeat_disabled_sources",
        "heartbeat_notify_end_hour",
        "extraction_revision",
        "home_location_encrypted",
        "sms_preferences",
    ],
)
async def test_scope_changes_invalidate_prepared_content_without_returning_private_data(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    from src.domains.heartbeat.delivery_guard import heartbeat_delivery_stamp

    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    actor_id = uuid4()
    initial, changed = actor(actor_id, True), actor(actor_id, True)
    changes = {
        "heartbeat_disabled_sources": ["calendar"],
        "heartbeat_notify_end_hour": 20,
        "extraction_revision": 1,
        "home_location_encrypted": "private ciphertext",
        "sms_preferences": {"assistant_enabled": False},
    }
    setattr(changed, field, changes[field])
    db = authority_db()
    db.scalar.side_effect = [None, initial, None, None, changed, None]

    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", sessions)
    first = await heartbeat_delivery_stamp(actor_id)
    second = await heartbeat_delivery_stamp(actor_id)
    assert first is not None and second is not None and first != second
    assert len(first) == len(second) == 64
    assert "private ciphertext" not in second


async def test_connector_authority_changes_fence_paid_content_but_refreshing_tokens_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.connectors.models import ConnectorStatus, ConnectorType
    from src.domains.heartbeat import delivery_guard

    monkeypatch.setattr(settings, "heartbeat_enabled", True)
    current = actor(uuid4(), True)
    db = authority_db()
    db.scalar.side_effect = [None, current, None] * 3
    connector_id = uuid4()
    active = (connector_id, ConnectorType.GOOGLE_GMAIL, ConnectorStatus.ACTIVE, None, ["read"])
    revoked = (connector_id, ConnectorType.GOOGLE_GMAIL, ConnectorStatus.REVOKED, None, ["read"])
    rows = [Mock(all=Mock(return_value=[row])) for row in (active, active, revoked)]
    db.execute.side_effect = rows

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield db

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    first, refreshed, rejected = [
        await delivery_guard.heartbeat_delivery_stamp(current.id) for _ in range(3)
    ]
    assert first is not None
    assert refreshed == first
    assert rejected != first
    for call in db.execute.await_args_list:
        columns = {column.key for column in call.args[0].selected_columns}
        assert columns == {"id", "connector_type", "status", "preferences_encrypted", "scopes"}
