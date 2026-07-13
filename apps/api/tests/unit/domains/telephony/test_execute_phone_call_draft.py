"""Unit tests for execute_phone_call_draft (P3.4), with initiate_call mocked."""

from __future__ import annotations

import contextlib
from uuid import uuid4

import pytest

import src.domains.agents.tools.telephony_tools as tt
from src.core.i18n_drafts import get_draft_success_message
from src.domains.telephony.service import InitiateCallResult, TelephonyExecutionError

_DRAFT = {
    "callee_name": "Marie",
    "callee_phone": "+33612345678",
    "objective": "Lui demander si elle est libre mardi",
    "date_window": None,
    "user_language": "fr",
}


def _patch(monkeypatch: pytest.MonkeyPatch, result: InitiateCallResult) -> None:
    @contextlib.asynccontextmanager
    async def _ctx():
        yield object()

    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", _ctx)

    class _FakeService:
        def __init__(self, db, **kwargs) -> None:  # noqa: ANN001
            pass

        async def initiate_call(self, **kwargs) -> InitiateCallResult:
            return result

    monkeypatch.setattr("src.domains.telephony.service.TelephonyService", _FakeService)


@pytest.mark.unit
async def test_placed_returns_name_and_call_id(monkeypatch: pytest.MonkeyPatch) -> None:
    call_id = uuid4()
    _patch(monkeypatch, InitiateCallResult(status="placed", call_id=call_id))
    out = await tt.execute_phone_call_draft(_DRAFT, uuid4(), None)
    assert out["success"] is True
    assert out["name"] == "Marie"  # drives the async phone_call success template
    assert out["call_id"] == str(call_id)


@pytest.mark.unit
async def test_already_active_raises_friendly_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, InitiateCallResult(status="already_active", call_id=uuid4()))
    with pytest.raises(TelephonyExecutionError) as excinfo:
        await tt.execute_phone_call_draft(_DRAFT, uuid4(), None)
    assert "déjà en cours" in str(excinfo.value)


@pytest.mark.unit
async def test_not_configured_raises_activation_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, InitiateCallResult(status="not_configured"))
    with pytest.raises(TelephonyExecutionError) as excinfo:
        await tt.execute_phone_call_draft(_DRAFT, uuid4(), None)
    assert "connecteur" in str(excinfo.value).lower()


@pytest.mark.unit
async def test_failed_raises_retry_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, InitiateCallResult(status="failed"))
    with pytest.raises(TelephonyExecutionError) as excinfo:
        await tt.execute_phone_call_draft(_DRAFT, uuid4(), None)
    assert "réessaie" in str(excinfo.value).lower()


@pytest.mark.unit
def test_phone_call_executor_is_registered() -> None:
    """The PHONE_CALL draft type resolves to execute_phone_call_draft (wiring guard)."""
    from src.domains.agents.drafts.models import DraftType
    from src.domains.agents.services.draft_executor import (
        _EXECUTOR_REGISTRY as registry,
    )
    from src.domains.agents.services.draft_executor import (
        _ensure_executors_registered,
    )

    _ensure_executors_registered()
    assert DraftType.PHONE_CALL.value in registry


@pytest.mark.unit
def test_success_message_is_async_not_past_tense() -> None:
    """The phone_call success message frames an in-progress call, not a completed one."""
    msg = get_draft_success_message("phone_call", "fr", name="Marie")
    assert "Marie" in msg
    assert "appelle" in msg.lower()  # present/ongoing
    assert "passé" not in msg.lower()  # NOT the generic past-participle template
    # English variant also present-tense.
    assert "calling" in get_draft_success_message("phone_call", "en", name="Marie").lower()
