"""SMS uses shared phone punctuation rules without adopting a country guess."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.domains.telephony.phone_numbers import normalize_phone

pytestmark = pytest.mark.unit


def test_explicit_country_policy_preserves_telephony_and_sms_local_identity() -> None:
    with patch(
        "src.domains.telephony.phone_numbers.get_settings",
        return_value=SimpleNamespace(telephony_default_country_code="+44"),
    ):
        assert normalize_phone("0612 345 678") == "+44612345678"
        assert normalize_phone("0612 345 678", infer_country=False) == "0612345678"
