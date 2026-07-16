"""Unit tests for the telephony webhook endpoint routing (P4.1)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import src.domains.telephony.router as rt
from src.domains.telephony.webhook_handler import WebhookAuth, WebhookOutcome


class _FakeRequest:
    def __init__(self, body: bytes = b"{}", headers: dict | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def body(self) -> bytes:
        return self._body


def _patch_auth(monkeypatch, auth: WebhookAuth) -> dict:
    fired: dict = {}

    async def _auth(*_args, **_kwargs) -> WebhookAuth:
        return auth

    def _fire(coro, name=None):  # noqa: ANN001
        fired["name"] = name
        coro.close()  # close the unawaited coroutine (no event loop scheduling in the test)
        return None

    async def _pcc(_call_id, _payload) -> None:
        return None

    monkeypatch.setattr(rt, "authenticate_and_reconcile", _auth)
    monkeypatch.setattr(rt, "safe_fire_and_forget", _fire)
    monkeypatch.setattr("src.domains.telephony.return_synthesis.process_completed_call", _pcc)
    return fired


@pytest.mark.unit
async def test_webhook_ok_fires_background_task(monkeypatch) -> None:
    call = SimpleNamespace(id=uuid4())
    auth = WebhookAuth(WebhookOutcome.OK, call=call, payload={"x": 1})
    fired = _patch_auth(monkeypatch, auth)

    # OK outcome now durably persists the encrypted return inbox (T1 approach A)
    # BEFORE firing the background synthesis, so the handler touches the DB —
    # give it an async session mock (execute/commit).
    resp = await rt.telephony_webhook(_FakeRequest(), db=AsyncMock())

    assert resp == {"ok": True}
    assert fired["name"] == "telephony_return"


@pytest.mark.unit
async def test_webhook_ignored_returns_200_without_firing(monkeypatch) -> None:
    fired = _patch_auth(monkeypatch, WebhookAuth(WebhookOutcome.IGNORED_UNKNOWN))
    resp = await rt.telephony_webhook(_FakeRequest(), db=object())
    assert resp == {"ok": True}
    assert "name" not in fired  # never fired a background task


@pytest.mark.unit
async def test_webhook_bad_signature_raises(monkeypatch) -> None:
    call = SimpleNamespace(id=uuid4())
    _patch_auth(monkeypatch, WebhookAuth(WebhookOutcome.BAD_SIGNATURE, call=call))
    with pytest.raises(Exception):  # raise_invalid_webhook_signature → 4xx
        await rt.telephony_webhook(_FakeRequest(), db=object())
