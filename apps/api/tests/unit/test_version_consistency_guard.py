"""SEC-022 guard — release vs API-contract version must stay distinct.

Regression: the root endpoint and the OpenAPI schema advertised a single
``version`` equal to ``API_VERSION`` ("1.0.0"), which read as the *application*
version and contradicted the build manifests (1.24.0). The running artifact's
release version now comes from ``settings.app_version`` (env APP_VERSION) and is
exposed distinctly from the frozen ``/v1`` API-contract constant.

These tests fail if either surface regresses to hardcoding the contract constant
as the app version.
"""

from src.core import constants
from src.core.config import settings
from src.main import app, root


async def test_root_endpoint_advertises_release_and_contract_versions_distinctly() -> None:
    """The root endpoint exposes app_version (release) and api_version (contract)."""
    body = await root()

    assert body["app_version"] == settings.app_version
    assert body["api_version"] == constants.API_VERSION
    # There must be no bare ``version`` field silently reintroducing the
    # confusing single value.
    assert "version" not in body


def test_openapi_schema_advertises_release_version() -> None:
    """The FastAPI/OpenAPI version tracks the release, not the /v1 constant."""
    assert app.version == settings.app_version


def test_release_version_is_not_the_contract_constant_in_dev() -> None:
    """In dev/CI the release version defaults to the dev sentinel, never the
    frozen contract constant — a cheap tripwire against wiring app_version back
    to API_VERSION."""
    assert settings.app_version != constants.API_VERSION
