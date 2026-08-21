"""ConnectorTool category mix: user-key vs platform-key providers (lot E).

The "weather" category mixes OpenWeatherMap (per-user API key) with Google
Weather (platform GOOGLE_API_KEY). The base tool must pick the credentials
path from the RESOLVED connector type: a platform-key provider is activated
by toggle and never asks for user credentials; a user-key provider keeps the
credentials path untouched.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime

from src.domains.agents.tools.base import APIKeyConnectorTool, ConnectorTool
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


class _FakeGoogleWeatherClient:
    """Platform-key client shape: single-arg constructor."""

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id


class _FakeOwmClient:
    """User-key client shape: (user_id, credentials, connector_service)."""

    def __init__(self, user_id: UUID, credentials: Any, connector_service: Any) -> None:
        self.user_id = user_id
        self.credentials = credentials


class _WeatherProbeTool(ConnectorTool[Any]):
    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = _FakeOwmClient
    functional_category = "weather"

    def __init__(self) -> None:
        super().__init__(tool_name="weather_probe_tool", operation="read")

    async def execute_api_call(self, client: Any, user_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return {"client": type(client).__name__}

    def format_response(self, result: dict[str, Any]) -> str:
        return json.dumps(result)


def _runtime(user_id: str) -> ToolRuntime:
    store = MagicMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock()
    return ToolRuntime(
        state={},
        context=None,
        config={"configurable": {"user_id": user_id, "thread_id": "t"}},
        stream_writer=MagicMock(),
        tool_call_id="test_call_id",
        store=store,
    )


def _deps(service: MagicMock) -> MagicMock:
    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=service)

    async def _run_factory(cls: Any, cache_key: Any, factory: Any) -> Any:
        return await factory()

    deps.get_or_create_client = AsyncMock(side_effect=_run_factory)
    deps.db = MagicMock()
    return deps


class _WeatherApiKeyProbeTool(APIKeyConnectorTool[Any]):
    """Weather tools live on APIKeyConnectorTool — same mix contract."""

    connector_type = ConnectorType.OPENWEATHERMAP
    client_class = _FakeOwmClient
    functional_category = "weather"

    def __init__(self) -> None:
        super().__init__(tool_name="weather_api_key_probe_tool", operation="read")

    def create_client(self, credentials: Any, user_id: UUID) -> Any:
        client = MagicMock()
        client.kind = "_FakeOwmClient"
        return client

    async def execute_api_call(self, client: Any, user_id: UUID, **kwargs: Any) -> dict[str, Any]:
        return {"client": getattr(client, "kind", type(client).__name__)}

    def format_response(self, result: dict[str, Any]) -> str:
        return json.dumps(result)


class TestApiKeyToolGlobalKeyMix:
    async def test_platform_key_provider_skips_api_key_credentials(self) -> None:
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=True)
        service.get_api_key_credentials = AsyncMock()
        deps = _deps(service)

        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_active_connector",
                new=AsyncMock(return_value=ConnectorType.GOOGLE_WEATHER),
            ),
            patch(
                "src.domains.connectors.clients.registry.ClientRegistry.get_client_class",
                return_value=_FakeGoogleWeatherClient,
            ),
            patch("src.domains.agents.tools.base.get_dependencies", return_value=deps),
        ):
            result = await _WeatherApiKeyProbeTool().execute(_runtime(str(uuid4())))

        assert "_FakeGoogleWeatherClient" in str(result)
        service.get_api_key_credentials.assert_not_awaited()

    async def test_user_key_provider_keeps_the_api_key_path(self) -> None:
        service = MagicMock()
        service.get_api_key_credentials = AsyncMock(return_value=MagicMock(api_key="k"))
        deps = _deps(service)

        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_active_connector",
                new=AsyncMock(return_value=ConnectorType.OPENWEATHERMAP),
            ),
            patch("src.domains.agents.tools.base.get_dependencies", return_value=deps),
        ):
            result = await _WeatherApiKeyProbeTool().execute(_runtime(str(uuid4())))

        assert "_FakeOwmClient" in str(result)
        service.get_api_key_credentials.assert_awaited_once()

    async def test_no_active_weather_provider_yields_not_activated_error(self) -> None:
        service = MagicMock()
        service.get_api_key_credentials = AsyncMock()
        deps = _deps(service)

        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_active_connector",
                new=AsyncMock(return_value=None),
            ),
            patch("src.domains.agents.tools.base.get_dependencies", return_value=deps),
        ):
            result = await _WeatherApiKeyProbeTool().execute(_runtime(str(uuid4())))

        assert "_FakeOwmClient" not in str(result)
        assert "_FakeGoogleWeatherClient" not in str(result)


class TestGlobalKeyMix:
    async def test_platform_key_provider_needs_no_user_credentials(self) -> None:
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=True)
        service.get_connector_credentials = AsyncMock()

        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_active_connector",
                new=AsyncMock(return_value=ConnectorType.GOOGLE_WEATHER),
            ),
            patch(
                "src.domains.connectors.clients.registry.ClientRegistry.get_client_class",
                return_value=_FakeGoogleWeatherClient,
            ),
            patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps(service)),
        ):
            result = await _WeatherProbeTool().execute(_runtime(str(uuid4())))

        assert "_FakeGoogleWeatherClient" in str(result)
        service.get_connector_credentials.assert_not_awaited()

    async def test_user_key_provider_keeps_the_credentials_path(self) -> None:
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=True)
        service.get_connector_credentials = AsyncMock(
            return_value=ConnectorCredentials(
                access_token="k", refresh_token=None, expires_at=9999999999
            )
        )

        with (
            patch(
                "src.domains.connectors.provider_resolver.resolve_active_connector",
                new=AsyncMock(return_value=ConnectorType.OPENWEATHERMAP),
            ),
            patch(
                "src.domains.connectors.clients.registry.ClientRegistry.get_client_class",
                return_value=_FakeOwmClient,
            ),
            patch("src.domains.agents.tools.base.get_dependencies", return_value=_deps(service)),
        ):
            result = await _WeatherProbeTool().execute(_runtime(str(uuid4())))

        assert "_FakeOwmClient" in str(result)
        service.get_connector_credentials.assert_awaited_once()
