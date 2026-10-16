"""Provider diagnostics cannot expose credentials in activation refusals."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import structlog
from structlog.testing import capture_logs

from src.core import _exceptions_base
from src.core.exceptions import BaseAPIException
from src.domains.connectors import service as service_module
from src.domains.connectors.clients.philips_hue_client import PhilipsHueClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService

PRIVATE = "proof-private-mail@example.com?access_token=proof-private-value"


@pytest.mark.parametrize("kind", ["google_gmail", "microsoft_outlook", "hue_local"])
async def test_activation_failure_excludes_provider_prose_from_response_and_public_logs(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    service = ConnectorService(AsyncMock())
    monkeypatch.setattr(service_module, "logger", structlog.get_logger())
    monkeypatch.setattr(_exceptions_base, "logger", structlog.get_logger())
    failure = RuntimeError(PRIVATE)
    if kind == "hue_local":
        monkeypatch.setattr(PhilipsHueClient, "test_connection", AsyncMock(side_effect=failure))
    else:
        handler = MagicMock(handle_callback=AsyncMock(side_effect=failure))
        monkeypatch.setattr("src.core.oauth.OAuthFlowHandler", lambda *args: handler)
        monkeypatch.setattr(
            service_module, "get_redis_session", AsyncMock(return_value=MagicMock())
        )
    with capture_logs() as records:
        with pytest.raises(BaseAPIException) as refused:
            if kind == "hue_local":
                await service.activate_hue_local(uuid4(), "192.168.1.2", "proof-application-key")
            else:
                await service._handle_oauth_connector_callback(
                    uuid4(),
                    "proof-code",
                    "proof-state",
                    ConnectorType(kind),
                    lambda config: MagicMock(),
                )
    assert PRIVATE not in str(refused.value.detail)
    public = [record for record in records if record["log_level"] != "debug"]
    assert PRIVATE not in json.dumps(public, default=str)
    assert all(not record.get("exc_info") for record in public)
    assert refused.value.status_code == (503 if kind == "hue_local" else 400)
