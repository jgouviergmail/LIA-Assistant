"""The ``ollama`` reasoning family: a ladder the server declares, never the name.

Ollama's ``think`` field accepts a boolean or a level. ``false`` is accepted by
every model; a positive level is refused (400) by a model without the
``thinking`` capability, and only the server knows which tag has it
(``/api/show``). So the family's ladder is a VOCABULARY the discovery narrows
per model -- full for a thinking model, ``("none",)`` for the others -- and a tag
nobody discovered stays unknown: no kwarg, no rejection, no offer.
"""

from __future__ import annotations

import pytest

from src.core.reasoning_intent import LEVELS, ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import (
    _RULES,
    FAMILIES,
    ollama_declared_ladder,
    resolve_reasoning_profile,
)
from src.infrastructure.llm.reasoning.translate import honours_exclude_from_output, translate

pytestmark = pytest.mark.unit

THINKING = ollama_declared_ladder(True)
PLAIN = ollama_declared_ladder(False)


def test_the_family_is_declared_and_ruled() -> None:
    assert "ollama" in FAMILIES
    assert any(
        provider == "ollama" and profile.family == "ollama" for provider, _, profile in _RULES
    )


def test_an_undeclared_tag_is_unknown_not_reasoning() -> None:
    """The pre-ADR-267 behaviour, kept on purpose: never a claim without a declaration."""
    profile = resolve_reasoning_profile("ollama", "some-tag:latest")
    assert profile.family == "none"
    assert profile.source == "unknown"
    for level in LEVELS:
        assert translate(ReasoningIntent(level=level), profile, "some-tag:latest", 4096) == {}  # type: ignore[arg-type]


def test_a_thinking_model_gets_the_full_ollama_ladder() -> None:
    profile = resolve_reasoning_profile("ollama", "qwen3.8:27b", model_levels=THINKING)
    assert profile.family == "ollama"
    assert profile.levels == ("none", "low", "medium", "high", "max")
    assert profile.can_disable is True
    assert profile.supports_budget is False


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("provider_default", {}),
        ("none", {"reasoning": False}),
        ("low", {"reasoning": "low"}),
        ("medium", {"reasoning": "medium"}),
        ("high", {"reasoning": "high"}),
        ("max", {"reasoning": "max"}),
        ("minimal", {"reasoning": "low"}),  # coerced upward onto the server vocabulary
        ("xhigh", {"reasoning": "max"}),
    ],
)
def test_a_thinking_model_translates_every_level(level: str, expected: dict) -> None:
    profile = resolve_reasoning_profile("ollama", "qwen3.8:27b", model_levels=THINKING)
    assert translate(ReasoningIntent(level=level), profile, "qwen3.8:27b", 4096) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("level", ["none", "low", "medium", "high", "max", "minimal", "xhigh"])
def test_a_model_that_cannot_think_only_ever_switches_thinking_off(level: str) -> None:
    """``("none",)`` is the one ladder shape the coercion keeps usable: every depth
    lands on the switch-off, which the server accepts on any model."""
    profile = resolve_reasoning_profile("ollama", "llama3.2", model_levels=PLAIN)
    assert profile.family == "ollama"
    assert profile.levels == ("none",)
    assert translate(ReasoningIntent(level=level), profile, "llama3.2", 4096) == {  # type: ignore[arg-type]
        "reasoning": False
    }


def test_provider_default_sends_nothing_on_any_ladder() -> None:
    for ladder in (THINKING, PLAIN):
        profile = resolve_reasoning_profile("ollama", "m", model_levels=ladder)
        assert translate(ReasoningIntent(), profile, "m", 4096) == {}


def test_the_declared_ladders_speak_the_ladder_vocabulary() -> None:
    """A seed guard refuses levels off the ladder; the discovery must obey it too."""
    assert set(THINKING) <= set(LEVELS)
    assert set(PLAIN) <= set(LEVELS)


def test_exclude_from_output_is_not_expressible() -> None:
    assert honours_exclude_from_output("ollama") is False


def test_a_budget_is_ignored_not_sent() -> None:
    profile = resolve_reasoning_profile("ollama", "qwen3.8:27b", model_levels=THINKING)
    produced = translate(ReasoningIntent(level="high", budget_tokens=2048), profile, "m", 4096)
    assert produced == {"reasoning": "high"}


def test_the_write_path_refuses_a_depth_a_plain_model_cannot_honour() -> None:
    """Philosophy A: the UI offers what the API accepts, and the API refuses the rest."""
    from types import SimpleNamespace

    from src.core.exceptions import StructuredValidationError
    from src.domains.llm_config.reasoning_validation import validate_reasoning_effort

    plain = SimpleNamespace(model_id="llama3.2", reasoning_enum_values=list(PLAIN))
    validate_reasoning_effort(plain, ReasoningIntent(level="none"), "ollama")
    with pytest.raises(StructuredValidationError):
        validate_reasoning_effort(plain, ReasoningIntent(level="medium"), "ollama")

    thinking = SimpleNamespace(model_id="qwen3.8:27b", reasoning_enum_values=list(THINKING))
    validate_reasoning_effort(thinking, ReasoningIntent(level="medium"), "ollama")

    undeclared = SimpleNamespace(model_id="new-tag", reasoning_enum_values=None)
    validate_reasoning_effort(undeclared, ReasoningIntent(level="high"), "ollama")


def test_the_admin_metadata_publishes_the_declared_ladder() -> None:
    """The UI is offered exactly what the API accepts (ADR-184's rule, ADR-245)."""
    from src.domains.llm_config.service import LLMConfigService
    from src.infrastructure.llm.model_profiles import ModelProfile

    thinking = ModelProfile(model_id="qwen3.8:27b", reasoning_enum_values=list(THINKING))
    published = LLMConfigService._reasoning_metadata("ollama", thinking)
    assert published["reasoning_family"] == "ollama"
    assert published["reasoning_levels"] == list(THINKING)
    assert published["reasoning_can_disable"] is True

    plain = ModelProfile(model_id="llama3.2", reasoning_enum_values=list(PLAIN))
    assert LLMConfigService._reasoning_metadata("ollama", plain)["reasoning_levels"] == ["none"]

    assert LLMConfigService._reasoning_metadata("ollama", None)["reasoning_levels"] == []
