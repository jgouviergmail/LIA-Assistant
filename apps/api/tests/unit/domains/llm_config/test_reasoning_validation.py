"""Unit tests for the strict reasoning_effort validation module.

The validation logic is the core of the backend strict policy: any invalid
combination of (model, reasoning_effort) MUST raise HTTPException(422) with a
structured ctx that the frontend can use to surface "did you mean" hints.

Regression: covers the production bug where ``gpt-5.2`` accepted
``reasoning_effort='minimal'`` despite the OpenAI API rejecting it.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from _pytest._code.code import ExceptionInfo
from fastapi import HTTPException

from src.core.reasoning_types import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)
from src.domains.llm_config.reasoning_validation import (
    reasoning_effort_matches_widget,
    validate_reasoning_effort,
)

CapsFactory = Callable[..., Any]


def _detail(exc: ExceptionInfo[HTTPException]) -> dict[str, Any]:
    """Return ``exc.value.detail`` typed as a dict for clean assertions.

    Starlette types ``HTTPException.detail`` as ``str`` even though FastAPI
    accepts ``Any``; this helper localises the cast in one place.
    """
    detail = exc.value.detail
    assert isinstance(detail, dict), f"Expected dict detail, got {type(detail).__name__}"
    return detail


@pytest.fixture
def caps_factory() -> CapsFactory:
    """Builds an in-memory fake of ModelCapabilities for validation tests.

    Uses SimpleNamespace so we don't depend on the full Pydantic ModelCapabilities
    constructor (which requires every field to be set). The validation function
    only reads attributes via duck typing.
    """

    def _make(**kwargs: Any) -> SimpleNamespace:
        defaults: dict[str, Any] = {
            "model_id": "test-model",
            "reasoning_widget": "none",
            "reasoning_enum_values": None,
            "reasoning_budget_range": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    return _make


# ============================================================================
# widget=none
# ============================================================================


@pytest.mark.unit
def test_widget_none_accepts_None(caps_factory: CapsFactory) -> None:
    caps = caps_factory(model_id="gpt-4.1", reasoning_widget="none")
    validate_reasoning_effort(caps, None)  # must not raise


@pytest.mark.unit
def test_widget_none_rejects_any_value(caps_factory: CapsFactory) -> None:
    caps = caps_factory(model_id="gpt-4.1", reasoning_widget="none")
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortEnum(effort="low"))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "reasoning_not_supported"
    assert _detail(exc)["ctx"]["model"] == "gpt-4.1"
    assert _detail(exc)["ctx"]["widget"] == "none"


# ============================================================================
# widget=enum
# ============================================================================


@pytest.mark.unit
def test_widget_enum_accepts_value_in_list(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gpt-5.2",
        reasoning_widget="enum",
        reasoning_enum_values=["none", "low", "medium", "high", "xhigh"],
    )
    validate_reasoning_effort(caps, ReasoningEffortEnum(effort="high"))


@pytest.mark.unit
def test_widget_enum_rejects_value_not_in_list_PROD_BUG_REGRESSION(
    caps_factory: CapsFactory,
) -> None:
    """Original prod bug: gpt-5.2 + 'minimal' must be rejected."""
    caps = caps_factory(
        model_id="gpt-5.2",
        reasoning_widget="enum",
        reasoning_enum_values=["none", "low", "medium", "high", "xhigh"],
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortEnum(effort="minimal"))
    assert exc.value.status_code == 422
    detail = _detail(exc)
    assert detail["type"] == "invalid_reasoning_effort"
    assert detail["ctx"]["model"] == "gpt-5.2"
    assert detail["ctx"]["provided"] == "minimal"
    assert detail["ctx"]["allowed"] == ["none", "low", "medium", "high", "xhigh"]
    assert detail["ctx"]["widget"] == "enum"
    assert "gpt-5.2" in detail["msg"]
    assert "minimal" in detail["msg"]


@pytest.mark.unit
def test_widget_enum_rejects_wrong_shape(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gpt-5",
        reasoning_widget="enum",
        reasoning_enum_values=["minimal", "low", "medium", "high"],
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortBudget(budget=1024))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "wrong_reasoning_effort_shape"


# ============================================================================
# widget=budget_int
# ============================================================================


@pytest.mark.unit
def test_widget_budget_int_accepts_value_in_range(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gemini-2.5-flash",
        reasoning_widget="budget_int",
        reasoning_budget_range={
            "min": 1,
            "max": 24576,
            "off_sentinel": 0,
            "dynamic_sentinel": -1,
        },
    )
    validate_reasoning_effort(caps, ReasoningEffortBudget(budget=16384))


@pytest.mark.unit
def test_widget_budget_int_accepts_off_sentinel(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gemini-2.5-flash",
        reasoning_widget="budget_int",
        reasoning_budget_range={
            "min": 1,
            "max": 24576,
            "off_sentinel": 0,
            "dynamic_sentinel": -1,
        },
    )
    validate_reasoning_effort(caps, ReasoningEffortBudget(budget=0))


@pytest.mark.unit
def test_widget_budget_int_accepts_dynamic_sentinel(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gemini-2.5-flash",
        reasoning_widget="budget_int",
        reasoning_budget_range={
            "min": 1,
            "max": 24576,
            "off_sentinel": 0,
            "dynamic_sentinel": -1,
        },
    )
    validate_reasoning_effort(caps, ReasoningEffortBudget(budget=-1))


@pytest.mark.unit
def test_widget_budget_int_rejects_out_of_range(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gemini-2.5-flash",
        reasoning_widget="budget_int",
        reasoning_budget_range={
            "min": 1,
            "max": 24576,
            "off_sentinel": 0,
            "dynamic_sentinel": -1,
        },
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortBudget(budget=24577))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "invalid_reasoning_budget"
    assert _detail(exc)["ctx"]["range"] == {"min": 1, "max": 24576}


@pytest.mark.unit
def test_widget_budget_int_pro_no_off_sentinel(caps_factory: CapsFactory) -> None:
    """gemini-2.5-pro cannot be disabled - only dynamic_sentinel exists."""
    caps = caps_factory(
        model_id="gemini-2.5-pro",
        reasoning_widget="budget_int",
        reasoning_budget_range={"min": 128, "max": 32768, "dynamic_sentinel": -1},
    )
    # 0 is NOT a valid off_sentinel here (None) so it must fall in range
    # [128, 32768] -> rejected
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortBudget(budget=0))
    assert exc.value.status_code == 422


@pytest.mark.unit
def test_widget_budget_int_rejects_wrong_shape(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="gemini-2.5-flash",
        reasoning_widget="budget_int",
        reasoning_budget_range={"min": 1, "max": 24576},
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortEnum(effort="high"))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "wrong_reasoning_effort_shape"


# ============================================================================
# widget=toggle_budget
# ============================================================================


@pytest.mark.unit
def test_widget_toggle_budget_accepts_disabled(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="qwen3.5-plus",
        reasoning_widget="toggle_budget",
        reasoning_budget_range={"min": 0, "max": 32768},
    )
    validate_reasoning_effort(caps, ReasoningEffortToggleBudget(enabled=False))


@pytest.mark.unit
def test_widget_toggle_budget_accepts_enabled_with_budget(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="qwen3.5-plus",
        reasoning_widget="toggle_budget",
        reasoning_budget_range={"min": 0, "max": 32768},
    )
    validate_reasoning_effort(caps, ReasoningEffortToggleBudget(enabled=True, budget=4096))


@pytest.mark.unit
def test_widget_toggle_budget_accepts_enabled_without_budget(caps_factory: CapsFactory) -> None:
    """budget=None means model default max, which is valid."""
    caps = caps_factory(
        model_id="qwen3.5-plus",
        reasoning_widget="toggle_budget",
        reasoning_budget_range={"min": 0, "max": 32768},
    )
    validate_reasoning_effort(caps, ReasoningEffortToggleBudget(enabled=True, budget=None))


@pytest.mark.unit
def test_widget_toggle_budget_rejects_budget_out_of_range(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="qwen3.5-plus",
        reasoning_widget="toggle_budget",
        reasoning_budget_range={"min": 0, "max": 32768},
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortToggleBudget(enabled=True, budget=32769))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "invalid_reasoning_budget"


@pytest.mark.unit
def test_widget_toggle_budget_rejects_wrong_shape(caps_factory: CapsFactory) -> None:
    caps = caps_factory(
        model_id="qwen3.5-plus",
        reasoning_widget="toggle_budget",
        reasoning_budget_range={"min": 0, "max": 32768},
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortEnum(effort="high"))
    assert exc.value.status_code == 422
    assert _detail(exc)["type"] == "wrong_reasoning_effort_shape"


# ============================================================================
# Parametrized full matrix - covers spec section 8.1 across all providers
# ============================================================================


def _build_value(case: dict[str, Any] | None) -> ReasoningEffortValue:
    """Helper: build a ReasoningEffortValue from a dict-like test case."""
    if case is None:
        return None
    if "effort" in case:
        return ReasoningEffortEnum(**case)
    if "enabled" in case:
        return ReasoningEffortToggleBudget(**case)
    if "budget" in case:
        return ReasoningEffortBudget(**case)
    raise ValueError(f"Cannot infer shape from {case}")


@pytest.mark.unit
@pytest.mark.parametrize(
    "model_name,widget,enum_values,range_,valid_cases,invalid_cases",
    [
        # OpenAI o-series
        (
            "o1",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}],
            [{"effort": "minimal"}, {"effort": "none"}, {"effort": "xhigh"}],
        ),
        ("o1-mini", "none", None, None, [None], [{"effort": "low"}]),
        (
            "o3-mini",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "high"}],
            [{"effort": "minimal"}],
        ),
        (
            "o4-mini",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "low"}],
            [{"effort": "minimal"}],
        ),
        # GPT-5
        (
            "gpt-5",
            "enum",
            ["minimal", "low", "medium", "high"],
            None,
            [{"effort": "minimal"}, {"effort": "high"}],
            [{"effort": "none"}, {"effort": "xhigh"}],
        ),
        (
            "gpt-5-pro",
            "enum",
            ["high"],
            None,
            [{"effort": "high"}],
            [{"effort": "low"}, {"effort": "medium"}],
        ),
        # GPT-5.2 - the original prod-bug case
        (
            "gpt-5.2",
            "enum",
            ["none", "low", "medium", "high", "xhigh"],
            None,
            [{"effort": "none"}, {"effort": "xhigh"}, {"effort": "medium"}],
            [{"effort": "minimal"}],
        ),
        (
            "gpt-5.2-pro",
            "enum",
            ["medium", "high", "xhigh"],
            None,
            [{"effort": "medium"}],
            [{"effort": "low"}, {"effort": "minimal"}],
        ),
        (
            "gpt-5.2-chat-latest",
            "enum",
            ["medium"],
            None,
            [{"effort": "medium"}],
            [{"effort": "low"}, {"effort": "high"}],
        ),
        (
            "gpt-5.4-mini",
            "enum",
            ["none", "low", "medium", "high", "xhigh"],
            None,
            [{"effort": "xhigh"}],
            [{"effort": "minimal"}],
        ),
        # GPT-4 / GPT-4o (non-reasoning)
        ("gpt-4.1", "none", None, None, [None], [{"effort": "low"}]),
        ("gpt-4o", "none", None, None, [None], [{"effort": "low"}]),
        # Anthropic 4.5+
        (
            "claude-opus-4-5",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "high"}],
            [{"effort": "max"}, {"effort": "minimal"}],
        ),
        (
            "claude-opus-4-6",
            "enum",
            ["low", "medium", "high", "max"],
            None,
            [{"effort": "max"}],
            [{"effort": "xhigh"}],
        ),
        (
            "claude-sonnet-4-6",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "high"}],
            [{"effort": "max"}],
        ),
        ("claude-haiku-4-5", "none", None, None, [None], [{"effort": "low"}]),
        # DeepSeek V4
        (
            "deepseek-v4-flash",
            "enum",
            ["off", "high", "max"],
            None,
            [{"effort": "off"}, {"effort": "max"}],
            [{"effort": "low"}, {"effort": "medium"}, {"effort": "minimal"}],
        ),
        # Gemini 2.5 (budget_int)
        (
            "gemini-2.5-flash",
            "budget_int",
            None,
            {"min": 1, "max": 24576, "off_sentinel": 0, "dynamic_sentinel": -1},
            [{"budget": 0}, {"budget": -1}, {"budget": 16384}, {"budget": 24576}],
            [{"budget": 24577}],
        ),
        (
            "gemini-2.5-pro",
            "budget_int",
            None,
            {"min": 128, "max": 32768, "dynamic_sentinel": -1},
            [{"budget": -1}, {"budget": 128}, {"budget": 32768}],
            [{"budget": 0}, {"budget": 127}, {"budget": 32769}],
        ),
        # Gemini 3.x
        (
            "gemini-3-pro-preview",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "high"}],
            [{"effort": "minimal"}],
        ),
        (
            "gemini-3-flash-preview",
            "enum",
            ["minimal", "low", "medium", "high"],
            None,
            [{"effort": "minimal"}],
            [{"effort": "xhigh"}],
        ),
        # Qwen3 toggle_budget
        (
            "qwen3.5-plus",
            "toggle_budget",
            None,
            {"min": 0, "max": 32768},
            [
                {"enabled": False},
                {"enabled": True, "budget": 4096},
                {"enabled": True, "budget": None},
            ],
            [{"enabled": True, "budget": 32769}],
        ),
        # Perplexity
        (
            "sonar-deep-research",
            "enum",
            ["low", "medium", "high"],
            None,
            [{"effort": "low"}],
            [{"effort": "minimal"}],
        ),
        ("sonar-pro", "none", None, None, [None], [{"effort": "low"}]),
    ],
)
def test_validate_matrix_per_model(
    model_name: str,
    widget: str,
    enum_values: list[str] | None,
    range_: dict[str, Any] | None,
    valid_cases: list[dict[str, Any] | None],
    invalid_cases: list[dict[str, Any] | None],
    caps_factory: CapsFactory,
) -> None:
    """Exhaustive matrix per spec section 8.1. Includes the original prod-bug regression."""
    caps = caps_factory(
        model_id=model_name,
        reasoning_widget=widget,
        reasoning_enum_values=enum_values,
        reasoning_budget_range=range_,
    )

    for case in valid_cases:
        validate_reasoning_effort(caps, _build_value(case))  # must not raise

    for case in invalid_cases:
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(caps, _build_value(case))
        assert (
            exc.value.status_code == 422
        ), f"Expected 422 for {model_name} + {case}, got {exc.value.status_code}"
        assert _detail(exc)["ctx"]["model"] == model_name


@pytest.mark.unit
class TestReasoningEffortMatchesWidget:
    """Non-raising twin of ``validate_reasoning_effort``.

    Used by callers that *reconcile* rather than *reject* — notably
    ``core.llm_config_helper.merge_config`` (drops a stale/incompatible
    reasoning_effort instead of crashing the typed reasoning builder) and the
    admin UI (clears the field when the model changes). Regression: the
    DeepSeek-style ``{"effort": "off"}`` must be rejected for a Qwen
    ``toggle_budget`` model.
    """

    def test_none_widget_accepts_only_null(self, caps_factory: CapsFactory) -> None:
        caps = caps_factory(reasoning_widget="none")
        assert reasoning_effort_matches_widget(caps, None) is True
        assert reasoning_effort_matches_widget(caps, ReasoningEffortEnum(effort="low")) is False
        assert (
            reasoning_effort_matches_widget(caps, ReasoningEffortToggleBudget(enabled=False))
            is False
        )

    def test_enum_widget_shape_and_allowed_value(self, caps_factory: CapsFactory) -> None:
        caps = caps_factory(
            reasoning_widget="enum", reasoning_enum_values=["low", "medium", "high"]
        )
        assert reasoning_effort_matches_widget(caps, ReasoningEffortEnum(effort="high")) is True
        # value not in the allowed set
        assert reasoning_effort_matches_widget(caps, ReasoningEffortEnum(effort="off")) is False
        # wrong shape (toggle on an enum widget)
        assert (
            reasoning_effort_matches_widget(caps, ReasoningEffortToggleBudget(enabled=False))
            is False
        )
        # null is not valid for a reasoning-capable widget
        assert reasoning_effort_matches_widget(caps, None) is False

    def test_toggle_budget_widget_rejects_enum_shape(self, caps_factory: CapsFactory) -> None:
        caps = caps_factory(
            reasoning_widget="toggle_budget",
            reasoning_budget_range={"min": 0, "max": 32768},
        )
        assert (
            reasoning_effort_matches_widget(caps, ReasoningEffortToggleBudget(enabled=False))
            is True
        )
        assert (
            reasoning_effort_matches_widget(
                caps, ReasoningEffortToggleBudget(enabled=True, budget=8192)
            )
            is True
        )
        # the production bug: enum-shaped "off" left over from a DeepSeek model
        assert reasoning_effort_matches_widget(caps, ReasoningEffortEnum(effort="off")) is False
        # out-of-range budget
        assert (
            reasoning_effort_matches_widget(
                caps, ReasoningEffortToggleBudget(enabled=True, budget=10_000_000)
            )
            is False
        )

    def test_budget_int_widget(self, caps_factory: CapsFactory) -> None:
        caps = caps_factory(
            reasoning_widget="budget_int",
            reasoning_budget_range={"min": 512, "max": 24576, "off_sentinel": 0},
        )
        assert reasoning_effort_matches_widget(caps, ReasoningEffortBudget(budget=8192)) is True
        assert reasoning_effort_matches_widget(caps, ReasoningEffortBudget(budget=0)) is True
        # out of range and not a sentinel
        assert reasoning_effort_matches_widget(caps, ReasoningEffortBudget(budget=100)) is False
        # wrong shape
        assert (
            reasoning_effort_matches_widget(caps, ReasoningEffortToggleBudget(enabled=False))
            is False
        )
