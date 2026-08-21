"""Weather functional category + platform-key connector types (lot E, 2026-08).

Google Weather joins OpenWeatherMap in a new mutually-exclusive "weather"
category (provider resolver doctrine). Platform-key types are now
self-describing (``ConnectorType.uses_global_api_key``) so a category can mix
a user-key provider (OWM) with a platform-key one (Google Weather) — the
ConnectorTool base picks the credentials path from the RESOLVED type.
"""

from __future__ import annotations

import pytest

from src.domains.connectors.models import (
    CONNECTOR_FUNCTIONAL_CATEGORIES,
    ConnectorType,
)

pytestmark = pytest.mark.unit


class TestWeatherCategory:
    def test_google_weather_and_environment_types_exist(self) -> None:
        assert ConnectorType.GOOGLE_WEATHER.value == "google_weather"
        assert ConnectorType.GOOGLE_ENVIRONMENT.value == "google_environment"

    def test_weather_category_contains_both_providers(self) -> None:
        assert CONNECTOR_FUNCTIONAL_CATEGORIES["weather"] == frozenset(
            {ConnectorType.OPENWEATHERMAP, ConnectorType.GOOGLE_WEATHER}
        )

    def test_environment_is_not_in_the_weather_category(self) -> None:
        """AQ/pollen are platform services independent of the weather provider
        choice — putting them in the category would make OWM users lose them
        (one active provider per category)."""
        assert ConnectorType.GOOGLE_ENVIRONMENT not in CONNECTOR_FUNCTIONAL_CATEGORIES["weather"]


class TestUsesGlobalApiKeyProperty:
    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.GOOGLE_PLACES,
            ConnectorType.GOOGLE_ROUTES,
            ConnectorType.GOOGLE_WEATHER,
            ConnectorType.GOOGLE_ENVIRONMENT,
        ],
    )
    def test_platform_key_types(self, connector_type: ConnectorType) -> None:
        assert connector_type.uses_global_api_key is True

    @pytest.mark.parametrize(
        "connector_type",
        [
            ConnectorType.OPENWEATHERMAP,
            ConnectorType.GOOGLE_GMAIL,
            ConnectorType.APPLE_CALENDAR,
            ConnectorType.PERPLEXITY,
        ],
    )
    def test_user_credential_types(self, connector_type: ConnectorType) -> None:
        assert connector_type.uses_global_api_key is False
