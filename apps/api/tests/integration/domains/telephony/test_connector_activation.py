"""Integration tests for telephony connector activation (P2.2).

Verifies the encrypted-storage invariant against a real DB: the ElevenLabs key
and webhook secret round-trip via credentials, while the webhook secret NEVER
lands in the JSONB metadata.
"""

import pytest

from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.telephony.connector import TelephonyConnectorService


class _FakeClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def create_agent(self, **kwargs) -> str:
        return "ag_created"

    async def delete_agent(self, agent_id: str) -> None:
        self.deleted.append(agent_id)


def _service(async_session, fake) -> TelephonyConnectorService:
    return TelephonyConnectorService(async_session, client_factory=lambda _key: fake)


@pytest.mark.integration
async def test_activate_persists_encrypted_creds_and_ids_only_metadata(async_session, test_user):
    fake = _FakeClient()
    connector = await _service(async_session, fake).activate(
        user_id=test_user.id,
        api_key="sk-elevenlabs",
        agent_phone_number_id="pn_1",
        webhook_secret="whsec_supersecret",
        user_language="fr",
        user_name="Jean",
        caller_number_display="+33600000000",
    )

    md = connector.connector_metadata or {}
    assert md["agent_id"] == "ag_created"
    assert md["agent_phone_number_id"] == "pn_1"
    # Secrets NEVER in JSONB metadata.
    assert "whsec_supersecret" not in str(md)
    assert "sk-elevenlabs" not in str(md)

    # Both secrets round-trip via the encrypted credentials blob.
    creds = await ConnectorService(async_session).get_api_key_credentials(
        test_user.id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    assert creds is not None
    assert creds.api_key == "sk-elevenlabs"
    assert creds.api_secret == "whsec_supersecret"


@pytest.mark.integration
async def test_deactivate_deletes_agent_and_removes_connector(async_session, test_user):
    fake = _FakeClient()
    svc = _service(async_session, fake)
    await svc.activate(
        user_id=test_user.id,
        api_key="sk-elevenlabs",
        agent_phone_number_id="pn_1",
        webhook_secret="whsec_x",
        user_language="en",
        user_name="Jean",
    )

    await svc.deactivate(test_user.id)

    assert fake.deleted == ["ag_created"]
    creds = await ConnectorService(async_session).get_api_key_credentials(
        test_user.id, ConnectorType.ELEVENLABS_TELEPHONY
    )
    assert creds is None
