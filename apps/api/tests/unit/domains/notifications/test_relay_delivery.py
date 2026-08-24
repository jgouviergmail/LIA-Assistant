"""
Routing a notification to a device the deployment cannot reach itself.

The published iOS shell registers a token prefixed ``relay:`` — its own
declaration that it is reachable only through a wake relay. Everything else
keeps going to Firebase exactly as before, and the first test in each class
exists to hold that: this branch must be invisible to Android, to the web, and
to a self-hoster who publishes their own iOS build.

Two failure modes are pinned deliberately. A relayed device on a server with no
relay configured must fail LOUDLY and identifiably, not silently — otherwise an
operator who forgot one variable sees "notifications don't work" with nothing
naming the cause. And an unreachable relay must never deactivate a token: doubt
never deletes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.domains.notifications.service import FCMNotificationService
from src.infrastructure.external.push_relay_client import RelayWakeResult

pytestmark = pytest.mark.unit

SERVICE = "src.domains.notifications.service"


def _service() -> FCMNotificationService:
    return FCMNotificationService(db=Mock())


async def _send(
    service: FCMNotificationService,
    token: str,
    *,
    relay_url: str | None = "https://relay.example.com",
    wake: RelayWakeResult | None = None,
) -> object:
    client = Mock()
    client.wake = AsyncMock(
        return_value=wake or RelayWakeResult(sent=True, should_forget_handle=False)
    )
    with (
        patch(f"{SERVICE}.settings") as fake_settings,
        patch(f"{SERVICE}.PushRelayClient", return_value=client) as factory,
    ):
        fake_settings.push_relay_url = relay_url
        fake_settings.push_relay_timeout_seconds = 8.0
        result = await service._send_to_token(token=token, title="T", body="B")
    return result, client, factory


class TestRelayedDevices:
    async def test_a_relayed_token_never_reaches_firebase(self) -> None:
        service = _service()
        with patch.object(service, "_get_firebase_app") as firebase:
            result, client, _ = await _send(service, "relay:sealed-handle")

        firebase.assert_not_called()
        assert result.success is True

    async def test_the_prefix_is_stripped_before_the_relay_sees_it(self) -> None:
        service = _service()
        _, client, _ = await _send(service, "relay:sealed-handle")

        # The prefix is this server's own bookkeeping. A relay that received it
        # would fail to unseal a handle it issued correctly.
        client.wake.assert_awaited_once_with("sealed-handle")

    async def test_the_relay_saying_forget_deactivates_the_token(self) -> None:
        service = _service()
        result, _, _ = await _send(
            service,
            "relay:sealed-handle",
            wake=RelayWakeResult(sent=False, should_forget_handle=True, error="device_gone"),
        )

        assert result.success is False
        assert result.token_invalid is True

    async def test_an_unreachable_relay_keeps_the_token(self) -> None:
        service = _service()
        result, _, _ = await _send(
            service,
            "relay:sealed-handle",
            wake=RelayWakeResult(sent=False, should_forget_handle=False, error="ConnectError"),
        )

        # Doubt never deletes: a relay outage must not cost every iPhone user
        # their notifications permanently.
        assert result.success is False
        assert result.token_invalid is False


class TestMisconfiguration:
    async def test_a_relayed_token_without_a_relay_fails_by_name(self) -> None:
        service = _service()
        result, _, factory = await _send(service, "relay:sealed-handle", relay_url=None)

        factory.assert_not_called()
        assert result.success is False
        assert "relay" in (result.error or "").lower()

    async def test_and_it_does_not_deactivate_the_token_either(self) -> None:
        service = _service()
        result, _, _ = await _send(service, "relay:sealed-handle", relay_url=None)

        # The device is fine. The server is missing a variable, and setting it
        # must be enough to make notifications work again.
        assert result.token_invalid is False


class TestEverythingElseIsUntouched:
    @pytest.mark.parametrize(
        "token",
        ["fcm-android-token", "fcm-web-token", "an-ios-token-of-our-own-build"],
    )
    async def test_a_token_without_the_prefix_goes_to_firebase(self, token: str) -> None:
        service = _service()
        with patch.object(service, "_get_firebase_app", return_value=None) as firebase:
            _, _, factory = await _send(service, token)

        firebase.assert_called_once()
        factory.assert_not_called()

    async def test_a_token_merely_containing_the_word_relay_is_not_relayed(self) -> None:
        service = _service()
        with patch.object(service, "_get_firebase_app", return_value=None) as firebase:
            _, _, factory = await _send(service, "some-relay:token")

        # The declaration is a PREFIX. Matching it loosely would hijack a
        # perfectly valid Firebase token.
        firebase.assert_called_once()
        factory.assert_not_called()
