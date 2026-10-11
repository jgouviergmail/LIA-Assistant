"""An export-port restart never retains the previous binding after owner construction fails."""

from unittest.mock import MagicMock

import pytest

from src.core.exceptions import AuthorizationError
from src.infrastructure.account_exports import configure_account_exports, get_account_exports
from src.infrastructure.startup import registries

pytestmark = pytest.mark.unit


def test_failed_export_owner_restart_withdraws_previous_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.account_export import gateway

    previous = configure_account_exports(gateway.SavedAccountExports())
    monkeypatch.setattr(
        gateway, "SavedAccountExports", MagicMock(side_effect=RuntimeError("broken owner"))
    )
    try:
        with pytest.raises(RuntimeError, match="broken owner"):
            registries.init_account_exports()
        with pytest.raises(AuthorizationError):
            get_account_exports()
    finally:
        configure_account_exports(previous)
