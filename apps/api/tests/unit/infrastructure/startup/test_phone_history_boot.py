"""A failed restart must withdraw the previous owner before rebuilding it."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_history import configure_phone_history, get_phone_history
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_history_owner_restart_withdraws_the_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.telephony import history_gateway

    previous = configure_phone_history(history_gateway.SavedPhoneHistory())
    monkeypatch.setattr(
        history_gateway, "SavedPhoneHistory", MagicMock(side_effect=RuntimeError("broken owner"))
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_phone_history()
        with pytest.raises(AuthorizationError):
            get_phone_history()
    finally:
        configure_phone_history(previous)
