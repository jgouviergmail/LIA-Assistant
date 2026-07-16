"""Unit tests for the telephony reapers + GET /telephony/calls (P4.3)."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.reapers as rp
import src.domains.telephony.router as rt
from src.core.config import settings
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus


def _install_reaper_db(monkeypatch, repo_cls) -> dict:
    captured: dict = {}

    async def _commit() -> None:
        captured["committed"] = True

    @contextlib.asynccontextmanager
    async def _ctx():
        yield SimpleNamespace(commit=_commit)

    monkeypatch.setattr(rp, "TelephonyRepository", repo_cls)
    monkeypatch.setattr(rp, "get_db_context", _ctx)
    return captured


@pytest.mark.unit
async def test_stale_reaper_uses_settings_threshold(monkeypatch) -> None:
    captured: dict = {}

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def recover_stale(self, timeout_minutes: int) -> int:
            captured["timeout"] = timeout_minutes
            return 2

    db_captured = _install_reaper_db(monkeypatch, _FakeRepo)
    await rp.telephony_stale_call_reaper()

    # Read the threshold from settings — never hard-code it.
    assert captured["timeout"] == settings.telephony_stale_call_timeout_minutes
    assert db_captured["committed"] is True


@pytest.mark.unit
async def test_retention_reaper_purges_and_commits(monkeypatch) -> None:
    captured: dict = {}

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def purge_expired(self) -> int:
            captured["purged"] = True
            return 3

    db_captured = _install_reaper_db(monkeypatch, _FakeRepo)
    await rp.telephony_retention_reaper()

    assert captured["purged"] is True
    assert db_captured["committed"] is True


def _install_notification_reaper(monkeypatch, *, pending, user, dispatch_error=None) -> dict:
    """Wire the notification reaper's collaborators to in-memory fakes.

    Returns a dict recording the dispatched target_ids and the delivered/failed
    call_ids so a test can assert the recovery outcome.
    """
    actions: dict = {"dispatched": [], "delivered": [], "failed": []}

    class _Repo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def fetch_recoverable_notifications(
            self, *, cutoff, max_attempts, limit
        ):  # noqa: ANN001
            return list(pending)

        async def mark_notification_delivered(self, call_id) -> None:  # noqa: ANN001
            actions["delivered"].append(call_id)

        async def record_notification_failure(
            self, call_id, *, max_attempts
        ) -> None:  # noqa: ANN001
            actions["failed"].append(call_id)

    class _Dispatcher:
        async def dispatch(self, **kwargs):
            if dispatch_error is not None:
                raise dispatch_error
            actions["dispatched"].append(kwargs["target_id"])
            return None

    @contextlib.asynccontextmanager
    async def _ctx():
        async def _get(_model, _ident):
            return user

        async def _commit() -> None:
            return None

        yield SimpleNamespace(get=_get, commit=_commit)

    monkeypatch.setattr(rp, "TelephonyRepository", _Repo)
    monkeypatch.setattr(rp, "get_db_context", _ctx)
    monkeypatch.setattr(
        "src.infrastructure.proactive.notification.NotificationDispatcher", _Dispatcher
    )
    return actions


def _pending_call(call_id=None, user_id=None):
    return SimpleNamespace(
        id=call_id or uuid4(),
        user_id=user_id or uuid4(),
        notification_payload={"content": "She is free Tuesday.", "title": "Call back"},
        status=SimpleNamespace(value="completed"),
    )


@pytest.mark.unit
async def test_notification_reaper_recovers_pending(monkeypatch) -> None:
    """A PENDING return left by a crash is re-dispatched then marked delivered (T1)."""
    call = _pending_call()
    user = SimpleNamespace(id=call.user_id, language="fr")
    actions = _install_notification_reaper(monkeypatch, pending=[call], user=user)

    await rp.telephony_notification_reaper()

    assert actions["dispatched"] == [str(call.id)]
    assert actions["delivered"] == [call.id]
    assert actions["failed"] == []


@pytest.mark.unit
async def test_notification_reaper_transient_failure_is_bounded(monkeypatch) -> None:
    """A dispatch failure records a bounded failure and does NOT mark delivered."""
    call = _pending_call()
    user = SimpleNamespace(id=call.user_id, language="fr")
    actions = _install_notification_reaper(
        monkeypatch, pending=[call], user=user, dispatch_error=RuntimeError("boom")
    )

    await rp.telephony_notification_reaper()

    assert actions["dispatched"] == []
    assert actions["delivered"] == []
    assert actions["failed"] == [call.id]


@pytest.mark.unit
async def test_notification_reaper_skips_when_user_gone(monkeypatch) -> None:
    """A recipient-less row is closed (delivered) so the reaper stops chasing it."""
    call = _pending_call()
    actions = _install_notification_reaper(monkeypatch, pending=[call], user=None)

    await rp.telephony_notification_reaper()

    assert actions["dispatched"] == []
    assert actions["delivered"] == [call.id]  # closed without a dispatch


@pytest.mark.unit
async def test_notification_reaper_noop_when_nothing_pending(monkeypatch) -> None:
    actions = _install_notification_reaper(monkeypatch, pending=[], user=None)
    await rp.telephony_notification_reaper()
    assert actions == {"dispatched": [], "delivered": [], "failed": []}


@pytest.mark.unit
async def test_list_calls_omits_encrypted_phone(monkeypatch) -> None:
    call = SimpleNamespace(
        id=uuid4(),
        callee_display="Marie",
        objective="ask availability",
        status=PhoneCallStatus.COMPLETED,
        outcome=PhoneCallOutcome.OBJECTIVE_MET,
        summary="She is free Tuesday.",
        call_seconds=Decimal("42.5"),
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        callee_phone="ENCRYPTED_SECRET_BLOB",  # must NEVER surface
    )

    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def list_recent_for_user(self, _user_id, limit: int = 20):
            return [call]

    monkeypatch.setattr(rt, "TelephonyRepository", _FakeRepo)

    result = await rt.list_calls(user=SimpleNamespace(id=uuid4()), db=None, limit=20)

    assert len(result) == 1
    dumped = result[0].model_dump(mode="json")
    assert dumped["callee_display"] == "Marie"
    assert dumped["status"] == "completed"
    assert dumped["outcome"] == "objective_met"
    assert dumped["call_seconds"] == 42.5
    # The encrypted phone is not a field on the summary — it can never leak.
    assert "callee_phone" not in dumped
    assert "ENCRYPTED_SECRET_BLOB" not in str(dumped)
