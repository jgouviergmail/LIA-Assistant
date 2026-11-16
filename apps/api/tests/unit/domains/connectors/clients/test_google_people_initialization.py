"""People clients initialize OAuth once and keep external resources lazy."""

from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.domains.connectors.clients.base_google_client import BaseGoogleClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.connectors.session_scope import ConnectorUnitOfWork, DetachedConnectorService

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("explicit_rate", [False, True])
def test_initializes_oauth_once_without_opening_external_resources(
    monkeypatch: pytest.MonkeyPatch, explicit_rate: bool
) -> None:
    """Missing or repeated base initialization breaks identity or resource ownership."""
    configured_rate = settings.client_rate_limit_google_per_second + 1
    monkeypatch.setattr(settings, "client_rate_limit_google_per_second", configured_rate)
    original_init = BaseGoogleClient.__init__
    initialized: list[BaseGoogleClient] = []

    def initialize_base(
        client: BaseGoogleClient,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: ConnectorService | ConnectorUnitOfWork,
        rate_limit_per_second: int | None = None,
    ) -> None:
        initialized.append(client)
        original_init(client, user_id, credentials, connector_service, rate_limit_per_second)

    monkeypatch.setattr(BaseGoogleClient, "__init__", initialize_base)
    user_id = uuid4()
    credentials = ConnectorCredentials(access_token="unused", account_binding="test-grant")
    service = DetachedConnectorService()
    expected_rate = configured_rate + 1 if explicit_rate else configured_rate
    if explicit_rate:
        client = GooglePeopleClient(
            user_id, credentials, service, rate_limit_per_second=expected_rate
        )
    else:
        client = GooglePeopleClient(user_id, credentials, service)

    assert initialized == [client]
    assert client.user_id == user_id
    assert client.credentials is credentials
    assert client.connector_service is service
    assert client._rate_limit_per_second == expected_rate
    assert client._rate_limit_interval == 1.0 / expected_rate
    assert client._http_client is None
    assert client._redis_rate_limiter is None
    assert client._circuit_breaker is None
    assert client._cache is None
