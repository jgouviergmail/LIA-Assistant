"""A failed consent-owner restart cannot preserve an obsolete source binding."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_preferences import configure_phone_preferences, get_phone_preferences
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_preferences_restart_withdraws_the_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.telephony import preference_gateway

    previous = configure_phone_preferences(preference_gateway.SavedPhonePreferences())
    monkeypatch.setattr(
        preference_gateway,
        "SavedPhonePreferences",
        MagicMock(side_effect=RuntimeError("broken owner")),
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_phone_preferences()
        with pytest.raises(AuthorizationError):
            get_phone_preferences()
    finally:
        configure_phone_preferences(previous)
