"""Keyless connectors are decided by the INSTANCE, never by a row (ADR-307).

``connectors/keyless.py`` is the one predicate; ``ConnectorService.is_connector_active``
answers it for every keyless type without reading the account's rows, and the
activation schema refuses to write one back.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.domains.connectors.keyless import (
    REASON_BROWSER_DISABLED,
    REASON_DISABLED_BY_ADMIN,
    REASON_PLATFORM_KEY_MISSING,
    is_keyless_available,
    keyless_unavailable_reason,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyActivationRequest
from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.unit

KEYLESS = sorted(ConnectorType.get_keyless_types())
PLATFORM_KEY = [t for t in KEYLESS if t.uses_global_api_key]


def _repository(*, enabled: bool | None = None) -> MagicMock:
    """A repository whose global configuration row says ``enabled`` (None = no row)."""
    repository = MagicMock()
    config = None if enabled is None else SimpleNamespace(is_enabled=enabled)
    repository.get_global_config_by_type = AsyncMock(return_value=config)
    repository.get_by_user_and_type = AsyncMock()
    return repository


@pytest.fixture
def instance_provides_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_api_key", "platform-key")
    monkeypatch.setattr(settings, "browser_enabled", True)


@pytest.mark.usefixtures("instance_provides_everything")
class TestKeylessUnavailableReason:
    @pytest.mark.parametrize("connector_type", KEYLESS)
    async def test_available_with_no_global_row(self, connector_type: ConnectorType) -> None:
        assert await keyless_unavailable_reason(_repository(), connector_type) is None
        assert await is_keyless_available(_repository(enabled=True), connector_type)

    @pytest.mark.parametrize("connector_type", KEYLESS)
    async def test_the_administrator_switch_wins(self, connector_type: ConnectorType) -> None:
        reason = await keyless_unavailable_reason(_repository(enabled=False), connector_type)
        assert reason == REASON_DISABLED_BY_ADMIN

    @pytest.mark.parametrize("connector_type", PLATFORM_KEY)
    async def test_a_platform_key_type_needs_the_platform_key(
        self, connector_type: ConnectorType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "google_api_key", "")
        reason = await keyless_unavailable_reason(_repository(), connector_type)
        assert reason == REASON_PLATFORM_KEY_MISSING

    async def test_the_free_services_need_no_platform_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "google_api_key", "")
        for connector_type in (ConnectorType.WIKIPEDIA, ConnectorType.BROWSER):
            assert await is_keyless_available(_repository(), connector_type)

    async def test_the_browser_follows_its_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "browser_enabled", False)
        reason = await keyless_unavailable_reason(_repository(), ConnectorType.BROWSER)
        assert reason == REASON_BROWSER_DISABLED

    async def test_a_connector_the_person_configures_has_no_instance_answer(self) -> None:
        with pytest.raises(ValueError, match="not a keyless"):
            await keyless_unavailable_reason(_repository(), ConnectorType.OPENWEATHERMAP)


@pytest.mark.usefixtures("instance_provides_everything")
class TestIsConnectorActive:
    @pytest.mark.parametrize("connector_type", KEYLESS)
    async def test_a_keyless_type_never_reads_the_account_rows(
        self, connector_type: ConnectorType
    ) -> None:
        service = ConnectorService(AsyncMock())
        service.repository = _repository()

        assert await service.is_connector_active(uuid4(), connector_type)
        service.repository.get_by_user_and_type.assert_not_awaited()

    async def test_a_keyless_type_withheld_by_the_instance_is_inactive(self) -> None:
        service = ConnectorService(AsyncMock())
        service.repository = _repository(enabled=False)

        assert not await service.is_connector_active(uuid4(), ConnectorType.GOOGLE_PLACES)

    async def test_any_other_type_still_reads_its_row(self) -> None:
        service = ConnectorService(AsyncMock())
        service.repository = _repository()
        service.repository.get_by_user_and_type.return_value = None

        assert not await service.is_connector_active(uuid4(), ConnectorType.OPENWEATHERMAP)
        service.repository.get_by_user_and_type.assert_awaited_once()


class TestActivationRefusesKeylessTypes:
    @pytest.mark.parametrize("connector_type", KEYLESS)
    def test_no_account_can_activate_a_keyless_type(self, connector_type: ConnectorType) -> None:
        with pytest.raises(ValidationError, match="the instance provides it"):
            APIKeyActivationRequest(api_key="not_required", connector_type=connector_type)

    def test_a_key_the_person_owns_is_still_accepted(self) -> None:
        request = APIKeyActivationRequest(
            api_key="k" * 32, connector_type=ConnectorType.OPENWEATHERMAP
        )
        assert request.connector_type is ConnectorType.OPENWEATHERMAP
