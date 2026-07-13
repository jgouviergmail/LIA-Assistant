"""Unit tests for the telephony webhook handler (P4.1) — auth + reconcile."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.webhook_handler as wh
from src.domains.telephony.webhook_handler import (
    WebhookOutcome,
    authenticate_and_reconcile,
    extract_agent_id,
    extract_call_id,
    verify_signature,
)

_SECRET = "whsec_test"
_TOLERANCE = 1800


def _sign(body: bytes, secret: str = _SECRET, ts: int | None = None) -> str:
    timestamp = ts if ts is not None else int(datetime.now(UTC).timestamp())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


def _payload(call_id, agent_id: str = "ag_1") -> dict:
    return {
        "type": "post_call_transcription",
        "data": {
            "agent_id": agent_id,
            "conversation_id": "conv_1",
            "conversation_initiation_client_data": {"dynamic_variables": {"call_id": str(call_id)}},
        },
    }


# --------------------------------------------------------------------------- #
# Signature verification
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_verify_signature_valid() -> None:
    body = b'{"hello":"world"}'
    assert verify_signature(body, _sign(body), _SECRET, _TOLERANCE) is True


@pytest.mark.unit
def test_verify_signature_wrong_secret() -> None:
    body = b'{"hello":"world"}'
    assert verify_signature(body, _sign(body), "other_secret", _TOLERANCE) is False


@pytest.mark.unit
def test_verify_signature_tampered_body() -> None:
    header = _sign(b'{"hello":"world"}')
    assert verify_signature(b'{"hello":"evil"}', header, _SECRET, _TOLERANCE) is False


@pytest.mark.unit
def test_verify_signature_expired_timestamp() -> None:
    body = b"{}"
    old = int(datetime.now(UTC).timestamp()) - 10_000
    assert verify_signature(body, _sign(body, ts=old), _SECRET, _TOLERANCE) is False


@pytest.mark.unit
@pytest.mark.parametrize("header", ["", "garbage", "t=123", "v0=abc", "t=notint,v0=abc"])
def test_verify_signature_malformed_header(header: str) -> None:
    assert verify_signature(b"{}", header, _SECRET, _TOLERANCE) is False


# --------------------------------------------------------------------------- #
# Field extraction
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_extractors() -> None:
    cid = uuid4()
    payload = _payload(cid, agent_id="ag_9")
    assert extract_call_id(payload) == str(cid)
    assert extract_agent_id(payload) == "ag_9"
    assert extract_call_id({"data": {}}) is None
    assert extract_agent_id({}) is None


# --------------------------------------------------------------------------- #
# authenticate_and_reconcile
# --------------------------------------------------------------------------- #


def _install(monkeypatch, *, call, connector, creds) -> None:
    class _FakeRepo:
        def __init__(self, db) -> None:  # noqa: ANN001
            pass

        async def get_by_call_id(self, _cid):
            return call

    async def _get_conn(_user_id, _ctype):
        return connector

    class _FakeConnectorService:
        def __init__(self, db) -> None:  # noqa: ANN001
            self.repository = SimpleNamespace(get_by_user_and_type=_get_conn)

        async def get_api_key_credentials(self, _user_id, _ctype):
            return creds

    monkeypatch.setattr(wh, "TelephonyRepository", _FakeRepo)
    monkeypatch.setattr(wh, "ConnectorService", _FakeConnectorService)


def _call() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=uuid4())


def _connector(agent_id: str = "ag_1") -> SimpleNamespace:
    return SimpleNamespace(connector_metadata={"agent_id": agent_id})


def _creds(secret: str = _SECRET) -> SimpleNamespace:
    return SimpleNamespace(api_secret=secret)


async def _auth(body: bytes, sig: str) -> object:
    return await authenticate_and_reconcile(body, sig, db=object(), tolerance_seconds=_TOLERANCE)


@pytest.mark.unit
async def test_reconcile_ok(monkeypatch) -> None:
    call = _call()
    payload = _payload(call.id, agent_id="ag_1")
    body = json.dumps(payload).encode()
    _install(monkeypatch, call=call, connector=_connector("ag_1"), creds=_creds())
    result = await _auth(body, _sign(body))
    assert result.outcome is WebhookOutcome.OK
    assert result.call is call
    assert result.payload == payload


@pytest.mark.unit
async def test_reconcile_unknown_call(monkeypatch) -> None:
    payload = _payload(uuid4())
    body = json.dumps(payload).encode()
    _install(monkeypatch, call=None, connector=_connector(), creds=_creds())
    result = await _auth(body, _sign(body))
    assert result.outcome is WebhookOutcome.IGNORED_UNKNOWN


@pytest.mark.unit
async def test_reconcile_agent_mismatch(monkeypatch) -> None:
    call = _call()
    payload = _payload(call.id, agent_id="ag_INTRUDER")
    body = json.dumps(payload).encode()
    _install(monkeypatch, call=call, connector=_connector("ag_1"), creds=_creds())
    result = await _auth(body, _sign(body))
    assert result.outcome is WebhookOutcome.IGNORED_AGENT_MISMATCH


@pytest.mark.unit
async def test_reconcile_bad_signature(monkeypatch) -> None:
    call = _call()
    payload = _payload(call.id, agent_id="ag_1")
    body = json.dumps(payload).encode()
    _install(monkeypatch, call=call, connector=_connector("ag_1"), creds=_creds("real_secret"))
    result = await _auth(body, _sign(body, secret="forged_secret"))
    assert result.outcome is WebhookOutcome.BAD_SIGNATURE
    assert result.call is call  # known call, forged signature → surfaced as 4xx


@pytest.mark.unit
async def test_reconcile_malformed_body(monkeypatch) -> None:
    _install(monkeypatch, call=_call(), connector=_connector(), creds=_creds())
    result = await _auth(b"not-json", "t=1,v0=x")
    assert result.outcome is WebhookOutcome.IGNORED_MALFORMED


@pytest.mark.unit
async def test_reconcile_missing_call_id(monkeypatch) -> None:
    _install(monkeypatch, call=_call(), connector=_connector(), creds=_creds())
    result = await _auth(b'{"data":{"agent_id":"ag_1"}}', "t=1,v0=x")
    assert result.outcome is WebhookOutcome.IGNORED_MALFORMED
