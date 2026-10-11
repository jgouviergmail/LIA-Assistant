"""Failed number-owner restarts withdraw stale bindings before any operation."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_number_preferences import (
    configure_phone_number_preferences,
    get_phone_number_preferences,
)
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_number_restart_withdraws_the_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.telephony import number_gateway

    previous = configure_phone_number_preferences(number_gateway.SavedPhoneNumber())
    monkeypatch.setattr(
        number_gateway, "SavedPhoneNumber", MagicMock(side_effect=RuntimeError("broken owner"))
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_phone_number()
        with pytest.raises(AuthorizationError):
            get_phone_number_preferences()
    finally:
        configure_phone_number_preferences(previous)
