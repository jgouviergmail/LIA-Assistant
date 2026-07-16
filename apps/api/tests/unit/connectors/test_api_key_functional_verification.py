"""API-key connectors are verified functionally before activation (audit F034).

``validate_api_key`` must (a) reject well-formed but wrong keys via the
registered functional verifier, (b) enforce a timeout, and (c) fall back to a
format-only, *honestly-labelled* result when no verifier exists. The router
calls this before ``activate_api_key_connector``, so a False result blocks the
ACTIVE transition — closing the "ACTIVE on format only" defect.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.domains.connectors import api_key_verifiers
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService

_TYPE = ConnectorType.OPENWEATHERMAP  # has a real verifier in the registry


@pytest.fixture
def service():
    return ConnectorService(AsyncMock())


async def test_format_failures_short_circuit_before_verifier(service, monkeypatch):
    """A too-short or placeholder key never reaches the functional verifier."""
    called = False

    async def _verifier(_key, _secret):
        nonlocal called
        called = True
        return True, "should not run"

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _verifier)

    ok, _msg = await service.validate_api_key(_TYPE, "short")
    assert ok is False
    ok, _msg = await service.validate_api_key(_TYPE, "your_api_key_here")
    assert ok is False
    assert called is False


async def test_functional_rejection_blocks_activation(service, monkeypatch):
    """A well-formed key rejected by the verifier yields is_valid=False."""

    async def _verifier(_key, _secret):
        return False, "provider rejected the key"

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _verifier)

    ok, msg = await service.validate_api_key(_TYPE, "a-plausible-key-1234")
    assert ok is False
    assert "rejected" in msg


async def test_functional_success_passes(service, monkeypatch):
    """A key the verifier accepts passes validation."""

    async def _verifier(_key, _secret):
        return True, "verified"

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _verifier)

    ok, msg = await service.validate_api_key(_TYPE, "a-plausible-key-1234")
    assert ok is True
    assert msg == "verified"


async def test_verification_timeout_blocks(service, monkeypatch):
    """A verifier that hangs past the timeout is treated as invalid."""

    async def _verifier(_key, _secret):
        await asyncio.sleep(5)
        return True, "too late"

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _verifier)
    monkeypatch.setattr(
        "src.domains.connectors.service.settings.connector_api_key_verify_timeout_seconds",
        0.05,
        raising=False,
    )

    ok, msg = await service.validate_api_key(_TYPE, "a-plausible-key-1234")
    assert ok is False
    assert "timed out" in msg


async def test_type_without_verifier_is_honestly_format_only(service, monkeypatch):
    """A type with no verifier passes on format but says so explicitly."""
    monkeypatch.setattr(api_key_verifiers, "API_KEY_FUNCTIONAL_VERIFIERS", {})
    ok, msg = await service.validate_api_key(ConnectorType.PERPLEXITY, "a-plausible-key-1234")
    assert ok is True
    assert "no functional verifier" in msg


def test_functionally_verified_flag_tracks_verifier_presence():
    """F034: the ``functionally_verified`` flag surfaced by the /validate response
    and stored in the connector metadata is True iff a functional verifier exists
    for the type — so a format-only key is never presented as a verified one."""
    reg = api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS
    assert ConnectorType.OPENWEATHERMAP in reg  # real probe → functionally verified
    assert ConnectorType.BRAVE_SEARCH in reg  # cheap 1-result search probe
    # No cheap/free/non-billed probe → honestly format-only (see module docstring).
    assert ConnectorType.PERPLEXITY not in reg
    assert ConnectorType.GOOGLE_PLACES not in reg


# --------------------------------------------------------------------------- #
# Brave Search verifier (F034): cheap 1-result probe, fails closed
# --------------------------------------------------------------------------- #


def _patch_brave(monkeypatch, *, search_result=None, search_exc=None):
    """Patch BraveSearchClient so ``search``/``close`` are hermetic (no network)."""
    from unittest.mock import MagicMock

    client = MagicMock()
    if search_exc is not None:
        client.search = AsyncMock(side_effect=search_exc)
    else:
        client.search = AsyncMock(return_value=search_result)
    client.close = AsyncMock()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(
        "src.domains.connectors.clients.brave_search_client.BraveSearchClient", factory
    )
    return client


async def test_brave_verifier_accepts_a_working_key(monkeypatch):
    client = _patch_brave(monkeypatch, search_result={"web": {"results": []}})
    ok, msg = await api_key_verifiers._verify_brave_search("BSA-plausible-key", None)
    assert ok is True
    assert "verified" in msg
    client.close.assert_awaited_once()  # connection always released


async def test_brave_verifier_rejects_on_none_result(monkeypatch):
    # A 401/403/quota/network failure collapses to None inside search → not verified.
    client = _patch_brave(monkeypatch, search_result=None)
    ok, msg = await api_key_verifiers._verify_brave_search("BSA-bad-key", None)
    assert ok is False
    assert "rejected" in msg or "unreachable" in msg
    client.close.assert_awaited_once()


async def test_brave_verifier_fails_closed_on_unexpected_exception(monkeypatch):
    client = _patch_brave(monkeypatch, search_exc=RuntimeError("boom"))
    ok, msg = await api_key_verifiers._verify_brave_search("BSA-key", None)
    assert ok is False
    assert "RuntimeError" in msg
    client.close.assert_awaited_once()  # closed even on failure


def _verify_count(connector_type: ConnectorType, result: str) -> float:
    from src.infrastructure.observability.metrics import connector_api_key_verification_total

    return connector_api_key_verification_total.labels(
        connector_type=connector_type.value, result=result
    )._value.get()


async def test_verification_outcomes_are_metered(service, monkeypatch):
    """F034: each verification outcome increments connector_api_key_verification_total."""

    async def _ok(_key, _secret):
        return True, "verified"

    async def _ko(_key, _secret):
        return False, "rejected"

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _ok)
    before = _verify_count(_TYPE, "verified")
    await service.validate_api_key(_TYPE, "a-plausible-key-1234")
    assert _verify_count(_TYPE, "verified") == before + 1

    monkeypatch.setitem(api_key_verifiers.API_KEY_FUNCTIONAL_VERIFIERS, _TYPE, _ko)
    before = _verify_count(_TYPE, "rejected")
    await service.validate_api_key(_TYPE, "a-plausible-key-1234")
    assert _verify_count(_TYPE, "rejected") == before + 1

    # A type with no verifier is metered as format_only (honest, not "verified").
    before = _verify_count(ConnectorType.PERPLEXITY, "format_only")
    monkeypatch.setattr(api_key_verifiers, "API_KEY_FUNCTIONAL_VERIFIERS", {})
    await service.validate_api_key(ConnectorType.PERPLEXITY, "a-plausible-key-1234")
    assert _verify_count(ConnectorType.PERPLEXITY, "format_only") == before + 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
