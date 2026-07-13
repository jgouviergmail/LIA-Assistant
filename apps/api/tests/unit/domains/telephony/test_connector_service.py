"""Unit tests for TelephonyConnectorService validate/list (P2.2, mocked client)."""

import pytest

from src.domains.telephony.connector import TelephonyConnectorService
from src.domains.telephony.schemas import PhoneNumberInfo


class _FakeClient:
    def __init__(self, *, valid: bool = True, raise_validate: bool = False, numbers=None):
        self._valid = valid
        self._raise = raise_validate
        self._numbers = numbers or []

    async def validate_key(self) -> bool:
        if self._raise:
            raise RuntimeError("network down")
        return self._valid

    async def list_phone_numbers(self):
        return self._numbers


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
