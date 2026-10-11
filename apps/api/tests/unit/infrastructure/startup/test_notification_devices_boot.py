"""A failed reinitialization must withdraw the previous notification owner."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.notification_devices import (
    configure_notification_devices,
    get_notification_devices,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_reinitialization_never_keeps_a_stale_device_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.notifications import device_gateway

    previous = configure_notification_devices(device_gateway.SavedNotificationDevices())
    monkeypatch.setattr(
        device_gateway,
        "SavedNotificationDevices",
        MagicMock(side_effect=RuntimeError("broken owner")),
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_notification_devices()
        with pytest.raises(AuthorizationError):
            get_notification_devices()
    finally:
        configure_notification_devices(previous)
