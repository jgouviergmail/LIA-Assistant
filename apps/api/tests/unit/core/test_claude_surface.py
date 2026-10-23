"""The request surface each Claude generation accepts, pinned to what the API answered.

Every expectation below is a literal read on the Claude API on 2026-09-23 (the
Models API for the thinking shape, then near-free validation requests — count
tokens, ``max_tokens=0`` — for the rest; ADR-306). A wrong row is not a style
problem: each column is an HTTP 400 when it is got wrong, on every call.
"""

from __future__ import annotations

import pytest

from src.core.claude_surface import claude_surface

pytestmark = pytest.mark.unit

#: model -> (thinking, accepts_sampling, accepts_forced_tool_choice, binds_thinking)
MEASURED: dict[str, tuple[str, bool, bool, bool]] = {
    # ``adaptive`` refused (400) on the 4.5 generation: thinking is a token budget.
    "claude-haiku-4-5": ("budget", True, True, False),
    "claude-haiku-4-5-20251001": ("budget", True, True, False),
    "claude-sonnet-4-5": ("budget", True, True, False),
    "claude-sonnet-4-5-20250929": ("budget", True, True, False),
    "claude-opus-4-5": ("budget", True, True, False),
    "claude-opus-4-5-20251101": ("budget", True, True, False),
    # Adaptive, off unless asked; sampling still accepted.
    "claude-opus-4-6": ("adaptive", True, True, False),
    "claude-sonnet-4-6": ("adaptive", True, True, False),
    # « `temperature` is deprecated for this model » from Opus 4.7 on.
    "claude-opus-4-7": ("opt_in", False, True, False),
    "claude-opus-4-8": ("opt_in", False, True, False),
    # Thinks when the request says nothing; ``disabled`` still accepted.
    "claude-opus-5": ("default_on", False, True, False),
    "claude-sonnet-5": ("default_on", False, True, False),
    # ``thinking.type.disabled`` refused: thinking cannot be switched off.
    "claude-fable-5": ("always_on", False, True, False),
    # « tool_choice: type "tool" and "any" are not supported for this model »,
    # and a replayed thinking block is bound to the conversation that made it.
    "claude-fable-5-1": ("always_on", False, False, True),
    "claude-opus-5-5": ("always_on", False, False, True),
    # Read on the vendor's migration guide (2026-09-30), NOT measured -- no
    # Anthropic credit was left for a probe: ``disabled`` refused, its lowest
    # setting is ``between_tools``, forced tool choice refused, thinking bound.
    "claude-sonnet-5-5": ("between_tools", False, False, True),
    # Read on the vendor's overview, migration guide and thinking reference
    # (2026-10-08), NOT measured -- no spend on the Anthropic account: thinks
    # unasked, ``disabled`` accepted at ``high`` effort or below, sampling refused,
    # a replayed thinking block bound to its conversation -- and yet a forced
    # ``tool_choice`` ACCEPTED (the response then opens on the tool call).
    "claude-haiku-5-5": ("default_on", False, True, True),
}


@pytest.mark.parametrize(("model", "expected"), sorted(MEASURED.items()))
def test_each_served_model_resolves_to_its_measured_surface(
    model: str, expected: tuple[str, bool, bool, bool]
) -> None:
    surface = claude_surface(model)
    assert (
        surface.thinking,
        surface.accepts_sampling,
        surface.accepts_forced_tool_choice,
        surface.binds_thinking_to_conversation,
    ) == expected


def test_a_newer_name_is_never_captured_by_its_older_prefix() -> None:
    """``claude-opus-5`` is a prefix of ``claude-opus-5-5``, ``claude-opus-4`` of
    ``claude-opus-4-8``: an order mistake gives a model its predecessor's surface —
    the budget form Opus 4.8 refuses, or the forced tool call Opus 5.5 refuses."""
    assert claude_surface("claude-opus-5-5").accepts_forced_tool_choice is False
    assert claude_surface("claude-opus-5").accepts_forced_tool_choice is True
    assert claude_surface("claude-fable-5-1").binds_thinking_to_conversation is True
    assert claude_surface("claude-fable-5").binds_thinking_to_conversation is False
    assert claude_surface("claude-opus-4-8").thinking == "opt_in"
    assert claude_surface("claude-opus-4-7").thinking == "opt_in"
    # ``claude-sonnet-5`` is a prefix of ``claude-sonnet-5-5``: matched there it
    # would send ``disabled`` and force the structured-output tool, two 400s.
    assert claude_surface("claude-sonnet-5-5").thinking == "between_tools"
    assert claude_surface("claude-sonnet-5").thinking == "default_on"


def _facts(model: str) -> tuple[object, ...]:
    surface = claude_surface(model)
    return (
        surface.thinking,
        surface.implicit_effort,
        surface.accepts_sampling,
        surface.accepts_forced_tool_choice,
        surface.binds_thinking_to_conversation,
    )


def test_the_mythos_models_share_the_fable_surface() -> None:
    """Glasswing's Mythos is the same model as Fable under another name (not
    reachable from an ordinary organisation, so not offered by the catalogue)."""
    assert _facts("claude-mythos-5-1") == _facts("claude-fable-5-1")
    assert _facts("claude-mythos-5") == _facts("claude-fable-5")


def test_the_implicit_effort_is_the_one_the_api_applies_unasked() -> None:
    """Opus 5.5 defaults to ``medium``, every other thinking-by-default model to
    ``high`` (models overview, 2026-09-23); a model that does not think unasked
    has none."""
    assert claude_surface("claude-opus-5-5").implicit_effort == "medium"
    assert claude_surface("claude-fable-5-1").implicit_effort == "high"
    assert claude_surface("claude-opus-5").implicit_effort == "high"
    assert claude_surface("claude-sonnet-5").implicit_effort == "high"
    assert claude_surface("claude-sonnet-5-5").implicit_effort == "high"
    # Haiku 5.5's default is ``medium`` too (effort reference, 2026-10-08).
    assert claude_surface("claude-haiku-5-5").implicit_effort == "medium"
    assert claude_surface("claude-opus-4-8").implicit_effort is None
    assert claude_surface("claude-opus-4-6").implicit_effort is None


def test_an_undeclared_claude_model_gets_the_strictest_surface() -> None:
    """A generation released after this table is sent what every generation
    accepts: no sampling parameter (the API default applies), no forced tool
    call (the auto-tool path works everywhere), no binding beta (it requires a
    thinking form an unknown model may refuse)."""
    surface = claude_surface("claude-opus-6")
    assert surface.thinking is None
    assert surface.accepts_sampling is False
    assert surface.accepts_forced_tool_choice is False
    assert surface.binds_thinking_to_conversation is False
    assert surface.implicit_effort is None


#: model -> whether the API keeps a previous turn's thinking in the model's
#: context. Read on the prompt-caching page (2026-10-22): « Opus 4.5 and later,
#: Sonnet 4.6 and later, Haiku 5.5, Fable and Mythos » keep it; the earlier
#: Opus, Sonnet and Haiku models strip it themselves. Measured the same day on
#: ``claude-sonnet-5``: a replayed block, in LIA's two-assistant history shape,
#: is accepted and billed as input (ADR-362).
PRESERVES_PRIOR_TURN_THINKING: dict[str, bool] = {
    "claude-3-5-sonnet": False,
    "claude-sonnet-4": False,
    "claude-opus-4-1": False,
    "claude-haiku-4-5": False,
    "claude-sonnet-4-5": False,
    "claude-sonnet-4-5-20250929": False,
    "claude-opus-4-5": True,
    "claude-opus-4-5-20251101": True,
    "claude-opus-4-6": True,
    "claude-sonnet-4-6": True,
    "claude-opus-4-7": True,
    "claude-opus-4-8": True,
    "claude-opus-5": True,
    "claude-sonnet-5": True,
    "claude-fable-5": True,
    "claude-mythos-5": True,
    "claude-fable-5-1": True,
    "claude-opus-5-5": True,
    "claude-sonnet-5-5": True,
    "claude-haiku-5-5": True,
}


@pytest.mark.parametrize(("model", "expected"), sorted(PRESERVES_PRIOR_TURN_THINKING.items()))
def test_each_generation_says_whether_it_keeps_prior_turn_thinking(
    model: str, expected: bool
) -> None:
    assert claude_surface(model).preserves_prior_turn_thinking is expected


def test_opus_4_5_is_not_captured_by_the_older_opus_4_prefix() -> None:
    """The 4.5 generation shares its request surface but not its thinking
    retention: Opus 4.5 keeps prior thinking, Sonnet and Haiku 4.5 do not."""
    assert _facts("claude-opus-4-5") == _facts("claude-sonnet-4-5")
    assert claude_surface("claude-opus-4-5").preserves_prior_turn_thinking is True
    assert claude_surface("claude-opus-4-1").preserves_prior_turn_thinking is False


def test_an_undeclared_claude_model_keeps_no_prior_thinking() -> None:
    """Unknown retention reads as none: the history is sent without it."""
    assert claude_surface("claude-opus-6").preserves_prior_turn_thinking is False
