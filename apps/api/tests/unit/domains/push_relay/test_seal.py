"""
The sealed handle — the relay's entire storage design.

A handle is an authenticated ciphertext carrying the device token itself, so
the relay keeps no database: nothing to leak, nothing to clean up, no table
mapping devices to anything. That property only holds if the seal is genuinely
opaque and genuinely fail-closed, which is what these tests exist to hold in
place.

Fail-closed here means: any handle that is not one we issued yields nothing at
all. Not a partial read, not an exception the caller has to classify — nothing.
A wake with an unreadable handle must be indistinguishable from a wake with a
handle for a device that no longer exists.
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet

from src.domains.push_relay.seal import seal_device, unseal_handle

pytestmark = pytest.mark.unit


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


class TestRoundTrip:
    def test_a_sealed_device_comes_back_whole(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key)

        device = unseal_handle(handle, key=key)

        assert device is not None
        assert device.device_token == "apns-token-abc"
        assert device.sandbox is False

    def test_the_gateway_survives_the_round_trip(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=True, key=key)

        device = unseal_handle(handle, key=key)

        # Losing this flag sends every development build's notification to the
        # production gateway, where it is a permanent BadDeviceToken.
        assert device is not None
        assert device.sandbox is True

    def test_the_handle_does_not_expose_the_device_token(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key)

        # The handle travels to a self-hosted server we do not control, and is
        # stored there. It must reveal nothing about the device.
        assert "apns-token-abc" not in handle

    def test_two_seals_of_one_device_differ(self, key: str) -> None:
        first = seal_device("apns-token-abc", sandbox=False, key=key)
        second = seal_device("apns-token-abc", sandbox=False, key=key)

        # Otherwise a handle is a stable device identifier, and correlating two
        # servers' stored handles would reveal they hold the same user.
        assert first != second


class TestFailClosed:
    @pytest.mark.parametrize(
        "handle",
        ["", "not-a-handle", "z" * 200],
    )
    def test_a_handle_we_never_issued_yields_nothing(self, key: str, handle: str) -> None:
        assert unseal_handle(handle, key=key) is None

    def test_a_handle_sealed_with_another_key_yields_nothing(self, key: str) -> None:
        foreign = seal_device("apns-token-abc", sandbox=False, key=Fernet.generate_key().decode())

        # Rotating the seal key is the relay's panic button: it must invalidate
        # every handle in circulation at once.
        assert unseal_handle(foreign, key=key) is None

    def test_a_tampered_handle_yields_nothing(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key)
        tampered = handle[:-4] + ("aaaa" if not handle.endswith("aaaa") else "bbbb")

        assert unseal_handle(tampered, key=key) is None

    def test_an_expired_handle_yields_nothing(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key)

        # The shell re-registers on every launch, so expiry is self-healing and
        # bounds how long a leaked handle stays usable.
        tomorrow = time.time() + 86400
        assert unseal_handle(handle, key=key, max_age=timedelta(hours=1), now=tomorrow) is None

    def test_a_handle_inside_its_window_still_reads(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key)

        assert unseal_handle(handle, key=key, max_age=timedelta(days=180)) is not None

    def test_a_malformed_key_yields_nothing_rather_than_raising(self) -> None:
        # A misconfigured deployment must refuse wakes, not return 500s that
        # look like the caller's fault.
        assert unseal_handle("anything", key="not-a-fernet-key") is None


class TestLanguage:
    def test_the_language_travels_inside_the_handle(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key, language="de")

        device = unseal_handle(handle, key=key)

        # Sealed rather than passed at wake time: a calling server should not
        # have to tell the relay anything about the user it is waking.
        assert device is not None
        assert device.language == "de"

    def test_a_handle_sealed_before_the_field_existed_still_reads(self, key: str) -> None:
        legacy = Fernet(key.encode()).encrypt(b'{"t": "apns-token-abc", "s": false}').decode()

        device = unseal_handle(legacy, key=key)

        # Refusing it would silence a device until its next launch, for a field
        # whose absence has a perfectly good answer.
        assert device is not None
        assert device.language == "fr"

    def test_an_unsupported_language_falls_back_rather_than_refusing(self, key: str) -> None:
        handle = seal_device("apns-token-abc", sandbox=False, key=key, language="klingon")

        device = unseal_handle(handle, key=key)

        assert device is not None
        assert device.language == "fr"
