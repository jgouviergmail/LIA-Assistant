"""Schema-level validation of time-slot tariffs on the admin pricing API.

The admin payloads are the only writers of ``llm_model_pricing.time_slots``
(ADR-223); everything the runtime resolver assumes — non-overlap, HH:MM
shape, token-billed unit — must therefore be enforced HERE, at 422 time.
A slot list the schema lets through is a slot list the hot path will obey.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate

pytestmark = pytest.mark.unit

VALID_SLOT: dict[str, Any] = {
    "start_utc": "01:00",
    "end_utc": "04:00",
    "input_unit_price": "0.44",
    "cached_input_unit_price": "0.014",
    "output_unit_price": "1.32",
}
SECOND_SLOT: dict[str, Any] = {**VALID_SLOT, "start_utc": "06:00", "end_utc": "10:00"}


def _create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "deepseek",
        "model_name": "deepseek-v4-flash",
        "kind": "chat",
        "max_input_tokens": 1_000_000,
        "max_output_tokens": 384_000,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_temperature": True,
        "supports_top_p": True,
        "supports_frequency_penalty": True,
        "supports_presence_penalty": True,
        "is_reasoning_model": False,
        "reasoning_widget": "none",
        "input_unit_price": Decimal("0.22"),
        "cached_input_unit_price": Decimal("0.007"),
        "output_unit_price": Decimal("0.66"),
    }
    payload.update(overrides)
    return payload


class TestCreateTimeSlots:
    def test_accepts_a_valid_windowed_tariff(self) -> None:
        data = ModelPriceCreate(**_create_payload(time_slots=[VALID_SLOT, SECOND_SLOT]))
        assert data.time_slots is not None
        assert len(data.time_slots) == 2
        assert data.time_slots[0].input_unit_price == Decimal("0.44")

    def test_defaults_to_flat_pricing(self) -> None:
        assert ModelPriceCreate(**_create_payload()).time_slots is None

    def test_rejects_overlapping_slots(self) -> None:
        overlapping = [VALID_SLOT, {**VALID_SLOT, "start_utc": "03:00", "end_utc": "05:00"}]
        with pytest.raises(ValidationError, match="overlap"):
            ModelPriceCreate(**_create_payload(time_slots=overlapping))

    @pytest.mark.parametrize("unit", ["per_audio_minute", "per_audio_hour"])
    def test_rejects_slots_on_an_audio_billed_unit(self, unit: str) -> None:
        """The runtime token resolver never reads slots on audio rows; a
        windowed audio tariff would be stored and silently ignored."""
        with pytest.raises(ValidationError, match="per_1m_tokens"):
            ModelPriceCreate(**_create_payload(pricing_unit=unit, time_slots=[VALID_SLOT]))

    def test_rejects_malformed_hours(self) -> None:
        with pytest.raises(ValidationError):
            ModelPriceCreate(**_create_payload(time_slots=[{**VALID_SLOT, "start_utc": "25:00"}]))

    def test_empty_list_normalizes_to_flat_pricing(self) -> None:
        """`[]` and None mean the same thing at create time."""
        data = ModelPriceCreate(**_create_payload(time_slots=[]))
        assert data.time_slots == []


class TestUpdateTimeSlots:
    def test_accepts_slots_alone(self) -> None:
        update = ModelPriceUpdate(time_slots=[VALID_SLOT])
        assert update.time_slots is not None

    def test_empty_list_is_the_clearing_sentinel(self) -> None:
        """`exclude_none=True` in the service drops explicit nulls, so the
        wire contract for 'remove the windowed tariff' is `[]` — pinned
        here and in the service tests."""
        update = ModelPriceUpdate(time_slots=[])
        dumped = update.model_dump(exclude_unset=True, exclude_none=True)
        assert dumped["time_slots"] == []

    def test_omitted_slots_are_absent_from_the_change_set(self) -> None:
        update = ModelPriceUpdate(input_unit_price=Decimal("2.0"))
        dumped = update.model_dump(exclude_unset=True, exclude_none=True)
        assert "time_slots" not in dumped

    def test_rejects_overlapping_slots(self) -> None:
        with pytest.raises(ValidationError, match="overlap"):
            ModelPriceUpdate(time_slots=[VALID_SLOT, {**VALID_SLOT, "end_utc": "02:00"}])

    @pytest.mark.parametrize("unit", ["per_audio_minute", "per_audio_hour"])
    def test_rejects_slots_combined_with_an_audio_unit(self, unit: str) -> None:
        with pytest.raises(ValidationError, match="per_1m_tokens"):
            ModelPriceUpdate(pricing_unit=unit, time_slots=[VALID_SLOT])

    def test_clearing_alongside_a_unit_switch_is_legal(self) -> None:
        update = ModelPriceUpdate(pricing_unit="per_audio_hour", time_slots=[])
        assert update.time_slots == []
