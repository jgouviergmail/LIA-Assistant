"""Malformed escaped Unicode never reaches serialization or error logs."""

import pytest
from pydantic import ValidationError

from src.domains.sms.schemas import SmsIngestItem
from src.domains.sms.sender_policy import normalize_sender

pytestmark = pytest.mark.unit


def test_unpaired_surrogate_is_an_invalid_item_not_a_serialization_failure():
    for field in ("sender", "body"):
        payload = {
            "sender": "Alice",
            "body": "Bonjour",
            "date": "2026-01-01T00:00:00Z",
            "o": "iphone",
        }
        payload[field] = "private" + chr(0xD800)
        with pytest.raises(ValidationError):
            SmsIngestItem.model_validate(payload)


def test_punctuation_only_senders_do_not_collapse_to_one_empty_number():
    assert normalize_sender("---") != normalize_sender("(.)")
    assert not normalize_sender("---").startswith("phone:")


def test_extreme_timezone_date_is_rejected_before_utc_overflow():
    with pytest.raises(ValidationError):
        SmsIngestItem.model_validate(
            {
                "sender": "Alice",
                "body": "Bonjour",
                "date": "0001-01-01T00:00:00+14:00",
                "o": "iphone",
            }
        )
