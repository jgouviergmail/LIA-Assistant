"""A failed live owner restart must not retain its previous binding."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.live_preferences import configure_live_preferences, get_live_preferences
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_live_connector_owner_restart_withdraws_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.live import connector_preference_gateway
    from src.infrastructure.live_connector_preferences import (
        configure_live_connector_preferences,
        get_live_connector_preferences,
    )

    previous = configure_live_connector_preferences(
        connector_preference_gateway.SavedLiveConnectorPreferences()
    )
    monkeypatch.setattr(
        connector_preference_gateway,
        "SavedLiveConnectorPreferences",
        MagicMock(side_effect=RuntimeError("broken owner")),
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_live_connector_preferences()
        with pytest.raises(AuthorizationError):
            get_live_connector_preferences()
    finally:
        configure_live_connector_preferences(previous)


def test_failed_live_owner_restart_withdraws_the_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.live import preference_gateway

    previous = configure_live_preferences(preference_gateway.SavedLivePreferences())
    monkeypatch.setattr(
        preference_gateway,
        "SavedLivePreferences",
        MagicMock(side_effect=RuntimeError("broken owner")),
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_live_preferences()
        with pytest.raises(AuthorizationError):
            get_live_preferences()
    finally:
        configure_live_preferences(previous)
