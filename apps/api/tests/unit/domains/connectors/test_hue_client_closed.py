"""Every Philips Hue client a request builds is closed, whatever the outcome (audit A04).

The local activation and the connection test built a ``PhilipsHueClient``, called the
bridge and returned — on success as on failure — without closing it: each call left the
client's pooled httpx transport open. A per-instance transport left open is a leak under
load (``open_active_client`` closes on every path for the same reason).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.connectors import router as connectors_router
from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient
from src.domains.connectors.schemas import HueBridgeCredentials, HueConnectionMode
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User

pytestmark = pytest.mark.unit


class _Stop(Exception):
    """Ends an activation once its bridge test is over: what follows is not under test."""


@pytest.fixture
def closes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every ``close`` a Hue client received."""
    seen: list[str] = []

    async def close(_client: PhilipsHueClient) -> None:
        seen.append("closed")

    monkeypatch.setattr(PhilipsHueClient, "close", close)
    return seen


def _bridge_answers(monkeypatch: pytest.MonkeyPatch, answer: object) -> None:
    effect = answer if isinstance(answer, BaseException) else None
    value = None if effect is not None else answer
    monkeypatch.setattr(
        PhilipsHueClient, "test_connection", AsyncMock(side_effect=effect, return_value=value)
    )


class TestTheLocalActivation:
    async def test_the_test_client_is_closed_before_the_activation_goes_on(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        """Closed once the bridge answered — never held across the activation's writes."""
        service = ConnectorService(AsyncMock())
        _bridge_answers(monkeypatch, {"data": [{"name": "bridge"}]})
        closed_when_locking: list[list[str]] = []

        async def lock(*_args: object) -> None:
            closed_when_locking.append(list(closes))
            raise _Stop

        monkeypatch.setattr(service, "_lock_activation", lock)

        with pytest.raises(_Stop):
            await service.activate_hue_local(uuid4(), "192.168.1.2", "proof-application-key")

        assert closed_when_locking == [["closed"]]

    async def test_an_unreachable_bridge_keeps_its_503_and_closes_the_client(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        service = ConnectorService(AsyncMock())
        _bridge_answers(monkeypatch, RuntimeError("bridge down"))

        with pytest.raises(BaseAPIException) as refused:
            await service.activate_hue_local(uuid4(), "192.168.1.2", "proof-application-key")

        assert refused.value.status_code == 503
        assert closes == ["closed"]

    async def test_a_cancelled_activation_still_closes_the_client(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        service = ConnectorService(AsyncMock())
        _bridge_answers(monkeypatch, asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await service.activate_hue_local(uuid4(), "192.168.1.2", "proof-application-key")

        assert closes == ["closed"]


class TestTheConnectionTestRoute:
    @pytest.fixture(autouse=True)
    def _stored_bridge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stored = HueBridgeCredentials(
            connection_mode=HueConnectionMode.LOCAL, api_key="proof-key", bridge_ip="192.168.1.2"
        )
        monkeypatch.setattr(ConnectorService, "get_hue_credentials", AsyncMock(return_value=stored))

    async def _test_the_bridge(self) -> dict[str, object]:
        return await connectors_router.test_hue_connection(
            current_user=User(id=uuid4()), db=AsyncMock()
        )

    async def test_a_reachable_bridge_answers_and_the_client_is_closed(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        _bridge_answers(monkeypatch, {"data": [{"name": "bridge"}]})

        answer = await self._test_the_bridge()

        assert answer == {"success": True, "bridge": {"name": "bridge"}}
        assert closes == ["closed"]

    async def test_an_unreachable_bridge_still_closes_the_client(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        _bridge_answers(monkeypatch, RuntimeError("bridge down"))

        with pytest.raises(RuntimeError):
            await self._test_the_bridge()

        assert closes == ["closed"]

    async def test_a_cancelled_test_still_closes_the_client(
        self, monkeypatch: pytest.MonkeyPatch, closes: list[str]
    ) -> None:
        _bridge_answers(monkeypatch, asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await self._test_the_bridge()

        assert closes == ["closed"]
