"""Unit tests for the PhoneCall model + StructuredCallData schema (P1.3)."""

import pytest

from src.domains.telephony.models import PhoneCall, PhoneCallStatus
from src.domains.telephony.schemas import StructuredCallData


@pytest.mark.unit
def test_phone_call_status_values():
    assert PhoneCallStatus.DIALING.value == "dialing"
    assert {s.value for s in PhoneCallStatus} == {
        "dialing",
        "in_progress",
        "completed",
        "no_answer",
        "voicemail",
        "failed",
        "cancelled",
    }


@pytest.mark.unit
def test_structured_call_data_round_trips_through_dict():
    data = StructuredCallData(
        agreed=True,
        proposed_datetime="2026-07-11T12:00:00Z",
        location="L'Ardoise",
    )
    as_dict = data.model_dump()
    assert StructuredCallData.model_validate(as_dict) == data


@pytest.mark.unit
def test_structured_call_data_ignores_unknown_fields():
    # Extra keys from the transcript extraction must not break ingestion.
    data = StructuredCallData.model_validate({"agreed": False, "unexpected": "x"})
    assert data.agreed is False
    assert not hasattr(data, "unexpected")


@pytest.mark.unit
def test_phone_call_tablename():
    assert PhoneCall.__tablename__ == "phone_calls"
