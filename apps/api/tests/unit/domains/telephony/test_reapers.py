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
