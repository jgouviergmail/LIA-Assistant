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

import httpx
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


def _answered(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://bridge")
    return httpx.HTTPStatusError(
        "refused", request=request, response=httpx.Response(status, request=request)
    )


def _room_client() -> tuple[PhilipsHueClient, AsyncMock]:
    client, spy = _client()
    spy.return_value = {
        "data": [{"id": _LIGHT, "services": [{"rtype": "grouped_light", "rid": _LIGHT}]}]
    }
    return client, spy


class TestWhatTheBridgeHolds:
    async def test_its_zones_and_who_it_reaches_are_two_reads(self) -> None:
        client, spy = _client()

        assert await client.list_zones() == [{"id": _LIGHT, "services": []}]
        assert await client.list_connectivity() == [{"id": _LIGHT, "services": []}]

        assert [call.args for call in spy.await_args_list] == [
            ("GET", "zone"),
            ("GET", "zigbee_connectivity"),
        ]

    @pytest.mark.parametrize("read", ["list_zones", "list_connectivity"])
    async def test_a_bridge_that_holds_no_such_resource_reads_as_none(self, read: str) -> None:
        client, spy = _client()
        spy.side_effect = _answered(404)

        assert await getattr(client, read)() == []

    @pytest.mark.parametrize("read", ["list_zones", "list_connectivity"])
    @pytest.mark.parametrize("status", [401, 429, 503])
    async def test_any_other_refusal_stays_a_failure(self, read: str, status: int) -> None:
        client, spy = _client()
        spy.side_effect = _answered(status)

        with pytest.raises(httpx.HTTPStatusError):
            await getattr(client, read)()


class TestAGroup:
    async def test_a_zone_is_read_as_a_zone(self) -> None:
        client, spy = _room_client()

        await client.control_room(_LIGHT, on=True, group="zone")

        assert spy.await_args_list[0].args == ("GET", f"zone/{_LIGHT}")

    async def test_a_room_takes_a_colour_or_a_temperature_as_a_lamp_does(self) -> None:
        client, spy = _room_client()

        await client.control_room(_LIGHT, color_xy=(0.1, 0.2), color_temperature_mirek=300)

        assert spy.await_args.args == ("PUT", f"grouped_light/{_LIGHT}")
        assert spy.await_args.kwargs["json_data"] == {
            "color": {"xy": {"x": 0.1, "y": 0.2}},
            "color_temperature": {"mirek": 300},
        }

    async def test_a_lamp_and_a_room_are_sent_the_same_body(self) -> None:
        client, spy = _room_client()
        state = {
            "on": True,
            "brightness": 140.0,
            "color_xy": (0.1, 0.2),
            "color_temperature_mirek": 300,
        }

        await client.control_room(_LIGHT, **state)
        room = spy.await_args.kwargs["json_data"]
        await client.update_light(_LIGHT, **state)

        assert spy.await_args.kwargs["json_data"] == room
        assert room["dimming"] == {"brightness": 100.0}


class TestAScene:
    async def test_a_recall_says_the_person_s_action(self) -> None:
        client, spy = _client()

        await client.activate_scene(_LIGHT, action="dynamic_palette")

        assert spy.await_args.kwargs["json_data"] == {"recall": {"action": "dynamic_palette"}}

    async def test_a_recall_names_the_scene_as_it_stands_by_default(self) -> None:
        client, spy = _client()

        await client.activate_scene(_LIGHT)

        assert spy.await_args.kwargs["json_data"] == {"recall": {"action": "active"}}


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
