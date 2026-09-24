"""Unit tests for the reasoning validation module.

Any invalid combination of (model, reasoning intent) MUST raise a structured
422 the frontend can turn into a "did you mean" hint.

**What this file stopped testing (ADR-245).** It used to cover a cross-product
of four stored shapes against four ``reasoning_widget`` values — 46 assertions
about which shape belonged to which widget. There is one shape now, an unknown
level is refused by the ``Literal`` on ``ReasoningIntent.level`` before this
module sees it, and what remains to reject is:

- a model that does not reason at all;
- a level the model's ladder does not offer;
- a token budget a level-based family cannot express, or one outside its range.

The production regression that motivated the original file is still covered:
``gpt-5.2`` accepting ``minimal`` when the OpenAI API rejects it. It is now
caught by the ladder rather than by an enum column — which means it is caught
for every model, including one the catalogue has never heard of.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from _pytest._code.code import ExceptionInfo
from fastapi import HTTPException

from src.core.reasoning_intent import ReasoningIntent
from src.domains.llm_config.reasoning_validation import (
    validate_reasoning_effort,
    validate_thinking_token_budget,
)

pytestmark = pytest.mark.unit


def _detail(exc: ExceptionInfo[HTTPException]) -> dict[str, Any]:
    """Return ``exc.value.detail`` typed as a dict for clean assertions."""
    return exc.value.detail  # type: ignore[return-value]


def _caps(model_id: str, levels: list[str] | None = None) -> SimpleNamespace:
    """A duck-typed ``_CapsLike``, with the catalogue's optional ladder."""
    return SimpleNamespace(
        model_id=model_id,
        reasoning_widget="enum" if levels else "none",
        reasoning_enum_values=levels,
        reasoning_budget_range=None,
        max_output_tokens=32768,
    )


def _agent_config(**overrides: Any) -> Any:
    """A minimal effective config for the thinking-budget guard."""
    base: dict[str, Any] = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "top_p": 1.0,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "max_tokens": 600,
        "reasoning_effort": None,
    }
    base.update(overrides)
    from src.core.llm_agent_config import LLMAgentConfig

    return LLMAgentConfig(**base)


class TestNothingToValidate:
    """The cases that must never reject."""

    def test_a_null_intent_is_valid_for_every_model(self) -> None:
        for model, provider in (("gpt-4.1", "openai"), ("gpt-5.2", "openai")):
            validate_reasoning_effort(_caps(model), None, provider)

    def test_provider_default_is_valid_on_a_reasoning_model(self) -> None:
        validate_reasoning_effort(_caps("gpt-5.2"), ReasoningIntent(), "openai")

    def test_an_absent_provider_rejects_nothing(self) -> None:
        """The family is derived from (provider, model).

        Without a provider it cannot be derived, and an underived family is not
        evidence that the model does not reason. Absence of evidence is never a
        rejection — the runtime resolves and coerces with the provider it has.
        """
        validate_reasoning_effort(_caps("anything"), ReasoningIntent(level="high"), None)

    def test_a_model_outside_every_rule_rejects_nothing(self) -> None:
        """A dynamically discovered Ollama tag must stay configurable."""
        validate_reasoning_effort(_caps("some-local-tag"), ReasoningIntent(level="high"), "ollama")


class TestNonReasoningModels:
    def test_a_non_reasoning_model_rejects_any_level(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(_caps("gpt-4.1"), ReasoningIntent(level="low"), "openai")
        detail = _detail(exc)
        assert exc.value.status_code == 422
        assert detail["type"] == "reasoning_not_supported"
        assert detail["ctx"] == {"model": "gpt-4.1", "family": "none"}

    @pytest.mark.parametrize("model", ["gpt-4o", "gpt-5-chat-latest", "computer-use-preview"])
    def test_the_negative_rules_all_reject(self, model: str) -> None:
        with pytest.raises(HTTPException):
            validate_reasoning_effort(_caps(model), ReasoningIntent(level="high"), "openai")


class TestLadderMembership:
    """The production regression, generalised: a level the model does not offer."""

    def test_gpt_52_rejects_minimal_when_the_catalogue_says_so(self) -> None:
        """The original bug: gpt-5.2 accepted 'minimal', the OpenAI API did not."""
        caps = _caps("gpt-5.2", levels=["none", "low", "medium", "high", "xhigh"])
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(caps, ReasoningIntent(level="minimal"), "openai")
        detail = _detail(exc)
        assert detail["type"] == "invalid_reasoning_effort"
        assert detail["ctx"]["submitted"] == "minimal"
        assert "minimal" not in detail["ctx"]["allowed"]

    def test_a_level_on_the_family_ladder_is_accepted(self) -> None:
        validate_reasoning_effort(_caps("gpt-5.2"), ReasoningIntent(level="medium"), "openai")

    def test_deepseek_rejects_a_level_its_ladder_does_not_carry(self) -> None:
        """``medium`` is not on the vendor's documented ``low/high/max`` ladder."""
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(
                _caps("deepseek-flash"), ReasoningIntent(level="medium"), "deepseek"
            )
        assert _detail(exc)["ctx"]["allowed"] == ["none", "low", "high", "max"]

    def test_the_catalogue_ladder_narrows_what_is_accepted(self) -> None:
        """A single-level row: everything else is refused."""
        caps = _caps("gpt-5.2-chat-latest", levels=["medium"])
        validate_reasoning_effort(caps, ReasoningIntent(level="medium"), "openai")
        with pytest.raises(HTTPException):
            validate_reasoning_effort(caps, ReasoningIntent(level="high"), "openai")


class TestBudgets:
    def test_a_budget_on_a_level_based_family_is_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(
                _caps("gpt-5.2"), ReasoningIntent(budget_tokens=1024), "openai"
            )
        assert _detail(exc)["type"] == "reasoning_budget_not_supported"

    def test_a_budget_inside_the_family_range_is_accepted(self) -> None:
        validate_reasoning_effort(
            _caps("claude-opus-4-5"), ReasoningIntent(budget_tokens=8192), "anthropic"
        )

    @pytest.mark.parametrize("budget", [1, 999_999])
    def test_a_budget_outside_the_family_range_is_rejected(self, budget: int) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(
                _caps("claude-opus-4-5"), ReasoningIntent(budget_tokens=budget), "anthropic"
            )
        detail = _detail(exc)
        assert detail["type"] == "invalid_reasoning_budget"
        assert detail["ctx"] == {"model": "claude-opus-4-5", "min": 1024, "max": 128000}


class TestThinkingTokenBudgetFloor:
    """The incident guard: reasoning tokens are billed inside ``max_tokens``.

    Measured in production 2026-07-29 — ``telephony_synthesis`` moved to
    ``deepseek-v4-flash`` at effort ``high`` while its effective ``max_tokens``
    stayed at 600, and every post-call synthesis came back unusable.
    """

    def _assert_blocks(self, effective: Any, floor: int = 4000) -> dict[str, Any]:
        with pytest.raises(HTTPException) as exc:
            validate_thinking_token_budget(
                llm_type="telephony_synthesis", effective=effective, floor=floor
            )
        assert exc.value.status_code == 422
        detail = _detail(exc)
        assert detail["type"] == "thinking_budget_below_floor"
        assert detail["loc"] == ["body", "max_tokens"]
        assert str(floor) in detail["msg"]
        assert detail["ctx"]["floor"] == floor
        assert detail["ctx"]["effective_max_tokens"] == effective.max_tokens
        return detail

    def _assert_passes(self, effective: Any, floor: int = 4000) -> None:
        validate_thinking_token_budget(
            llm_type="telephony_synthesis", effective=effective, floor=floor
        )

    def test_no_reasoning_passes_any_budget(self) -> None:
        self._assert_passes(_agent_config(reasoning_effort=None, max_tokens=100))

    @pytest.mark.parametrize("level", ["provider_default", "none", "minimal", "low"])
    def test_the_light_band_is_exempt(self, level: str) -> None:
        self._assert_passes(
            _agent_config(reasoning_effort=ReasoningIntent(level=level), max_tokens=100)
        )

    @pytest.mark.parametrize("level", ["medium", "high", "xhigh", "max"])
    def test_a_heavy_level_is_blocked_below_the_floor(self, level: str) -> None:
        self._assert_blocks(
            _agent_config(reasoning_effort=ReasoningIntent(level=level), max_tokens=600)
        )

    def test_a_heavy_level_at_the_floor_passes(self) -> None:
        self._assert_passes(
            _agent_config(reasoning_effort=ReasoningIntent(level="high"), max_tokens=4000)
        )

    def test_the_floor_is_caller_driven(self) -> None:
        effective = _agent_config(reasoning_effort=ReasoningIntent(level="high"), max_tokens=3000)
        self._assert_passes(effective, floor=2000)
        self._assert_blocks(effective, floor=8000)

    def test_an_explicit_budget_is_heavy_whatever_its_size(self) -> None:
        """The caller asked for thinking; the guard is about where it is billed."""
        self._assert_blocks(
            _agent_config(reasoning_effort=ReasoningIntent(budget_tokens=1024), max_tokens=600)
        )

    def test_a_zero_budget_is_not_heavy(self) -> None:
        self._assert_passes(
            _agent_config(reasoning_effort=ReasoningIntent(budget_tokens=0), max_tokens=100)
        )

    def test_the_guard_runs_on_the_effective_config(self) -> None:
        """Which is why the incident happened: an omitted max_tokens inherits.

        ``LLMAgentConfig.max_tokens`` is a required positive int, so "absent"
        never reaches this guard as ``None`` — it reaches it as the code
        default the merge filled in. That is exactly the shape of the 2026-07-29
        incident: the admin left the field empty, the default was calibrated for
        a non-thinking model, and 600 tokens went to a model that thinks.
        """
        from src.domains.llm_config.constants import LLM_DEFAULTS

        inherited = LLM_DEFAULTS["telephony_synthesis"].max_tokens
        assert inherited is not None and inherited > 0
        self._assert_passes(
            _agent_config(reasoning_effort=ReasoningIntent(level="low"), max_tokens=inherited)
        )


class TestAModelThatReasonsUnasked:
    """``provider_default`` is not "no reasoning" on a Claude generation that thinks unasked.

    Fable 5, Fable 5.1 and Opus 5.5 cannot switch thinking off; Opus 5 and
    Sonnet 5 think unless told not to (ADR-306). Leaving the level unset there
    buys the vendor's implicit depth -- billed inside ``max_tokens`` like any
    other -- so the incident guard must read that depth, not the empty field.
    """

    def _claude(self, model: str, intent: ReasoningIntent | None, max_tokens: int) -> Any:
        return _agent_config(
            provider="anthropic", model=model, reasoning_effort=intent, max_tokens=max_tokens
        )

    @pytest.mark.parametrize(
        ("model", "implicit"),
        [
            ("claude-fable-5-1", "high"),
            ("claude-fable-5", "high"),
            ("claude-opus-5-5", "medium"),
            ("claude-opus-5", "high"),
            ("claude-sonnet-5", "high"),
        ],
    )
    @pytest.mark.parametrize("intent", [None, ReasoningIntent(level="provider_default")])
    def test_an_unset_level_is_the_implicit_depth(
        self, model: str, implicit: str, intent: ReasoningIntent | None
    ) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_thinking_token_budget(
                llm_type="response", effective=self._claude(model, intent, 600), floor=4000
            )
        detail = _detail(exc)
        assert detail["type"] == "thinking_budget_below_floor"
        assert detail["ctx"]["implicit_level"] == implicit
        assert repr(implicit) in detail["msg"]

    def test_the_implicit_depth_at_the_floor_passes(self) -> None:
        validate_thinking_token_budget(
            llm_type="response", effective=self._claude("claude-opus-5-5", None, 4000), floor=4000
        )

    def test_switching_it_off_is_light(self) -> None:
        validate_thinking_token_budget(
            llm_type="response",
            effective=self._claude("claude-opus-5", ReasoningIntent(level="none"), 100),
            floor=4000,
        )

    def test_an_explicit_light_level_stays_light(self) -> None:
        """An operator who asked for ``low`` is judged on ``low``, not the default."""
        validate_thinking_token_budget(
            llm_type="response",
            effective=self._claude("claude-fable-5-1", ReasoningIntent(level="low"), 100),
            floor=4000,
        )

    @pytest.mark.parametrize(
        ("provider", "model"),
        [
            ("anthropic", "claude-opus-4-7"),  # opt-in: off until asked
            ("anthropic", "claude-opus-4-6"),
            ("anthropic", "claude-haiku-4-5"),
            ("deepseek", "deepseek-v4-flash"),  # no depth declared: unchanged
            ("openai", "gpt-5.2"),
        ],
    )
    def test_a_model_without_a_declared_implicit_depth_is_unchanged(
        self, provider: str, model: str
    ) -> None:
        validate_thinking_token_budget(
            llm_type="response",
            effective=_agent_config(
                provider=provider, model=model, reasoning_effort=None, max_tokens=100
            ),
            floor=4000,
        )


class TestExplicitOff:
    """``none`` is governed by ``can_disable``, never by ladder membership.

    A catalogue row narrows the ladder to the DEPTHS a model offers —
    ``claude-opus-4-6`` declares ["low","medium","high","max"] — without meaning
    "and it can no longer be turned off". Rejecting an explicit ``none`` there
    would refuse the one setting an operator most often wants, and it is the
    same trap the runtime coercion contract closes.
    """

    def test_none_is_accepted_when_the_ladder_omits_it(self) -> None:
        caps = _caps("claude-opus-4-6", levels=["low", "medium", "high", "max"])
        validate_reasoning_effort(caps, ReasoningIntent(level="none"), "anthropic")

    def test_none_is_accepted_on_the_family_ladder_too(self) -> None:
        validate_reasoning_effort(
            _caps("deepseek-v4-flash"), ReasoningIntent(level="none"), "deepseek"
        )

    def test_none_is_still_rejected_on_a_mandatory_reasoning_model(self) -> None:
        """``gemini-3.5-flash`` has no off switch; saying otherwise misprices it."""
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(
                _caps("gemini-3.5-flash"), ReasoningIntent(level="none"), "gemini"
            )
        assert _detail(exc)["type"] == "invalid_reasoning_effort"
