"""
The relay's two endpoints, called as a self-hosted server calls them.

The contract worth pinning at this level is what a CALLER can act on. A wake
that reaches Apple is a successful call whatever Apple then said, so the
outcome travels in the body — and ``should_forget_handle`` is the field a
calling server actually branches on. Getting that flag wrong in the safe-looking
direction (forgetting on our own misconfiguration) would have every self-hosted
deployment silently delete every handle it holds, the moment we mistype an
environment variable.

Throttling is the deliberate exception: 429 with ``Retry-After`` is what an HTTP
client already knows how to obey without reading our taxonomy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domains.push_relay.dependencies import (
    get_push_relay_service,
    rate_limit_relay_register,
)
from src.domains.push_relay.router import router
from src.domains.push_relay.service import WakeOutcome

pytestmark = pytest.mark.unit

_DEVICE_TOKEN = "a1b2c3d4" * 8


def _client(service: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_push_relay_service] = lambda: service
    app.dependency_overrides[rate_limit_relay_register] = lambda: None
    return TestClient(app)


def _service(*, outcome: WakeOutcome = WakeOutcome.SENT, handle: str = "sealed") -> AsyncMock:
    service = AsyncMock()
    service.register = AsyncMock(return_value=handle)
    service.wake = AsyncMock(return_value=outcome)
    return service


class TestRegistration:
    def test_a_device_gets_its_handle(self) -> None:
        service = _service(handle="sealed-handle")

        response = _client(service).post(
            "/push-relay/devices",
            json={"device_token": _DEVICE_TOKEN, "sandbox": False, "language": "de"},
        )

        assert response.status_code == 201
        assert response.json() == {"handle": "sealed-handle"}

    def test_the_language_reaches_the_seal(self) -> None:
        service = _service()

        _client(service).post(
            "/push-relay/devices",
            json={"device_token": _DEVICE_TOKEN, "language": "it"},
        )

        assert service.register.await_args.kwargs["language"] == "it"

    def test_a_language_we_do_not_speak_falls_back(self) -> None:
        service = _service()

        _client(service).post(
            "/push-relay/devices",
            json={"device_token": _DEVICE_TOKEN, "language": "klingon"},
        )

        # Sealing an unknown language would produce a device that can only ever
        # be woken in the fallback anyway — decided here, once.
        assert service.register.await_args.kwargs["language"] == "fr"

    @pytest.mark.parametrize(
        "token",
        ["", "short", "not-hexadecimal-at-all-not-at-all-nope-nope", "zz" * 32],
    )
    def test_something_that_is_not_a_device_token_is_refused(self, token: str) -> None:
        response = _client(_service()).post("/push-relay/devices", json={"device_token": token})

        assert response.status_code == 422

    def test_the_gateway_defaults_to_production(self) -> None:
        service = _service()

        _client(service).post("/push-relay/devices", json={"device_token": _DEVICE_TOKEN})

        assert service.register.await_args.kwargs["sandbox"] is False


class TestWaking:
    def test_a_sent_wake_says_so_and_keeps_the_handle(self) -> None:
        response = _client(_service(outcome=WakeOutcome.SENT)).post(
            "/push-relay/wake", json={"handle": "sealed"}
        )

        assert response.status_code == 200
        assert response.json() == {"outcome": "sent", "should_forget_handle": False}

    @pytest.mark.parametrize(
        "outcome",
        [WakeOutcome.UNKNOWN_HANDLE, WakeOutcome.DEVICE_GONE],
    )
    def test_an_unrecoverable_outcome_tells_the_caller_to_forget(
        self, outcome: WakeOutcome
    ) -> None:
        response = _client(_service(outcome=outcome)).post(
            "/push-relay/wake", json={"handle": "sealed"}
        )

        assert response.json()["should_forget_handle"] is True

    @pytest.mark.parametrize(
        "outcome",
        [WakeOutcome.UNAVAILABLE, WakeOutcome.MISCONFIGURED],
    )
    def test_a_failure_of_ours_never_costs_the_caller_its_handle(
        self, outcome: WakeOutcome
    ) -> None:
        response = _client(_service(outcome=outcome)).post(
            "/push-relay/wake", json={"handle": "sealed"}
        )

        # Apple being down, or us mistyping a topic, must not make every
        # self-hosted deployment delete every handle it holds.
        assert response.status_code == 200
        assert response.json()["should_forget_handle"] is False

    def test_a_spent_budget_is_a_429_a_client_can_obey(self) -> None:
        response = _client(_service(outcome=WakeOutcome.THROTTLED)).post(
            "/push-relay/wake", json={"handle": "sealed"}
        )

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"

    def test_an_empty_handle_never_reaches_the_service(self) -> None:
        service = _service()

        response = _client(service).post("/push-relay/wake", json={"handle": ""})

        assert response.status_code == 422
        service.wake.assert_not_awaited()
