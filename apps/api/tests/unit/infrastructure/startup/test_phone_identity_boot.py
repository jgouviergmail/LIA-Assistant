"""A failed phone-owner restart cannot leave an obsolete read binding serving data."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.phone_identity import configure_phone_identity, get_phone_identity
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_phone_owner_restart_withdraws_the_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.telephony import identity_gateway

    previous = configure_phone_identity(identity_gateway.SavedPhoneIdentity())
    monkeypatch.setattr(
        identity_gateway, "SavedPhoneIdentity", MagicMock(side_effect=RuntimeError("broken owner"))
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_phone_identity()
        with pytest.raises(AuthorizationError):
            get_phone_identity()
    finally:
        configure_phone_identity(previous)
