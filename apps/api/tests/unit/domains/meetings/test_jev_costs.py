"""The displayed meeting total includes native spend without repricing synthesis tokens."""

from types import SimpleNamespace

import pytest

from src.domains.meetings.models import Meeting
from src.domains.meetings.processing import _cost_metadata
from src.domains.meetings.service import total_cost_eur
from src.domains.meetings.synthesis import SynthesisUsage
from src.infrastructure.llm.decision_types import DecisionCharge

pytestmark = pytest.mark.unit


def test_native_selection_is_in_meeting_and_notification_totals() -> None:
    charge = DecisionCharge(
        model="jev-1.13.0",
        input_tokens=1000,
        output_tokens=20,
        cost_usd=0.000042,
        cost_eur=0.0000378,
    )
    meeting = Meeting(stt_cost_eur=0.1, synthesis_cost_eur=0.2)
    meeting.template_selection_usage = [
        {**charge.model_dump(mode="json"), "run_id": "meeting-native"}
    ]
    assert total_cost_eur(meeting) == 0.300038
    meta = _cost_metadata(
        meeting,
        SimpleNamespace(cost_eur=0.1, model="stt", audio_duration_seconds=60),
        SynthesisUsage(100, 30, 0, "synthesis-model"),
    )
    assert meta["cost_eur"] == 0.300038
    assert meta["tokens_in"] == 1100 and meta["tokens_out"] == 50
    assert meta["template_selection_usage"][0]["model"] == "jev-1.13.0"
    assert meta["llm_cost_eur"] == 0.2
    assert meta["selection_cost_eur"] == pytest.approx(0.0000378)
    assert meeting.synthesis_tokens_in is None  # Native tokens never mutate the synthesis bucket.


def test_notification_does_not_rebill_a_previous_failed_attempt() -> None:
    meeting = Meeting(stt_cost_eur=0.1, synthesis_cost_eur=0.2)
    meeting.template_selection_usage = [
        {
            "model": "jev-1.13.0",
            "input_tokens": 1000,
            "output_tokens": 20,
            "cost_usd": 0.000042,
            "cost_eur": 0.0000378,
            "run_id": "failed-attempt",
        }
    ]
    meta = _cost_metadata(
        meeting,
        SimpleNamespace(cost_eur=0.1, model="stt", audio_duration_seconds=60),
        SynthesisUsage(100, 30, 0, "synthesis-model"),
        run_id="retry",
    )
    assert meta["tokens_in"] == 100
    assert meta["cost_eur"] == 0.3
    assert total_cost_eur(meeting) == 0.300038  # The meeting still owns ALL its paid attempts.


def test_native_price_does_not_make_an_unpriced_synthesis_look_priced() -> None:
    meeting = Meeting(stt_cost_eur=0.1, synthesis_cost_eur=None)
    meeting.template_selection_usage = [
        {
            "model": "jev-1.13.0",
            "input_tokens": 1000,
            "output_tokens": 20,
            "cost_usd": 0.000042,
            "cost_eur": 0.0000378,
            "run_id": "current",
        }
    ]
    meta = _cost_metadata(
        meeting,
        SimpleNamespace(cost_eur=0.1, model="stt", audio_duration_seconds=60),
        SynthesisUsage(100, 30, 0, "unpriced"),
        run_id="current",
    )
    assert meta["llm_cost_eur"] is None
    assert meta["selection_cost_eur"] == pytest.approx(0.0000378)
    assert meta["cost_eur"] == 0.100038
