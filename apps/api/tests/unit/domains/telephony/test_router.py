"""Unit tests for the telephony connector router logic (P2.3, service mocked)."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

import src.domains.telephony.router as rmod
from src.domains.telephony.schemas import (
    KeyValidationResult,
    PhoneNumberInfo,
    TelephonyActivateRequest,
    TelephonyKeyValidateRequest,
)


class _FakeService:
    def __init__(self, db) -> None:  # noqa: ANN001 — db unused in the fake
        self.db = db

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        return KeyValidationResult(is_valid=True, message="valid")

    async def list_numbers(self, api_key: str):
        return [
            PhoneNumberInfo(phone_number_id="pn_1", phone_number="+33600000000", provider="twilio")
        ]

    async def activate(self, **kwargs):
        return SimpleNamespace(
            connector_metadata={"agent_id": "ag_1", "agent_phone_number_id": "pn_1"}
        )

    async def deactivate(self, user_id) -> None:  # noqa: ANN001
        return None


def _user():
    return SimpleNamespace(id=uuid4(), full_name="Jean", email="jean@example.com", language="fr")


@pytest.fixture(autouse=True)
def _patch_service(monkeypatch):
    monkeypatch.setattr(rmod, "TelephonyConnectorService", _FakeService)


@pytest.mark.unit
async def test_validate_key_endpoint_returns_numbers_when_valid():
    resp = await rmod.validate_key(
        TelephonyKeyValidateRequest(api_key="sk-testkey"), user=_user(), db=None
    )
    assert resp.is_valid is True
    assert len(resp.numbers) == 1
    assert resp.numbers[0].phone_number_id == "pn_1"


@pytest.mark.unit
async def test_activate_endpoint_maps_metadata_to_response():
    resp = await rmod.activate(
        TelephonyActivateRequest(
            api_key="sk-testkey", agent_phone_number_id="pn_1", webhook_secret="whsec"
        ),
        user=_user(),
        db=None,
    )
    assert resp.status == "active"
    assert resp.agent_id == "ag_1"
    assert resp.agent_phone_number_id == "pn_1"


@pytest.mark.unit
async def test_deactivate_endpoint_runs():
    # Should not raise; returns None (204).
    assert await rmod.deactivate(user=_user(), db=None) is None
