"""Document addresses are bounded routing data; CORS permits only the declared header."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.application_device_identity import (
    APPLICATION_DEVICE_HEADER,
    parse_application_device_id,
)
from src.core.middleware import setup_middleware

pytestmark = pytest.mark.unit


# Fixed ids: an id derived from a random UUID differs between pytest-xdist workers.
@pytest.mark.parametrize(
    "value",
    [None, "", "invented", "a" * 1000, "{" + str(uuid4()) + "}"],
    ids=["absent", "empty", "not_a_uuid", "oversized", "braced_uuid"],
)
def test_malformed_document_addresses_are_unavailable(value: str | None) -> None:
    assert parse_application_device_id(value) is None


def test_document_address_is_normalized_without_becoming_authentication() -> None:
    value = uuid4()
    assert parse_application_device_id(str(value).upper()) == value


def test_command_transport_preflight_accepts_the_finite_document_header() -> None:
    app = FastAPI()
    with (
        patch("src.core.middleware.settings.cors_origins", ["https://web.test"]),
        patch("src.core.middleware.settings.rate_limit_enabled", False),
    ):
        setup_middleware(app)
        response = TestClient(app).options(
            "/application-device/snapshot",
            headers={
                "Origin": "https://web.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": APPLICATION_DEVICE_HEADER,
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    assert (
        APPLICATION_DEVICE_HEADER.lower()
        in response.headers["access-control-allow-headers"].lower()
    )
