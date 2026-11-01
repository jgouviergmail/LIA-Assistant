"""The lights of the « Tools » section (ADR-369, Task 9.1).

One read draws the bridge: its rooms (with the lights their devices own), its
lights (what each one can do — dimming, colour, temperature and its range) and
its scenes. A change sends what the lamp accepts: a colour picked as #rrggbb
is sent as xy; a colour or a temperature for a lamp without one is refused
BEFORE anything is sent; an unreachable bridge, our own window and the
bridge's throttle each say what they are.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException, RateLimitError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import lights_service
from src.domains.workbench.light_colours import hex_to_xy
from src.domains.workbench.schemas.lights import LightChange, RoomChange, SceneRecall

pytestmark = pytest.mark.unit

USER = uuid4()
LAMP, BULB, PLUG = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)
DEVICE_A, DEVICE_B = (
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
)
ROOM, SCENE = (
    "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
)

_COLOUR_LAMP: dict[str, Any] = {
    "id": LAMP,
    "owner": {"rid": DEVICE_A, "rtype": "device"},
    "metadata": {"name": "Sofa"},
    "on": {"on": True},
    "dimming": {"brightness": 62.5, "min_dim_level": 0.2},
    "color": {"xy": {"x": 0.3127, "y": 0.329}},
    "color_temperature": {
        "mirek": 366,
        "mirek_valid": True,
        "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500},
    },
}
_WHITE_BULB: dict[str, Any] = {
    "id": BULB,
    "owner": {"rid": DEVICE_B, "rtype": "device"},
    "metadata": {"name": "Hall"},
    "on": {"on": False},
    "dimming": {"brightness": 100.0},
}
_PLUG: dict[str, Any] = {
    "id": PLUG,
    "owner": {"rid": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "rtype": "device"},
    "metadata": {"name": "Lamp plug"},
    "on": {"on": True},
}
_ROOM: dict[str, Any] = {
    "id": ROOM,
    "metadata": {"name": "Living room"},
    "children": [{"rid": DEVICE_A, "rtype": "device"}, {"rid": DEVICE_B, "rtype": "device"}],
    "services": [{"rid": "ffffffff-ffff-4fff-8fff-ffffffffffff", "rtype": "grouped_light"}],
}
_SCENE: dict[str, Any] = {
    "id": SCENE,
    "metadata": {"name": "Relax"},
    "group": {"rid": ROOM, "rtype": "room"},
    "status": {"active": "static"},
}


def _bridge(**overrides: Any) -> MagicMock:
    methods = {
        "list_lights": [_COLOUR_LAMP, _WHITE_BULB, _PLUG],
        "list_rooms": [_ROOM],
        "list_scenes": [_SCENE],
        "get_light": _COLOUR_LAMP,
        "update_light": {"data": [{"rid": LAMP}]},
        "control_room": {"data": []},
        "activate_scene": {"data": []},
    }
    methods.update(overrides)
    return MagicMock(**{name: AsyncMock(return_value=value) for name, value in methods.items()})


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.PHILIPS_HUE, preferred_name=None
        )

    return patch.object(lights_service, "open_tool_client", opened)


class TestTheRead:
    async def test_rooms_hold_the_lights_their_devices_own(self) -> None:
        with _door(_bridge()):
            view = await lights_service.read_lights(USER)

        room = view.rooms[0]
        assert (room.id, room.name, room.light_ids) == (ROOM, "Living room", [LAMP, BULB])
        assert room.on is True, "a room is on while one of its lights is"
        assert [light.room_id for light in view.lights] == [ROOM, ROOM, None]
        assert (view.scenes[0].name, view.scenes[0].room_id, view.scenes[0].active) == (
            "Relax",
            ROOM,
            True,
        )

    async def test_each_light_says_what_it_can_do(self) -> None:
        with _door(_bridge()):
            lamp, bulb, plug = (await lights_service.read_lights(USER)).lights

        assert (lamp.brightness, lamp.supports_color, lamp.color_hex) == (62.5, True, "#ffffff")
        assert (lamp.mirek, lamp.mirek_min, lamp.mirek_max) == (366, 153, 500)
        assert (bulb.supports_color, bulb.mirek, bulb.brightness) == (False, None, 100.0)
        assert (plug.brightness, plug.supports_color) == (None, False)


class TestAChange:
    async def test_a_colour_is_sent_as_its_chromaticity(self) -> None:
        bridge = _bridge()
        with _door(bridge):
            await lights_service.change_light(USER, LightChange(light_id=LAMP, color_hex="#ff8800"))

        assert bridge.update_light.await_args.kwargs["color_xy"] == hex_to_xy("#ff8800")

    async def test_switching_on_or_off_needs_no_read_of_the_lamp(self) -> None:
        bridge = _bridge()
        with _door(bridge):
            await lights_service.change_light(USER, LightChange(light_id=LAMP, on=False))

        bridge.get_light.assert_not_awaited()
        assert bridge.update_light.await_args.kwargs["on"] is False

    @pytest.mark.parametrize(
        ("lamp", "change"),
        [
            (_WHITE_BULB, {"color_hex": "#ff0000"}),
            (_WHITE_BULB, {"mirek": 300}),
            (_PLUG, {"brightness": 40}),
        ],
    )
    async def test_what_a_lamp_cannot_do_is_refused_unsent(
        self, lamp: dict[str, Any], change: dict[str, Any]
    ) -> None:
        bridge = _bridge(get_light=lamp)
        with _door(bridge), pytest.raises(BaseAPIException) as refused:
            await lights_service.change_light(USER, LightChange(light_id=lamp["id"], **change))

        assert refused.value.detail == {"code": "not_supported_by_provider"}
        bridge.update_light.assert_not_awaited()

    def test_a_colour_and_a_temperature_together_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            LightChange(light_id=LAMP, color_hex="#ff0000", mirek=300)

    def test_a_change_that_changes_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            LightChange(light_id=LAMP)

    async def test_a_room_and_a_scene(self) -> None:
        bridge = _bridge()
        with _door(bridge):
            await lights_service.change_room(USER, RoomChange(room_id=ROOM, on=True, brightness=30))
            await lights_service.recall_scene(USER, SceneRecall(scene_id=SCENE))

        assert bridge.control_room.await_args.kwargs == {"on": True, "brightness": 30.0}
        bridge.activate_scene.assert_awaited_once_with(SCENE)


class TestWhatTheBridgeSays:
    @pytest.mark.parametrize(
        ("failure", "detail"),
        [
            (
                httpx.ConnectError("unreachable", request=httpx.Request("GET", "https://b/x")),
                {"code": "provider_unavailable"},
            ),
            (
                RateLimitError(limit=600, window_seconds=60, retry_after=1),
                {"code": "provider_rate_limited", "retry_after": 1},
            ),
            (
                httpx.HTTPStatusError(
                    "throttled",
                    request=httpx.Request("PUT", "https://b/x"),
                    response=httpx.Response(429, request=httpx.Request("PUT", "https://b/x")),
                ),
                {"code": "provider_rate_limited"},
            ),
        ],
    )
    async def test_each_failure_says_what_it_is(
        self, failure: Exception, detail: dict[str, Any]
    ) -> None:
        bridge = _bridge()
        bridge.update_light.side_effect = failure
        with _door(bridge), pytest.raises(BaseAPIException) as refused:
            await lights_service.change_light(USER, LightChange(light_id=LAMP, on=True))

        assert refused.value.detail == detail
