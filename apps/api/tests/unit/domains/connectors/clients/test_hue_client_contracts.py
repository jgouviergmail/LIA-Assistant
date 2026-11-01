"""The Hue client's contract, for the « Tools » lights screen and the assistant (ADR-369).

- A light, room or scene id is the bridge's own (CLIP v2 ids are UUIDs): an id
  of any other shape comes from a browser or a model, names nothing, and asks
  nothing — interpolated raw, ``../bridge`` would aim the person's bridge key
  (or remote token) at another endpoint of their bridge.
- Our own per-account window, exhausted, is a TYPED rate limit with its wait —
  a bare RuntimeError could only read as an outage.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError, RateLimitError
from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient
from src.domains.connectors.schemas import HueBridgeCredentials, HueConnectionMode

pytestmark = pytest.mark.unit

_LIGHT = "3f2c1b6e-7c1a-4f4e-9a52-6a1f0b9c2d11"


def _client() -> tuple[PhilipsHueClient, AsyncMock]:
    client = PhilipsHueClient(
        user_id=uuid4(),
        credentials=HueBridgeCredentials(
            connection_mode=HueConnectionMode.LOCAL, api_key="key", bridge_ip="192.168.1.10"
        ),
        connector_service=None,
    )
    spy = AsyncMock(return_value={"data": [{"id": _LIGHT, "services": []}]})
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


_ACTS: dict[str, Any] = {
    "get_light": lambda c, i: c.get_light(i),
    "update_light": lambda c, i: c.update_light(i, on=True),
    "control_room": lambda c, i: c.control_room(i, on=True),
    "activate_scene": lambda c, i: c.activate_scene(i),
}


class TestAnIdIsTheBridgesOwn:
    @pytest.mark.parametrize("act", sorted(_ACTS))
    @pytest.mark.parametrize(
        "foreign", ["../bridge", f"{_LIGHT}/../../bridge", "", "living-room", f"{_LIGHT}?x=1"]
    )
    async def test_another_shape_asks_nothing(self, act: str, foreign: str) -> None:
        client, spy = _client()
        with pytest.raises(ConnectorAPIError) as refused:
            await _ACTS[act](client, foreign)
        assert refused.value.upstream_status_code == 404
        spy.assert_not_awaited()

    @pytest.mark.parametrize("act", sorted(_ACTS))
    async def test_the_bridge_s_own_id_is_asked_for(self, act: str) -> None:
        client, spy = _client()
        if act == "control_room":
            spy.return_value = {
                "data": [{"id": _LIGHT, "services": [{"rtype": "grouped_light", "rid": _LIGHT}]}]
            }
        await _ACTS[act](client, _LIGHT.upper())
        assert all(_LIGHT in call.args[1] for call in spy.await_args_list)


class TestOurOwnWindow:
    async def test_an_exhausted_window_is_a_typed_rate_limit(self) -> None:
        client, _ = _client()
        limiter = MagicMock(acquire=AsyncMock(return_value=False))
        with (
            patch.object(client, "_get_redis_rate_limiter", AsyncMock(return_value=limiter)),
            patch("asyncio.sleep", AsyncMock()),
            patch(
                "src.domains.connectors.clients.philips_hue_client.settings",
                MagicMock(rate_limit_enabled=True, hue_rate_limit_per_second=10),
            ),
            pytest.raises(RateLimitError) as refused,
        ):
            await client._rate_limit()
        assert refused.value.retry_after > 0
