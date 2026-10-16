"""The briefing's weather card names a provider's rate limit as one (ADR-108 amendment).

A 429 the API-key client could not wait out now reaches the fetcher as a typed
``ConnectorAPIError`` instead of a retry exhaustion; the card must read its
status — never the « network » it used to show for every exhausted retry.
"""

from __future__ import annotations

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.briefing.constants import (
    ERROR_CODE_CONNECTOR_NETWORK,
    ERROR_CODE_CONNECTOR_RATE_LIMIT,
)
from src.domains.briefing.fetchers import _classify_http_error

pytestmark = pytest.mark.unit


def test_a_provider_rate_limit_handed_back_by_the_client_reads_as_one() -> None:
    refusal = ConnectorAPIError(connector_type="openweathermap", status_code=429, detail="limited")

    assert _classify_http_error(refusal) == ERROR_CODE_CONNECTOR_RATE_LIMIT


def test_a_refused_platform_key_never_claims_the_persons_connector_expired() -> None:
    # Google Weather runs on the INSTANCE's key: a 401 is the operator's to fix
    # (ADR-307), so only the status a person can act on is mapped.
    refusal = ConnectorAPIError(connector_type="google_weather", status_code=401, detail="no")

    assert _classify_http_error(refusal) == ERROR_CODE_CONNECTOR_NETWORK


def test_a_raw_http_429_still_reads_as_a_rate_limit() -> None:
    request = httpx.Request("GET", "https://weather.example/api")
    error = httpx.HTTPStatusError(
        "429", request=request, response=httpx.Response(429, request=request)
    )

    assert _classify_http_error(error) == ERROR_CODE_CONNECTOR_RATE_LIMIT
