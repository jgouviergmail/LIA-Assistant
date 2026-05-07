"""Unit tests for ModelPriceCreate / ModelPriceUpdate validators (reasoning template XOR).

Pure Pydantic tests — no DB fixtures, run anywhere. The XOR contract between
``reasoning_template`` (Template mode) and the four explicit reasoning shape
fields (Custom mode) is enforced at schema validation time before reaching
the service layer.

The four ``supports_*`` sampling caps, ``kind`` and ``reasoning_doc_i18n_key``
are intentionally outside the XOR — they are saved per model regardless of
the reasoning template chosen.
"""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from src.core.reasoning_types import ReasoningBudgetRange
from src.domains.llm.schemas import ModelPriceCreate, ModelPriceUpdate


def _create_payload(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid create payload — defaults to Template mode.

    Custom-mode tests override ``reasoning_template`` to ``None`` and add
    the explicit reasoning fields.
    """
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
        "reasoning_template": "gpt-4.1",  # Template mode by default
        "input_price_per_1m_tokens": Decimal("1.0"),
        "cached_input_price_per_1m_tokens": None,
        "output_price_per_1m_tokens": Decimal("3.0"),
    }
    base.update(overrides)
    return base


# --- ModelPriceCreate: Template mode ---


@pytest.mark.unit
def test_create_template_mode_minimal_payload_validates() -> None:
    """Template mode passes validation with just ``reasoning_template`` set."""
    payload = _create_payload()
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_template == "gpt-4.1"
    assert obj.is_reasoning_model is None
    assert obj.reasoning_widget is None


@pytest.mark.unit
def test_create_template_mode_rejects_explicit_reasoning_widget() -> None:
    """Template + explicit reasoning_widget = XOR violation."""
    payload = _create_payload(reasoning_widget="enum")
    with pytest.raises(ValidationError, match="Template mode is exclusive"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_template_mode_rejects_explicit_is_reasoning_model() -> None:
    """Template + explicit is_reasoning_model = XOR violation."""
    payload = _create_payload(is_reasoning_model=True)
    with pytest.raises(ValidationError, match="Template mode is exclusive"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_template_mode_rejects_explicit_enum_values() -> None:
    """Template + explicit reasoning_enum_values = XOR violation."""
    payload = _create_payload(reasoning_enum_values=["low", "high"])
    with pytest.raises(ValidationError, match="Template mode is exclusive"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_template_mode_rejects_explicit_budget_range() -> None:
    """Template + explicit reasoning_budget_range = XOR violation."""
    payload = _create_payload(
        reasoning_budget_range=ReasoningBudgetRange(min=0, max=1024),
    )
    with pytest.raises(ValidationError, match="Template mode is exclusive"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_template_mode_allows_doc_i18n_key_alongside() -> None:
    """``reasoning_doc_i18n_key`` is independent of the template — must NOT
    raise the XOR error when passed alongside ``reasoning_template``."""
    payload = _create_payload(reasoning_doc_i18n_key="custom_tooltip_key")
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_template == "gpt-4.1"
    assert obj.reasoning_doc_i18n_key == "custom_tooltip_key"


# --- ModelPriceCreate: Custom mode ---


@pytest.mark.unit
def test_create_custom_mode_widget_none_validates() -> None:
    """Non-reasoning model in Custom mode (widget='none')."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=False,
        reasoning_widget="none",
    )
    obj = ModelPriceCreate(**payload)
    assert obj.is_reasoning_model is False
    assert obj.reasoning_widget == "none"


@pytest.mark.unit
def test_create_custom_mode_enum_widget_validates() -> None:
    """Custom mode widget=enum requires non-empty enum_values."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="enum",
        reasoning_enum_values=["low", "medium", "high"],
    )
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_widget == "enum"
    assert obj.reasoning_enum_values == ["low", "medium", "high"]


@pytest.mark.unit
def test_create_custom_mode_enum_without_values_rejected() -> None:
    """Custom mode widget=enum without enum_values raises."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="enum",
    )
    with pytest.raises(ValidationError, match="reasoning_enum_values"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_enum_with_empty_values_rejected() -> None:
    """Custom mode widget=enum with empty list also rejected (non-empty required)."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="enum",
        reasoning_enum_values=[],
    )
    with pytest.raises(ValidationError, match="reasoning_enum_values"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_budget_int_validates() -> None:
    """Custom mode widget=budget_int with budget_range."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="budget_int",
        reasoning_budget_range=ReasoningBudgetRange(
            min=0, max=32768, off_sentinel=0, dynamic_sentinel=-1
        ),
    )
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_widget == "budget_int"
    assert obj.reasoning_budget_range is not None
    assert obj.reasoning_budget_range.max == 32768


@pytest.mark.unit
def test_create_custom_mode_budget_int_without_range_rejected() -> None:
    """Custom mode widget=budget_int without budget_range raises."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="budget_int",
    )
    with pytest.raises(ValidationError, match="reasoning_budget_range"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_toggle_budget_validates() -> None:
    """Custom mode widget=toggle_budget."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="toggle_budget",
        reasoning_budget_range=ReasoningBudgetRange(min=0, max=38912),
    )
    obj = ModelPriceCreate(**payload)
    assert obj.reasoning_widget == "toggle_budget"
    assert obj.reasoning_budget_range is not None
    assert obj.reasoning_budget_range.max == 38912


@pytest.mark.unit
def test_create_custom_mode_toggle_budget_without_range_rejected() -> None:
    """Custom mode widget=toggle_budget without budget_range raises."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=True,
        reasoning_widget="toggle_budget",
    )
    with pytest.raises(ValidationError, match="reasoning_budget_range"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_widget_none_with_enum_values_rejected() -> None:
    """widget='none' must NOT carry enum_values."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=False,
        reasoning_widget="none",
        reasoning_enum_values=["low"],
    )
    with pytest.raises(ValidationError, match="must NOT have"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_widget_none_with_budget_range_rejected() -> None:
    """widget='none' must NOT carry budget_range."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=False,
        reasoning_widget="none",
        reasoning_budget_range=ReasoningBudgetRange(min=0, max=1024),
    )
    with pytest.raises(ValidationError, match="must NOT have"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_missing_is_reasoning_model_rejected() -> None:
    """Custom mode requires is_reasoning_model."""
    payload = _create_payload(
        reasoning_template=None,
        reasoning_widget="none",
    )
    with pytest.raises(ValidationError, match="Custom mode requires"):
        ModelPriceCreate(**payload)


@pytest.mark.unit
def test_create_custom_mode_missing_widget_rejected() -> None:
    """Custom mode requires reasoning_widget."""
    payload = _create_payload(
        reasoning_template=None,
        is_reasoning_model=False,
    )
    with pytest.raises(ValidationError, match="Custom mode requires"):
        ModelPriceCreate(**payload)


# --- ModelPriceCreate: required catalogue fields ---


@pytest.mark.unit
def test_create_missing_kind_rejected() -> None:
    """``kind`` is now a required catalogue field."""
    payload = _create_payload()
    payload.pop("kind")
    with pytest.raises(ValidationError, match="kind"):
        ModelPriceCreate(**payload)


@pytest.mark.parametrize(
    "field",
    [
        "supports_temperature",
        "supports_top_p",
        "supports_frequency_penalty",
        "supports_presence_penalty",
    ],
)
@pytest.mark.unit
def test_create_missing_sampling_cap_rejected(field: str) -> None:
    """All four sampling caps are required catalogue fields."""
    payload = _create_payload()
    payload.pop(field)
    with pytest.raises(ValidationError, match=field):
        ModelPriceCreate(**payload)


# --- ModelPriceUpdate ---


@pytest.mark.unit
def test_update_template_alone_validates() -> None:
    """Update with only ``reasoning_template`` set is allowed."""
    obj = ModelPriceUpdate(reasoning_template="gpt-4.1")
    assert obj.reasoning_template == "gpt-4.1"


@pytest.mark.unit
def test_update_template_with_doc_i18n_key_validates() -> None:
    """``reasoning_doc_i18n_key`` is independent of the template — allowed."""
    obj = ModelPriceUpdate(
        reasoning_template="gpt-4.1",
        reasoning_doc_i18n_key="custom_key",
    )
    assert obj.reasoning_template == "gpt-4.1"
    assert obj.reasoning_doc_i18n_key == "custom_key"


@pytest.mark.unit
def test_update_template_with_kind_validates() -> None:
    """``kind`` is independent of the template — allowed."""
    obj = ModelPriceUpdate(
        reasoning_template="gpt-4.1",
        kind="chat",
    )
    assert obj.reasoning_template == "gpt-4.1"
    assert obj.kind == "chat"


@pytest.mark.unit
def test_update_template_with_sampling_caps_validates() -> None:
    """The four sampling caps are independent of the template — allowed."""
    obj = ModelPriceUpdate(
        reasoning_template="gpt-4.1",
        supports_temperature=True,
        supports_top_p=False,
    )
    assert obj.reasoning_template == "gpt-4.1"
    assert obj.supports_temperature is True
    assert obj.supports_top_p is False


@pytest.mark.unit
def test_update_template_with_explicit_widget_rejected() -> None:
    """Template + explicit reasoning_widget = XOR violation."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        ModelPriceUpdate(reasoning_template="gpt-4.1", reasoning_widget="enum")


@pytest.mark.unit
def test_update_template_with_explicit_is_reasoning_rejected() -> None:
    """Template + explicit is_reasoning_model = XOR violation."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        ModelPriceUpdate(reasoning_template="gpt-4.1", is_reasoning_model=True)


@pytest.mark.unit
def test_update_template_with_explicit_enum_values_rejected() -> None:
    """Template + explicit reasoning_enum_values = XOR violation."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        ModelPriceUpdate(reasoning_template="gpt-4.1", reasoning_enum_values=["low"])


@pytest.mark.unit
def test_update_template_with_explicit_budget_range_rejected() -> None:
    """Template + explicit reasoning_budget_range = XOR violation."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        ModelPriceUpdate(
            reasoning_template="gpt-4.1",
            reasoning_budget_range=ReasoningBudgetRange(min=0, max=1024),
        )


@pytest.mark.unit
def test_update_explicit_reasoning_without_template_validates() -> None:
    """Pure Custom-mode update without template works."""
    obj = ModelPriceUpdate(
        is_reasoning_model=True,
        reasoning_widget="enum",
        reasoning_enum_values=["low", "medium", "high"],
    )
    assert obj.reasoning_template is None
    assert obj.reasoning_widget == "enum"


@pytest.mark.unit
def test_update_pricing_only_validates() -> None:
    """Pricing-only update — no reasoning fields involved."""
    obj = ModelPriceUpdate(input_price_per_1m_tokens=Decimal("2.5"))
    assert obj.input_price_per_1m_tokens == Decimal("2.5")
    assert obj.reasoning_template is None
