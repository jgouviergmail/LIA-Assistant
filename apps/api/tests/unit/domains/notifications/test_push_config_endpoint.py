"""
What a server tells its native shells about receiving notifications.

One app is published per store and it is pointed at whichever server its user
runs, so the shell cannot carry any of this in its binary. It asks, and the
answer differs per platform for a reason that is not symmetric:

- Android gets this deployment's own Firebase options and talks to Firebase
  directly. Nothing passes through anyone else.
- iOS gets a relay URL, because only the Apple team owning the published app
  may notify it, and a self-hosted deployment is not that team.

A deployment that has configured neither must say so plainly. A shell that
receives ``null`` shows the user that notifications are unavailable — far
better than registering a token nothing will ever send to, which looks exactly
like working until the first notification never arrives.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from src.domains.notifications.router import get_push_config

pytestmark = pytest.mark.unit

ROUTER = "src.domains.notifications.router"

_FIREBASE = {
    "firebase_android_app_id": "1:123:android:abc",
    "firebase_api_key": "AIzaKey",
    "firebase_project_id": "self-hosted-project",
    "firebase_sender_id": "123",
}


async def _config(**overrides: Any) -> Any:
    values = {**_FIREBASE, "push_relay_url": None, **overrides}
    with patch(f"{ROUTER}.settings") as fake_settings:
        for name, value in values.items():
            setattr(fake_settings, name, value)
        return await get_push_config()


class TestAndroid:
    async def test_a_configured_deployment_publishes_its_firebase_options(self) -> None:
        config = await _config()

        assert config.android is not None
        assert config.android.app_id == "1:123:android:abc"
        assert config.android.api_key == "AIzaKey"
        assert config.android.project_id == "self-hosted-project"
        assert config.android.sender_id == "123"

    @pytest.mark.parametrize(
        "missing",
        ["firebase_android_app_id", "firebase_api_key", "firebase_sender_id"],
    )
    async def test_one_missing_option_means_no_android_push_at_all(self, missing: str) -> None:
        config = await _config(**{missing: None})

        # Firebase refuses to initialise on a partial set, so handing the shell
        # three of four values buys a crash instead of a notification.
        assert config.android is None


class TestIos:
    async def test_a_relay_is_published_when_one_is_configured(self) -> None:
        config = await _config(push_relay_url="https://relay.example.com")

        assert config.ios is not None
        assert config.ios.relay_url == "https://relay.example.com"

    async def test_no_relay_means_no_ios_push(self) -> None:
        config = await _config(push_relay_url=None)

        # Deliberate: the shell must be able to tell the user notifications are
        # unavailable, rather than register a handle nobody can spend.
        assert config.ios is None

    async def test_ios_never_receives_the_firebase_options(self) -> None:
        config = await _config(push_relay_url="https://relay.example.com")

        # They would be useless — and worse, they would suggest a direct route
        # to a shell that has none.
        assert set(config.ios.model_dump()) == {"relay_url"}


class TestNeither:
    async def test_a_deployment_with_no_push_says_so_on_both_platforms(self) -> None:
        config = await _config(
            firebase_android_app_id=None,
            firebase_api_key=None,
            firebase_sender_id=None,
            push_relay_url=None,
        )

        assert config.android is None
        assert config.ios is None
