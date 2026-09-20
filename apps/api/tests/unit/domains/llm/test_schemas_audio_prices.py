"""Schema-level validation of the audio rate pair on the admin pricing API (ADR-300 wave 3).

A speech-to-speech model bills its audio at a rate of its own, next to its
text rate. The pair is declared whole or not at all, only on a token-billed
unit, and — on an update — cleared through a shape of its own, because the
service's change-set drops nulls (the cached price's own trap).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceResponse, ModelPriceUpdate

pytestmark = pytest.mark.unit


def _create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "gemini",
        "model_name": "gemini-live-model",
        "kind": "realtime",
        "max_input_tokens": 8192,
        "max_output_tokens": 4096,
        "supports_tools": True,
        "supports_structured_output": False,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_temperature": False,
        "supports_top_p": False,
        "supports_frequency_penalty": False,
        "supports_presence_penalty": False,
        "is_reasoning_model": False,
        "input_unit_price": Decimal("0.75"),
        "cached_input_unit_price": None,
        "output_unit_price": Decimal("4.5"),
    }
    payload.update(overrides)
    return payload


class TestCreate:
    def test_accepts_the_whole_pair_on_a_token_billed_unit(self) -> None:
        data = ModelPriceCreate(
            **_create_payload(
                audio_input_unit_price=Decimal("3"), audio_output_unit_price=Decimal("12")
            )
        )
        assert (data.audio_input_unit_price, data.audio_output_unit_price) == (
            Decimal("3"),
            Decimal("12"),
        )

    def test_accepts_no_pair_at_all(self) -> None:
        data = ModelPriceCreate(**_create_payload())
        assert data.audio_input_unit_price is None
        assert data.audio_output_unit_price is None

    @pytest.mark.parametrize(
        "half",
        [{"audio_input_unit_price": Decimal("3")}, {"audio_output_unit_price": Decimal("12")}],
        ids=["input_only", "output_only"],
    )
    def test_refuses_half_a_pair(self, half: dict[str, Any]) -> None:
        with pytest.raises(ValidationError, match="audio"):
            ModelPriceCreate(**_create_payload(**half))

    def test_refuses_the_pair_on_a_minute_billed_unit(self) -> None:
        with pytest.raises(ValidationError, match="per_1m_tokens"):
            ModelPriceCreate(
                **_create_payload(
                    pricing_unit="per_audio_minute",
                    audio_input_unit_price=Decimal("3"),
                    audio_output_unit_price=Decimal("12"),
                )
            )

    def test_refuses_a_negative_rate(self) -> None:
        with pytest.raises(ValidationError):
            ModelPriceCreate(
                **_create_payload(
                    audio_input_unit_price=Decimal("-1"), audio_output_unit_price=Decimal("12")
                )
            )


class TestUpdate:
    def test_a_sparse_update_may_carry_one_rate(self) -> None:
        # The merged state (with the current row's other rate) is the service's to judge.
        data = ModelPriceUpdate(audio_output_unit_price=Decimal("12"))
        assert data.audio_output_unit_price == Decimal("12")
        assert data.audio_input_unit_price is None
        assert data.clear_audio_prices is False

    def test_clearing_and_setting_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValidationError, match="clear_audio_prices"):
            ModelPriceUpdate(clear_audio_prices=True, audio_input_unit_price=Decimal("3"))

    def test_refuses_a_rate_beside_a_minute_billed_unit(self) -> None:
        with pytest.raises(ValidationError, match="per_1m_tokens"):
            ModelPriceUpdate(pricing_unit="per_audio_hour", audio_input_unit_price=Decimal("3"))

    def test_the_change_set_never_carries_a_bare_null_for_the_pair(self) -> None:
        # exclude_none is how the service builds its change-set: a null would
        # be dropped, so clearing needs its own shape (the cached price's rule).
        data = ModelPriceUpdate(clear_audio_prices=True)
        assert "audio_input_unit_price" not in data.model_dump(exclude_none=True)
        assert data.model_dump(exclude_none=True)["clear_audio_prices"] is True


class TestResponse:
    def test_carries_the_pair_and_defaults_it_to_null(self) -> None:
        fields = ModelPriceResponse.model_fields
        assert "audio_input_unit_price" in fields and "audio_output_unit_price" in fields
        assert fields["audio_input_unit_price"].default is None
        assert fields["audio_output_unit_price"].default is None
