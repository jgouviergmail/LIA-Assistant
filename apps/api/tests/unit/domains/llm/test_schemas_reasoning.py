"""Unit tests for the reasoning identity on ModelPriceCreate / ModelPriceUpdate.

Pure Pydantic tests -- no DB fixtures, run anywhere.

**What this file stopped testing.** Two thirds of it once exercised the
widget-conditional rules (``widget='enum'`` requires values, ``budget_int``
requires a range, ``widget='none'`` forbids both). Those went with the columns
they guarded (ADR-245), and the last of them had turned harmful: it forbade the
row an operator most often wants -- "this model reasons, and these are its
depths".

The rest went with the ``reasoning_template`` XOR, which had no caller left
once both editing surfaces -- the admin form and the ADR-228 workbook -- began
writing the ladder themselves. Copying another row's stored ladder could only
REMOVE depths, since a template groups models by that ladder rather than by
family.

What remains is what the schema still promises: ``is_reasoning_model`` plus an
optional ladder narrowing, with ``kind``, the four ``supports_*`` sampling caps
and ``reasoning_doc_i18n_key`` saved per model beside them.
"""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate


def _create_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid create payload."""
    base: dict[str, Any] = {
        "provider": "openai",
        "model_name": "test-model",
        "kind": "chat",
        "max_input_tokens": 1000,
        "max_output_tokens": 200,
        "supports_tools": True,
        "supports_structured_output": True,
        "supports_strict_mode": False,
        "supports_streaming": True,
        "supports_vision": False,
        "supports_temperature": True,
        "supports_top_p": True,
        "supports_frequency_penalty": True,
        "supports_presence_penalty": True,
        "input_unit_price": Decimal("1.0"),
        "cached_input_unit_price": None,
        "output_unit_price": Decimal("3.0"),
    }
    base.update(overrides)
    return base


# --- ModelPriceCreate: Template mode ---


@pytest.mark.unit
def test_create_template_mode_allows_doc_i18n_key_alongside() -> None:
    """``reasoning_doc_i18n_key`` is saved per model, outside the XOR."""
    payload = _create_payload(reasoning_doc_i18n_key="openai_gpt5_2")
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_doc_i18n_key == "openai_gpt5_2"


# --- ModelPriceCreate: Custom mode ---


@pytest.mark.unit
def test_create_custom_mode_non_reasoning_validates() -> None:
    """The minimum a Custom-mode row must state."""
    payload = _create_payload(reasoning_template=None, is_reasoning_model=False)
    obj = ModelPriceCreate(**payload)
    assert obj.is_reasoning_model is False
    assert obj.reasoning_enum_values is None


@pytest.mark.unit
def test_create_custom_mode_with_a_ladder_validates() -> None:
    """The ladder narrowing — the one catalogue value the runtime reads."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_enum_values=["low", "medium", "high"],
    )
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_enum_values == ["low", "medium", "high"]


@pytest.mark.unit
def test_create_custom_mode_without_a_ladder_validates() -> None:
    """Omitting it means "the family's own ladder applies", not "invalid"."""
    payload = _create_payload(reasoning_template=None, is_reasoning_model=True)
    obj = ModelPriceCreate(**payload)
    assert obj.is_reasoning_model is True
    assert obj.reasoning_enum_values is None


# --- ModelPriceCreate: fields outside the reasoning contract ---


@pytest.mark.unit
def test_create_missing_kind_rejected() -> None:
    payload = _create_payload()
    del payload["kind"]
    with pytest.raises(ValidationError):
        ModelPriceCreate(**payload)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field",
    [
        "supports_temperature",
        "supports_top_p",
        "supports_frequency_penalty",
        "supports_presence_penalty",
    ],
)
def test_create_missing_sampling_cap_rejected(field: str) -> None:
    payload = _create_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        ModelPriceCreate(**payload)


# --- ModelPriceUpdate ---


@pytest.mark.unit
def test_update_template_with_doc_i18n_key_validates() -> None:
    obj = ModelPriceUpdate(reasoning_template="gpt-4.1", reasoning_doc_i18n_key="k")
    assert obj.reasoning_doc_i18n_key == "k"


@pytest.mark.unit
def test_update_template_with_kind_validates() -> None:
    obj = ModelPriceUpdate(reasoning_template="gpt-4.1", kind="chat")
    assert obj.kind == "chat"


@pytest.mark.unit
def test_update_template_with_sampling_caps_validates() -> None:
    obj = ModelPriceUpdate(reasoning_template="gpt-4.1", supports_temperature=False)
    assert obj.supports_temperature is False


@pytest.mark.unit
def test_update_explicit_reasoning_without_template_validates() -> None:
    """Partial in-place mutation: no template, no cross-field rule to satisfy."""
    obj = ModelPriceUpdate(is_reasoning_model=True, reasoning_enum_values=["low", "high"])
    assert obj.reasoning_enum_values == ["low", "high"]


@pytest.mark.unit
def test_update_a_ladder_alone_validates() -> None:
    """Narrowing a model's ladder must not require restating its whole identity."""
    obj = ModelPriceUpdate(reasoning_enum_values=["high", "max"])
    assert obj.reasoning_enum_values == ["high", "max"]
    assert obj.is_reasoning_model is None


@pytest.mark.unit
def test_update_pricing_only_validates() -> None:
    obj = ModelPriceUpdate(input_unit_price=Decimal("2.0"))
    assert obj.input_unit_price == Decimal("2.0")
