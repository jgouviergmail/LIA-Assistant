"""The source-bound Tools read also works across separate web and API origins."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import WORKBENCH_CARD_SOURCE_HEADER
from src.core.middleware import setup_middleware

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "origin,expected", [("https://web.test", 200), ("https://other.test", 400)]
)
def test_card_source_preflight_is_limited_to_allowed_origins(origin: str, expected: int) -> None:
    app = FastAPI()
    with (
        patch("src.core.middleware.settings.cors_origins", ["https://web.test"]),
        patch("src.core.middleware.settings.rate_limit_enabled", False),
    ):
        setup_middleware(app)
        with TestClient(app) as client:
            response = client.options(
                "/workbench/calendar/event",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": WORKBENCH_CARD_SOURCE_HEADER,
                },
            )
    assert response.status_code == expected
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        assert (
            WORKBENCH_CARD_SOURCE_HEADER.lower()
            in response.headers["access-control-allow-headers"].lower()
        )
