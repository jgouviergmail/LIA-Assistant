"""Pure unit tests for LLMModelService static helpers.

These exercise methods that don't touch the DB — fingerprinting, rendering
template descriptions, widget cohesion checks. They run anywhere without
testcontainers.
"""

from typing import Any

import pytest

from src.domains.llm.models import (
    LLMModel,
    LLMModelKindEnum,
    LLMProviderEnum,
    LLMReasoningWidgetEnum,
)
from src.domains.llm.service import LLMModelService


def _make_row(
    *,
    model_name: str = "test-model",
    provider: LLMProviderEnum = LLMProviderEnum.openai,
    kind: LLMModelKindEnum = LLMModelKindEnum.chat,
    is_reasoning_model: bool = False,
    reasoning_widget: LLMReasoningWidgetEnum = LLMReasoningWidgetEnum.none,
    reasoning_enum_values: list[str] | None = None,
    reasoning_budget_range: dict[str, Any] | None = None,
    reasoning_doc_i18n_key: str | None = None,
    supports_temperature: bool = True,
    supports_top_p: bool = True,
    supports_frequency_penalty: bool = True,
    supports_presence_penalty: bool = True,
) -> LLMModel:
    """Build a transient (un-persisted) LLMModel row for fingerprint testing."""
    row = LLMModel()
    row.model_name = model_name
    row.provider = provider
    row.kind = kind
    row.is_reasoning_model = is_reasoning_model
    row.reasoning_widget = reasoning_widget
    row.reasoning_enum_values = reasoning_enum_values
    row.reasoning_budget_range = reasoning_budget_range
    row.reasoning_doc_i18n_key = reasoning_doc_i18n_key
    row.supports_temperature = supports_temperature
    row.supports_top_p = supports_top_p
    row.supports_frequency_penalty = supports_frequency_penalty
    row.supports_presence_penalty = supports_presence_penalty
    return row


# --- _fingerprint ---


@pytest.mark.unit
def test_fingerprint_identical_shapes_match() -> None:
    """Two rows with the same 4 shape fields produce equal fingerprints."""
    a = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low", "medium", "high"],
    )
    b = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low", "medium", "high"],
    )
    assert LLMModelService._fingerprint(a) == LLMModelService._fingerprint(b)


@pytest.mark.unit
def test_fingerprint_excludes_kind() -> None:
    """``kind`` is intentionally NOT part of the fingerprint."""
    chat = _make_row(kind=LLMModelKindEnum.chat)
    image = _make_row(kind=LLMModelKindEnum.image)
    assert LLMModelService._fingerprint(chat) == LLMModelService._fingerprint(image)


@pytest.mark.unit
def test_fingerprint_excludes_sampling_caps() -> None:
    """Sampling caps differ but fingerprint stays equal."""
    full = _make_row(
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
    )
    none = _make_row(
        supports_temperature=False,
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
    )
    assert LLMModelService._fingerprint(full) == LLMModelService._fingerprint(none)


@pytest.mark.unit
def test_fingerprint_excludes_doc_i18n_key() -> None:
    """``reasoning_doc_i18n_key`` is intentionally NOT part of the fingerprint
    (UX detail, would otherwise explode the dedupe count)."""
    a = _make_row(reasoning_doc_i18n_key="key_a")
    b = _make_row(reasoning_doc_i18n_key="key_b")
    assert LLMModelService._fingerprint(a) == LLMModelService._fingerprint(b)


@pytest.mark.unit
def test_fingerprint_distinguishes_widgets() -> None:
    """Different widget values give different fingerprints."""
    none_w = _make_row(reasoning_widget=LLMReasoningWidgetEnum.none)
    enum_w = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low"],
    )
    assert LLMModelService._fingerprint(none_w) != LLMModelService._fingerprint(enum_w)


@pytest.mark.unit
def test_fingerprint_distinguishes_enum_values() -> None:
    """Different enum_values lists give different fingerprints."""
    a = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low", "medium", "high"],
    )
    b = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["off", "low", "high", "max"],
    )
    assert LLMModelService._fingerprint(a) != LLMModelService._fingerprint(b)


@pytest.mark.unit
def test_fingerprint_distinguishes_budget_ranges() -> None:
    """Different budget_range dicts give different fingerprints."""
    a = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.budget_int,
        reasoning_budget_range={"min": 0, "max": 1024, "off_sentinel": 0, "dynamic_sentinel": -1},
    )
    b = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.budget_int,
        reasoning_budget_range={"min": 0, "max": 32768, "off_sentinel": 0, "dynamic_sentinel": -1},
    )
    assert LLMModelService._fingerprint(a) != LLMModelService._fingerprint(b)


@pytest.mark.unit
def test_fingerprint_distinguishes_always_on_from_none() -> None:
    """Special case: deepseek-reasoner shape (widget=none, is_reasoning=True)
    must NOT collapse with regular non-reasoning models (is_reasoning=False)."""
    always_on = _make_row(is_reasoning_model=True, reasoning_widget=LLMReasoningWidgetEnum.none)
    no_reasoning = _make_row(is_reasoning_model=False, reasoning_widget=LLMReasoningWidgetEnum.none)
    assert LLMModelService._fingerprint(always_on) != LLMModelService._fingerprint(no_reasoning)


# --- _render_template_description ---


@pytest.mark.unit
def test_render_description_no_reasoning() -> None:
    """Non-reasoning rows render as 'no reasoning'."""
    row = _make_row(model_name="gpt-4.1")
    desc = LLMModelService._render_template_description(row, count=14)
    assert "no reasoning" in desc
    assert "gpt-4.1" in desc
    assert "14 models" in desc


@pytest.mark.unit
def test_render_description_always_on() -> None:
    """deepseek-reasoner shape renders as 'always-on reasoning'."""
    row = _make_row(
        model_name="deepseek-reasoner",
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.none,
    )
    desc = LLMModelService._render_template_description(row, count=1)
    assert "always-on reasoning" in desc
    assert "deepseek-reasoner" in desc


@pytest.mark.unit
def test_render_description_enum_widget() -> None:
    """Enum widget renders the bracketed value list."""
    row = _make_row(
        model_name="gpt-5",
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["minimal", "low", "medium", "high"],
    )
    desc = LLMModelService._render_template_description(row, count=3)
    assert "enum [minimal/low/medium/high]" in desc
    assert "gpt-5" in desc


@pytest.mark.unit
def test_render_description_budget_int_widget() -> None:
    """budget_int widget renders the min..max range."""
    row = _make_row(
        model_name="gemini-2.5-pro",
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.budget_int,
        reasoning_budget_range={"min": 128, "max": 32768},
    )
    desc = LLMModelService._render_template_description(row, count=1)
    assert "budget 128..32768" in desc
    assert "gemini-2.5-pro" in desc


@pytest.mark.unit
def test_render_description_toggle_budget_widget() -> None:
    """toggle_budget widget renders 'toggle+budget min..max'."""
    row = _make_row(
        model_name="qwen3-max",
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.toggle_budget,
        reasoning_budget_range={"min": 0, "max": 38912},
    )
    desc = LLMModelService._render_template_description(row, count=4)
    assert "toggle+budget 0..38912" in desc
    assert "4 models" in desc


@pytest.mark.unit
def test_render_description_singular_count() -> None:
    """count=1 uses the singular form."""
    row = _make_row(model_name="solo-model")
    desc = LLMModelService._render_template_description(row, count=1)
    assert "1 model" in desc
    assert "1 models" not in desc


# --- _validate_reasoning_cohesion ---


@pytest.mark.unit
def test_validate_cohesion_widget_change_to_enum_without_values_raises() -> None:
    """Widget=enum requires non-empty enum_values."""
    current = _make_row(is_reasoning_model=False, reasoning_widget=LLMReasoningWidgetEnum.none)
    changes = {"is_reasoning_model": True, "reasoning_widget": "enum"}
    with pytest.raises(ValueError, match="reasoning_enum_values"):
        LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_widget_change_to_enum_with_values_passes() -> None:
    """Widget=enum + enum_values supplied — OK."""
    current = _make_row(is_reasoning_model=False, reasoning_widget=LLMReasoningWidgetEnum.none)
    changes = {
        "is_reasoning_model": True,
        "reasoning_widget": "enum",
        "reasoning_enum_values": ["low", "high"],
    }
    # Should not raise.
    LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_widget_change_to_budget_int_without_range_raises() -> None:
    """Widget=budget_int requires reasoning_budget_range."""
    current = _make_row(is_reasoning_model=False, reasoning_widget=LLMReasoningWidgetEnum.none)
    changes = {"is_reasoning_model": True, "reasoning_widget": "budget_int"}
    with pytest.raises(ValueError, match="reasoning_budget_range"):
        LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_widget_change_to_toggle_budget_without_range_raises() -> None:
    """Widget=toggle_budget requires reasoning_budget_range."""
    current = _make_row(is_reasoning_model=False, reasoning_widget=LLMReasoningWidgetEnum.none)
    changes = {"is_reasoning_model": True, "reasoning_widget": "toggle_budget"}
    with pytest.raises(ValueError, match="reasoning_budget_range"):
        LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_widget_to_none_with_lingering_enum_values_raises() -> None:
    """Switching to widget='none' while enum_values stay set raises."""
    current = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low", "high"],
    )
    changes = {"reasoning_widget": "none"}  # forgot to clear enum_values
    with pytest.raises(ValueError, match="must NOT have"):
        LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_widget_to_none_with_explicit_clear_passes() -> None:
    """Switching to widget='none' AND clearing enum_values — OK."""
    current = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low", "high"],
    )
    changes = {"reasoning_widget": "none", "reasoning_enum_values": None}
    # Should not raise.
    LLMModelService._validate_reasoning_cohesion(current, changes)


@pytest.mark.unit
def test_validate_cohesion_no_widget_change_keeps_current_state() -> None:
    """When changes don't touch widget, current widget governs the check."""
    current = _make_row(
        is_reasoning_model=True,
        reasoning_widget=LLMReasoningWidgetEnum.enum,
        reasoning_enum_values=["low"],
    )
    # Updating only enum_values — current widget=enum, must keep non-empty.
    LLMModelService._validate_reasoning_cohesion(
        current, {"reasoning_enum_values": ["low", "medium", "high"]}
    )
    # Clearing enum_values while widget stays enum — invalid.
    with pytest.raises(ValueError, match="reasoning_enum_values"):
        LLMModelService._validate_reasoning_cohesion(current, {"reasoning_enum_values": []})
