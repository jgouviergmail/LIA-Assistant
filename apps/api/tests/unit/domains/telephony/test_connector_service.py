"""Unit tests for TelephonyConnectorService validate/list (P2.2, mocked client)."""

import pytest

from src.core.config import settings
from src.core.exceptions import ExternalServiceError
from src.domains.telephony.client import ElevenLabsAgentsError
from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.schemas import PhoneNumberInfo


class _FakeClient:
    def __init__(
        self,
        *,
        valid: bool = True,
        raise_validate: bool = False,
        numbers=None,
        raise_create: ElevenLabsAgentsError | None = None,
    ):
        self._valid = valid
        self._raise = raise_validate
        self._numbers = numbers or []
        self._raise_create = raise_create
        self.create_agent_kwargs: dict | None = None

    async def validate_key(self) -> bool:
        if self._raise:
            raise RuntimeError("network down")
        return self._valid

    async def list_phone_numbers(self):
        return self._numbers

    async def create_agent(self, **kwargs) -> str:
        self.create_agent_kwargs = kwargs
        if self._raise_create is not None:
            raise self._raise_create
        return "ag_test"


def _service(client) -> TelephonyConnectorService:
    # db is unused by validate/list — safe to pass None for these unit tests.
    return TelephonyConnectorService(db=None, client_factory=lambda _key: client)  # type: ignore[arg-type]


@pytest.mark.unit
async def test_validate_key_ok():
    res = await _service(_FakeClient(valid=True)).validate_key("sk")
    assert res.is_valid is True


@pytest.mark.unit
async def test_validate_key_false_on_error():
    res = await _service(_FakeClient(raise_validate=True)).validate_key("sk")
    assert res.is_valid is False


@pytest.mark.unit
async def test_list_numbers_delegates_to_client():
    nums = [PhoneNumberInfo(phone_number_id="pn_1", phone_number="+33600000000", provider="twilio")]
    out = await _service(_FakeClient(numbers=nums)).list_numbers("sk")
    assert len(out) == 1 and out[0].phone_number_id == "pn_1"


@pytest.mark.unit
async def test_deactivate_deletes_via_connector_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deactivation must go through ConnectorService.delete_connector — the
    generic path that invalidates the Redis user-connectors cache. A direct row
    delete left the cached list serving the connector as connected (2026-07-17
    regression: disconnect looked like a no-op until the cache TTL expired)."""
    from types import SimpleNamespace
    from uuid import uuid4

    import src.domains.telephony.connector as cmod

    user_id = uuid4()
    connector = SimpleNamespace(id=uuid4(), connector_metadata={"agent_id": "ag_1"})
    deleted_agents: list[str] = []
    delete_calls: list[tuple] = []

    class _FakeConnectorService:
        def __init__(self, _db):
            self.repository = SimpleNamespace(
                get_by_user_and_type=self._get_by_user_and_type,
            )

        async def _get_by_user_and_type(self, _uid, _ctype):
            return connector

        async def get_api_key_credentials(self, _uid, _ctype):
            return SimpleNamespace(api_key="sk")

        async def delete_connector(self, uid, cid):
            delete_calls.append((uid, cid))

    class _FakeVendorClient:
        async def delete_agent(self, agent_id: str) -> None:
            deleted_agents.append(agent_id)

    monkeypatch.setattr(cmod, "ConnectorService", _FakeConnectorService)
    service = TelephonyConnectorService(db=None, client_factory=lambda _k: _FakeVendorClient())  # type: ignore[arg-type]
    await service.deactivate(user_id)

    assert deleted_agents == ["ag_1"]  # best-effort vendor cleanup ran
    assert delete_calls == [(user_id, connector.id)]  # cache-invalidating path used


@pytest.mark.unit
async def test_activate_passes_tts_model_and_maps_vendor_error():
    """activate() must send the settings-driven TTS model (non-English agents
    require turbo/flash v2.5) and translate a vendor 400 into the domain
    ExternalServiceError (503) instead of leaking an unhandled 500."""
    from uuid import uuid4

    err = ElevenLabsAgentsError(400, "Non-english Agents must use turbo or flash v2_5.")
    client = _FakeClient(raise_create=err)
    with pytest.raises(ExternalServiceError):
        await _service(client).activate(
            user_id=uuid4(),
            api_key="sk",
            agent_phone_number_id="pn_1",
            webhook_secret="whsec",
            user_language="fr",
            user_name="Jean",
        )
    assert client.create_agent_kwargs is not None
    assert client.create_agent_kwargs["tts_model_id"] == settings.telephony_agent_tts_model_id
    assert (
        client.create_agent_kwargs["max_duration_seconds"]
        == settings.telephony_max_call_duration_seconds
    )
    assert client.create_agent_kwargs["voice_id"] == (settings.telephony_agent_voice_id or None)
    assert client.create_agent_kwargs["audio_format"] == (
        settings.telephony_agent_audio_format or None
    )
    assert client.create_agent_kwargs["llm_model"] == (settings.telephony_agent_llm_model or None)
