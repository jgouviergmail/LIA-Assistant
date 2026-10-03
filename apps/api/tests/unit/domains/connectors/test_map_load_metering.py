"""Browser map grants cannot change beneficiary or bypass disabled configuration."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.connectors.map_load_metering import (
    browser_maps_key,
    issue_load_token,
    verify_load_token,
)
from src.domains.connectors.map_load_router import MapLoadReport, admit_map_load, report_map_load
from src.domains.google_api.pricing_service import GoogleApiPricingService


def test_grant_is_bound_to_the_authenticated_beneficiary():
    user_id = uuid4()
    token = issue_load_token(user_id)
    assert verify_load_token(token, user_id)
    with pytest.raises(BaseAPIException):
        verify_load_token(token, uuid4())


@pytest.mark.parametrize("token", ["", ".", "a" * 201, "0.0.0", "0.0.é", "../etc/passwd"])
def test_malformed_grants_fail_closed(token):
    with pytest.raises(BaseAPIException):
        verify_load_token(token, uuid4())


def test_expired_grant_is_refused_even_with_valid_signature(monkeypatch):
    import src.domains.connectors.map_load_metering as metering

    user_id = uuid4()
    monkeypatch.setattr(metering.time, "time", lambda: 1000)
    token = issue_load_token(user_id)
    monkeypatch.setattr(metering.time, "time", lambda: 5000)
    with pytest.raises(BaseAPIException):
        verify_load_token(token, user_id)


def test_token_tampering_and_secret_rotation_invalidate_admission(monkeypatch):
    user_id = uuid4()
    token = issue_load_token(user_id)
    with pytest.raises(BaseAPIException):
        verify_load_token(token[:-1] + ("a" if token[-1] != "a" else "b"), user_id)
    monkeypatch.setattr(settings, "secret_key", "replacement-key-only-for-this-test")
    with pytest.raises(BaseAPIException):
        verify_load_token(token, user_id)


@pytest.mark.parametrize("browser_key", ["", "server-key", " server-key "])
def test_shared_google_key_is_reused_with_optional_browser_override(monkeypatch, browser_key):
    monkeypatch.setattr(settings, "google_api_key", "server-key")
    monkeypatch.setattr(settings, "google_maps_browser_api_key", browser_key)
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.007"), Decimal("0.006"), Decimal(1)),
    )
    assert browser_maps_key() == "server-key"


def test_missing_google_keys_refuse_activation(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "google_maps_browser_api_key", "")
    with pytest.raises(BaseAPIException):
        browser_maps_key()


def test_browser_override_takes_precedence_over_shared_google_key(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", "shared-key")
    monkeypatch.setattr(settings, "google_maps_browser_api_key", " browser-key ")
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.007"), Decimal("0.006"), Decimal(1)),
    )
    assert browser_maps_key() == "browser-key"


def test_missing_price_refuses_activation_instead_of_accounting_at_zero(monkeypatch):
    monkeypatch.setattr(settings, "google_maps_browser_api_key", "browser-key")
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal(0), Decimal(0), Decimal(1)),
    )
    with pytest.raises(BaseAPIException):
        browser_maps_key()


@pytest.mark.parametrize("eur", [Decimal("0"), Decimal("-0.006")])
def test_admission_refuses_an_unusable_eur_budget_quote(monkeypatch, eur):
    from src.domains.connectors.map_load_metering import map_load_config

    monkeypatch.setattr(settings, "google_api_key", "shared-key")
    monkeypatch.setattr(settings, "google_maps_browser_api_key", "")
    monkeypatch.setattr(
        GoogleApiPricingService,
        "get_cost_per_request",
        lambda *_: (Decimal("0.007"), eur, Decimal(1)),
    )
    assert map_load_config() == {"enabled": False}
    with pytest.raises(BaseAPIException):
        browser_maps_key()


async def test_admission_is_budget_gated_private_and_does_not_meter_a_load(monkeypatch):
    import json

    import src.domains.connectors.map_load_router as router

    monkeypatch.setattr(router, "browser_maps_key", lambda: "browser-key")
    budget = AsyncMock(return_value=SimpleNamespace(allowed=True))
    monkeypatch.setattr(router.UsageLimitService, "check_user_allowed", budget)
    meter = AsyncMock()
    monkeypatch.setattr(router, "record_map_load", meter)
    user = SimpleNamespace(id=uuid4())
    response = await admit_map_load(user)
    payload = json.loads(response.body)
    assert payload["api_key"] == "browser-key"
    assert verify_load_token(payload["load_token"], user.id)
    assert response.headers["cache-control"] == "private, no-store"
    budget.assert_awaited_once_with(user.id)
    meter.assert_not_awaited()


async def test_invalid_beneficiary_report_does_not_reach_any_ledger(monkeypatch):
    import src.domains.connectors.map_load_router as router

    meter = AsyncMock()
    monkeypatch.setattr(router, "record_map_load", meter)
    body = MapLoadReport(load_token=issue_load_token(uuid4()))
    with pytest.raises(BaseAPIException):
        await report_map_load(body, SimpleNamespace(id=uuid4()))
    meter.assert_not_awaited()


async def test_failed_persistence_is_never_acknowledged_and_same_token_can_retry(monkeypatch):
    import src.domains.connectors.map_load_router as router

    user = SimpleNamespace(id=uuid4())
    body = MapLoadReport(load_token=issue_load_token(user.id))
    meter = AsyncMock(side_effect=RuntimeError("persistence unavailable"))
    monkeypatch.setattr(router, "record_map_load", meter)
    with pytest.raises(RuntimeError, match="persistence unavailable"):
        await report_map_load(body, user)
    meter.side_effect = None
    response = await report_map_load(body, user)
    assert response.status_code == 200
    assert meter.await_count == 2


async def test_blocked_budget_never_issues_an_admission(monkeypatch):
    import src.domains.connectors.map_load_router as router

    monkeypatch.setattr(router, "browser_maps_key", lambda: "browser-key")
    monkeypatch.setattr(
        router.UsageLimitService,
        "check_user_allowed",
        AsyncMock(return_value=SimpleNamespace(allowed=False)),
    )
    issued = AsyncMock()
    monkeypatch.setattr(router, "issue_load_token", issued)

    def refuse(*_args, **_kwargs):
        raise RuntimeError("budget blocked")

    monkeypatch.setattr(router, "raise_for_blocked_verdict", refuse)
    with pytest.raises(RuntimeError, match="budget blocked"):
        await admit_map_load(SimpleNamespace(id=uuid4()))
    issued.assert_not_called()


def test_report_cannot_spoof_the_beneficiary():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MapLoadReport.model_validate({"load_token": "x", "user_id": str(uuid4())})


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("0.007")])
async def test_public_configuration_requires_pricing_and_contains_no_credentials(
    monkeypatch, price
):
    import json

    from src.domains.connectors.map_load_metering import map_load_config

    monkeypatch.setattr(settings, "google_maps_browser_api_key", "browser-key")
    monkeypatch.setattr(settings, "google_api_key", "private-server-key")
    monkeypatch.setattr(
        GoogleApiPricingService, "get_cost_per_request", lambda *_: (price, price, Decimal(1))
    )
    payload = map_load_config()
    assert payload["enabled"] is (price > 0)
    assert "key" not in json.dumps(payload)
    if price:
        assert payload["estimated_cost_eur"] == "0.007"
